import html
import json
import time
from datetime import datetime, timedelta, timezone
import pytest
from test_minimal import n, api
from test_open_link import make_open
from invitation_store import ceremony_passed, valid_map_url


def test_ceremony_tashkent_day_boundary():
    details={'date':'05.11.2030'}
    assert not ceremony_passed(details,datetime(2030,11,5,18,59,59,tzinfo=timezone.utc).timestamp())
    assert ceremony_passed(details,datetime(2030,11,5,19,0,0,tzinfo=timezone.utc).timestamp())

async def test_expired_event_rejects_new_rsvp_and_keeps_saved_answer(n,api):
    item=await make_open(n); mid=item['id']; path=f'/api/invites/{mid}'
    for uid in (2,3): await n.msg(uid,f'/start i_{item["token"]}')
    status,first=await api('POST',path+'/rsvp',uid=2,json={'attending':1,'guests':2}); assert status==200
    assert any(f'Taklif #{mid}:' in message['text'] for message in n.sent(1))
    details=json.loads(item['details']); details['date']='01.01.2000'
    await n.db.run('UPDATE q_invites SET details=? WHERE id=?',(json.dumps(details),mid))
    status,late=await api('GET',path,uid=3); assert status==200 and late['rsvp_closed'] and late['rsvp'] is None
    status,error=await api('POST',path+'/rsvp',uid=3,json={'attending':1,'guests':1}); assert status==409 and 'o‘tib ketgan' in error['error']
    status,saved=await api('GET',path,uid=2); assert status==200 and saved['rsvp']==first['rsvp'] and saved['rsvp_closed']
    assert (await api('POST',path+'/rsvp',uid=2,json={'attending':0,'guests':0}))[1]==first
    await n.db.run('UPDATE q_invites SET expires_at=0 WHERE id=?',(mid,))
    assert await n.db.claim(item['token'],2)==mid
    assert await n.db.claim(item['token'],3) is None
    assert (await api('GET',path,uid=2))[1]['rsvp']==first['rsvp']

async def test_500_guest_entries_paginate_and_fit_telegram(n):
    item=await make_open(n); mid=item['id']
    async with n.db.connect(True) as c:
        await c.executemany('INSERT INTO q_rsvps(invite_id,telegram_user_id,attending,guests,responded_at,receiver_name,notice_status) VALUES(?,?,?,?,?,?,?)',[(mid,i,1,1,i,'<&>'*66+'X','suppressed') for i in range(1000,1500)])
    for page in range(250): await n.app.guests(1,mid,page)
    messages=[m for m in n.sent(1) if 'Kelaman:' in m.get('text','')]
    assert len(messages)==250
    assert all(len(html.unescape(m['text']))<=4096 and len(m['text'])<=4096 for m in messages)
    assert 'q:guests:1:249' in messages[-2]['reply_markup']
    assert 'q:guests:1:250' not in messages[-1].get('reply_markup','')

@pytest.mark.parametrize('url',['javascript:alert(1)','data:text/html,x','http://maps.google.com/x','https://evil.example/x','https://maps.google.com.evil.example/x'])
def test_unsafe_map_urls_rejected(url): assert not valid_map_url(url)

@pytest.mark.parametrize('method,suffix',[('GET',''),('GET','/media'),('POST','/accept'),('POST','/rsvp')])
async def test_all_invite_endpoints_reject_invalid_init_data(n,api,method,suffix):
    item=await make_open(n)
    assert (await api(method,f'/api/invites/{item["id"]}{suffix}',auth='hash=bad',json={} if method=='POST' else None))[0]==401

@pytest.mark.parametrize('snapshot',['pre_m0','m0','m1','pre_m4'])
async def test_historical_schema_upgrade_and_old_invite_open(n,api,tmp_path,snapshot):
    import sqlite3
    from pathlib import Path
    from invitation_store import InvitationDB
    path=tmp_path/f'{snapshot}.sqlite'
    with sqlite3.connect(path) as connection:
        connection.executescript((Path(__file__).parent/'fixtures'/'m6_schema'/f'{snapshot}.sql').read_text())
    database=InvitationDB(path); await database.init(); await database.init()
    n.app.db=database
    assert await database.claim('old-token',2)==1
    status,data=await api('GET','/api/invites/1',uid=2)
    assert status==200 and data['title']=='Old' and data['type']=='fun' and data['share_mode']=='single'
