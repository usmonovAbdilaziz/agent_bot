import asyncio
import io
import json
from datetime import datetime, timedelta
from PIL import Image
from test_minimal import n, api  # reuse real Dispatcher and signed HTTP fixtures
from wedding import UZ_TZ


async def wedding_draft(n, uid=1):
    await n.cb(uid,'q:choose')
    assert 'Taklif turini tanlang' in n.sent(uid)[-1]['text']
    await n.cb(uid,'q:ceremony')
    assert 'Marosim turini tanlang' in n.sent(uid)[-1]['text']
    await n.cb(uid,'q:banquet')
    assert 'keyingi bosqichda' in n.sent(uid)[-1]['text']
    assert not await n.db.flow(uid)
    await n.cb(uid,'q:ceremony')
    await n.cb(uid,'q:wedding')
    mid=(await n.db.flow(uid))['invite_id']
    await n.msg(uid,'Farrux')
    await n.msg(uid,'Nasiba')
    await n.msg(uid,'not a date')
    assert (await n.db.flow(uid))['stage']=='wedding_date'
    date=(datetime.now(UZ_TZ)+timedelta(days=20)).strftime('%d.%m.%Y')
    await n.msg(uid,date)
    await n.msg(uid,'25:88')
    assert (await n.db.flow(uid))['stage']=='wedding_time'
    await n.msg(uid,'17:00')
    await n.msg(uid,'Qamashi tumani, Shirinabonu to‘yxonasi')
    assert (await n.db.flow(uid))['stage']=='preview'
    return mid


async def test_wedding_shared_link_views_and_access(n,api):
    mid=await wedding_draft(n)
    await n.cb(1,f'q:edit:{mid}')
    await n.cb(1,f'q:wedit:{mid}:groom')
    await n.msg(1,'Farruxbek')
    assert (await n.db.flow(1))['stage']=='preview'
    item=await n.db.invite(mid)
    assert json.loads(item['details'])['groom']=='Farruxbek'
    status,preview=await api('GET',f'/api/invites/{mid}/wedding-image',uid=1)
    assert status==200 and Image.open(io.BytesIO(preview)).size==(720,1280)
    assert not await n.db.all('SELECT * FROM q_wedding_guests')
    await n.cb(1,f'q:confirm:{mid}')
    item=await n.db.invite(mid)
    assert item['type']=='ceremony' and item['token']
    assert (await api('GET',f'/api/invites/{mid}',uid=2))[0]==404
    for uid in (2,3):
        await n.msg(uid,f'/start i_{item["token"]}')
        assert 'Taklifni ochish' in n.sent(uid)[-1]['reply_markup']
        assert (await api('GET',f'/api/invites/{mid}',uid=uid))[0]==200
    assert all(row['viewed_at'] is None for row in await n.db.all('SELECT * FROM q_wedding_guests'))
    responses=await asyncio.gather(*[api('GET',f'/api/invites/{mid}/wedding-image',uid=2) for _ in range(3)])
    assert all(status==200 for status,_ in responses)
    assert (await api('GET',f'/api/invites/{mid}/wedding-image',uid=3))[0]==200
    assert (await api('POST',f'/api/invites/{mid}/accept',uid=2,json={}))[0]==409
    await n.cb(1,f'q:invite:{mid}')
    assert 'Ko‘rganlar: <b>2 kishi</b>' in n.sent(1)[-1]['text']
    assert (await api('GET',f'/api/invites/{mid}/wedding-image',uid=4))[0]==404
    await n.db.run('UPDATE q_invites SET expires_at=1 WHERE id=?',(mid,))
    assert (await api('GET',f'/api/invites/{mid}',uid=2))[0]==409
    await n.msg(4,f'/start i_{item["token"]}')
    assert 'muddati tugagan' in n.sent(4)[-1]['text']


async def test_wedding_sender_can_see_stats_after_credit_spent(n):
    await n.msg(2,'/start')
    await n.db.run('INSERT INTO q_senders(uid) VALUES(2)')
    await n.db.run('INSERT INTO q_sender_credits(uid,remaining) VALUES(2,1)')
    mid=await wedding_draft(n,2)
    await n.cb(2,f'q:confirm:{mid}')
    assert not await n.app.is_sender(2)
    await n.msg(2,'/start')
    assert 'Mening takliflarim' in n.sent(2)[-1]['reply_markup']
    await n.cb(2,f'q:invite:{mid}')
    assert 'Ko‘rganlar: <b>0 kishi</b>' in n.sent(2)[-1]['text']
