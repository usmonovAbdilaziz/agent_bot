import asyncio
import pytest
from test_minimal import n, api, ready
from test_ceremony import start, fill_to_map, finish

async def ceremony(n):
    mid=await start(n); await fill_to_map(n,mid); await finish(n,mid)
    await n.cb(1,f'q:confirm:{mid}'); item=await n.db.invite(mid)
    await n.msg(2,f'/start i_{item["token"]}')
    return mid

@pytest.mark.parametrize('data',[{},None,[],{'attending':True,'guests':1},{'attending':2,'guests':1},{'attending':1,'guests':0},{'attending':1,'guests':11},{'attending':1,'guests':True},{'attending':0,'guests':2},{'attending':0,'guests':-1}])
async def test_rsvp_invalid_values(n,api,data):
    mid=await ceremony(n)
    status,_=await api('POST',f'/api/invites/{mid}/rsvp',2,json=data)
    assert status==400 and not await n.db.one('SELECT * FROM q_rsvps WHERE invite_id=?',(mid,))

async def test_rsvp_auth_and_type(n,api):
    mid=await ceremony(n); path=f'/api/invites/{mid}/rsvp'; body={'attending':1,'guests':1}
    assert (await api('POST',path,auth='',json=body))[0]==401
    assert (await api('POST',path,auth='hash=bad',json=body))[0]==401
    assert (await api('POST',path,uid=3,json=body))[0]==404
    assert (await api('POST',path,uid=1,json=body))[0]==403
    fun=await ready(n)
    await n.msg(3,f'/start i_{fun["token"]}')
    assert (await api('POST',f'/api/invites/{fun["id"]}/rsvp',uid=3,json=body))[0]==409
    assert not await n.db.all('SELECT * FROM q_rsvps')

async def test_rsvp_atomic_first_result_notification_and_reload(n,api):
    mid=await ceremony(n); path=f'/api/invites/{mid}/rsvp'
    assert (await api('GET',f'/api/invites/{mid}'))[1]['rsvp'] is None
    payloads=[{'attending':1,'guests':3},{'attending':0,'guests':0},{'attending':1,'guests':10}]
    results=await asyncio.gather(*(api('POST',path,json=p) for p in payloads))
    assert all(status==200 for status,_ in results)
    assert len({str(body['rsvp']) for _,body in results})==1
    result=results[0][1]['rsvp']
    assert (await api('GET',f'/api/invites/{mid}'))[1]['rsvp']==result
    notices=[m['text'] for m in n.sent(1) if 'Taklifga javob' in m['text']]
    assert len(notices)==1 and 'Ism2' in notices[0] and 'Ali &amp; &lt;Vali&gt;' in notices[0]
    assert ('Kelaman' if result['attending'] else 'Kela olmayman') in notices[0]
    assert f"Mehmonlar soni: {result['guests']}" in notices[0]
    await n.db.run('UPDATE q_invites SET expires_at=0 WHERE id=?',(mid,))
    assert (await api('GET',f'/api/invites/{mid}'))[1]['rsvp']==result
    assert (await api('POST',path,json={'attending':1,'guests':1}))[1]['rsvp']==result

@pytest.mark.parametrize('attending,guests,expected',[(0,1,0),(0,0,0),(1,1,1),(1,10,10)])
async def test_rsvp_boundaries_and_decline_normalization(n,api,attending,guests,expected):
    mid=await ceremony(n)
    status,body=await api('POST',f'/api/invites/{mid}/rsvp',json={'attending':attending,'guests':guests})
    assert status==200 and body['rsvp']['guests']==expected

async def test_rsvp_notification_failure_is_durable_and_retry(n,api):
    mid=await ceremony(n)
    n.fail[('sendMessage',1)]=500
    status,body=await api('POST',f'/api/invites/{mid}/rsvp',json={'attending':1,'guests':4})
    assert status==200 and body['rsvp']['guests']==4
    assert (await n.db.one('SELECT * FROM q_rsvps WHERE invite_id=?',(mid,)))['notice_status']=='pending'
    from main import App
    restarted=App(n.bot,n.db,n.cfg,'test_agent_bot')
    await restarted.notify_rsvp(mid)
    assert (await n.db.one('SELECT * FROM q_rsvps WHERE invite_id=?',(mid,)))['notice_status']=='sent'
    assert any('Mehmonlar soni: 4' in m['text'] for m in n.sent(1))

async def test_rsvp_migration_is_idempotent(n):
    await n.db.init(); await n.db.init()
    assert await n.db.one("SELECT name FROM sqlite_master WHERE type='table' AND name='q_rsvps'")

async def test_rsvp_clears_photo_cache(n,api):
    mid=await ceremony(n)
    await n.db.run("UPDATE q_invites SET media_kind='photo',file_id='photo-test' WHERE id=?",(mid,))
    assert (await api('GET',f'/api/invites/{mid}/media'))[0]==200
    assert n.app.photo_cache.get('photo-test') is not None
    assert (await api('POST',f'/api/invites/{mid}/rsvp',json={'attending':0,'guests':0}))[0]==200
    assert n.app.photo_cache.get('photo-test') is None
