import asyncio
import json
import time
from test_minimal import n, api
from test_ceremony import start, fill_to_map, finish

async def make_open(n):
    mid=await start(n); await fill_to_map(n,mid); await finish(n,mid,mode='open')
    await n.cb(1,f'q:confirm:{mid}')
    return await n.db.invite(mid)

async def test_open_two_users_idempotent_private_guests(n,api):
    item=await make_open(n); mid=item['id']; path=f'/api/invites/{mid}'
    assert item['share_mode']=='open' and item['receiver'] is None
    assert (await api('GET',path,uid=3))[0]==404
    for uid in (2,3): await n.msg(uid,f'/start i_{item["token"]}')
    a,b=await asyncio.gather(api('POST',path+'/rsvp',uid=2,json={'attending':1,'guests':3}),api('POST',path+'/rsvp',uid=3,json={'attending':0,'guests':0}))
    assert a[0]==b[0]==200
    assert (await api('GET',path,uid=2))[1]['rsvp']==a[1]['rsvp']
    assert (await api('GET',path,uid=3))[1]['rsvp']==b[1]['rsvp']
    assert (await api('POST',path+'/rsvp',uid=2,json={'attending':0,'guests':0}))[1]['rsvp']==a[1]['rsvp']
    assert (await api('GET',path,uid=2))[1]['share_mode']=='open'
    assert (await api('GET',path,auth='hash=bad'))[0]==401
    await n.msg(1,'/guests'); assert 'jami 3 kishi' in n.sent(1)[-1]['text'] and 'Ism2' in n.sent(1)[-1]['text']
    await n.cb(3,f'q:guests:{mid}:0'); assert 'topilmadi' in n.sent(3)[-1]['text']
    assert any('share/url' in m.get('reply_markup','') for m in n.sent(1))

async def test_limit_rate_and_first_50(n,api):
    item=await make_open(n); mid=item['id']
    n.cfg.rsvp_max_responses=51
    for uid in range(100,152):
        await n.db.claim(item['token'],uid)
        response=await n.db.rsvp(mid,uid,1,1,f'Guest {uid}',n.cfg.rsvp_max_responses)
        assert (response=='limit') == (uid==151)
    rows=await n.db.all('SELECT notice_status FROM q_rsvps WHERE invite_id=? ORDER BY rowid',(mid,))
    assert [x['notice_status'] for x in rows].count('pending')==50
    assert rows[-1]['notice_status']=='suppressed'
    for uid in range(100,151): await n.app.notify_rsvp(mid,uid)
    assert len([m for m in n.sent(1) if 'Taklifga javob' in m['text']])==50
    await n.app.notify_rsvp(mid,150)
    assert len([m for m in n.sent(1) if 'Taklifga javob' in m['text']])==50
    assert isinstance(await n.db.rsvp(mid,100,0,0,'Again',51),dict)
    await n.msg(2,f'/start i_{item["token"]}')
    assert (await api('POST',f'/api/invites/{mid}/rsvp',uid=2,json={'attending':1,'guests':1}))[0]==409
    n.cfg.rsvp_rate_limit=1
    assert (await api('POST',f'/api/invites/{mid}/rsvp',uid=2,json={'attending':1,'guests':1}))[0]==429
    await n.msg(1,'/guests'); assert 'q:guests:1:1' in n.sent(1)[-1]['reply_markup']
    await n.cb(1,f'q:guests:{mid}:1'); assert 'Guest 102' in n.sent(1)[-1]['text']

async def test_legacy_rsvp_migration(tmp_path):
    from invitation_store import InvitationDB
    db=InvitationDB(tmp_path/'legacy.sqlite'); await db.init()
    await db.run("INSERT INTO q_invites(id,sender,receiver,title,created_at) VALUES(1,1,2,'old',?)",(time.time(),))
    await db.run('DROP TABLE q_rsvps')
    await db.run("CREATE TABLE q_rsvps(invite_id INTEGER PRIMARY KEY, attending INTEGER, guests INTEGER, responded_at REAL, receiver_name TEXT, notice_status TEXT)")
    await db.run("INSERT INTO q_rsvps VALUES(1,1,3,123,'Old','pending')")
    await db.init(); await db.init()
    row=await db.one('SELECT * FROM q_rsvps WHERE invite_id=1')
    assert row['telegram_user_id']==2 and row['guests']==3 and row['notice_status']=='pending'
    assert (await db.invite(1))['share_mode']=='single'
