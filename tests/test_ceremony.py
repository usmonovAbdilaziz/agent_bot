import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from test_minimal import n, api
from invitation_store import valid_map_url

FUTURE=(datetime.now(ZoneInfo('Asia/Tashkent')).date()+timedelta(days=365)).strftime('%d.%m.%Y')
PAST=(datetime.now(ZoneInfo('Asia/Tashkent')).date()-timedelta(days=1)).strftime('%d.%m.%Y')

async def start(n):
    await n.cb(1,'q:self')
    flow=await n.db.flow(1); mid=flow['invite_id']
    assert flow['stage']=='type'
    await n.cb(1,f'q:ctype:{mid}:ceremony')
    assert (await n.db.flow(1))['stage']=='c_kind'
    await n.cb(1,f'q:cevent:{mid}:wedding')
    return mid

async def fill_to_map(n,mid):
    await n.msg(1,'Ali & <Vali>')
    await n.msg(1,FUTURE)
    await n.msg(1,'18:30')
    await n.msg(1,'Toshkent, <Bog‘>')

async def finish(n,mid,skip=True,mode="single"):
    if skip:
        await n.cb(1,f'q:cskip:{mid}')
        await n.cb(1,f'q:cskip:{mid}')
    else:
        await n.msg(1,'https://maps.google.com/?q=Tashkent')
        await n.msg(1,'Kutib olish\nMarosim')
    await n.msg(1,'<Xush kelibsiz> & do‘stlar')
    await n.cb(1,f'q:cskip:{mid}')
    assert any(button['text']=='O‘tkazib yuborish' for row in json.loads(n.sent(1)[-1]['reply_markup'])['inline_keyboard'] for button in row)
    await n.cb(1,f'q:clayout:{mid}:top')
    await n.cb(1,f'q:cdesign:{mid}:ceremony_elegant')
    assert (await n.db.flow(1))['stage']=='c_share'
    assert 'manzil va vaqtni' in n.sent(1)[-1]['text']
    await n.cb(1,f'q:cshare:{mid}:{mode}')
    assert (await n.db.flow(1))['stage']=='c_preview'

@pytest.mark.parametrize('skip',[False,True])
async def test_ceremony_complete_preview_publish_and_readonly(n,api,skip):
    mid=await start(n)
    await fill_to_map(n,mid)
    await finish(n,mid,skip)
    item=await n.db.invite(mid); details=json.loads(item['details'])
    assert details['event_kind']=='wedding' and details['date']==FUTURE and details['time']=='18:30'
    assert details['address']=='Toshkent, <Bog‘>' and details['layout']['text_position']=='top'
    assert details['program']==([] if skip else ['Kutib olish','Marosim'])
    assert details['map_url']==('' if skip else 'https://maps.google.com/?q=Tashkent')
    preview=n.sent(1)[-1]['text']
    assert 'Ali &amp; &lt;Vali&gt;' in preview and '&lt;Xush kelibsiz&gt;' in preview
    assert all(value in preview for value in ('To‘y',FUTURE,'18:30','Manzil','Xarita','Dastur','Dizayn'))
    await n.cb(1,f'q:confirm:{mid}')
    item=await n.db.invite(mid); assert item['status']=='ready' and item['token']
    await n.msg(2,f'/start i_{item["token"]}')
    status,data=await api('GET',f'/api/invites/{mid}',2)
    assert status==200 and data['type']=='ceremony' and data['details']==details
    assert (await api('POST',f'/api/invites/{mid}/accept',2))[0]==409
    assert (await n.db.invite(mid))['status']=='ready'

async def test_validation_back_cancel_and_skip(n):
    mid=await start(n)
    await n.msg(1,'Test')
    for bad in [PAST,'31.02.2035','2035-01-01','1.01.2035']:
        await n.msg(1,bad); assert (await n.db.flow(1))['stage']=='c_date'
    await n.msg(1,FUTURE)
    for bad in ('24:00','9:00','09:60','abc'):
        await n.msg(1,bad); assert (await n.db.flow(1))['stage']=='c_time'
    await n.cb(1,f'q:cback:{mid}'); assert (await n.db.flow(1))['stage']=='c_date'
    await n.msg(1,FUTURE); await n.msg(1,'09:20'); await n.msg(1,'Manzil')
    for bad in ('http://maps.google.com/x','https://evil.example/maps.google.com','https://maps.google.com.evil.example/x','https://user@maps.google.com/x','https://yandex.ru/mail'):
        await n.msg(1,bad); assert (await n.db.flow(1))['stage']=='c_map'
    await n.cb(1,f'q:cskip:{mid}'); assert (await n.db.flow(1))['stage']=='c_program'
    await n.cb(1,f'q:cback:{mid}'); assert (await n.db.flow(1))['stage']=='c_map'
    await n.cb(1,f'q:ccancel:{mid}'); assert await n.db.invite(mid) is None
    assert await n.db.flow(1) is None

@pytest.mark.parametrize('updates',[{'event_kind':'invalid'},{'date':'31.02.2035'},{'date':'01.01.2000'}, {'time':'24:00'}, {'address':'x'*301}, {'map_url':'https://maps.google.com.evil.example/'}, {'program':['x'*201]}, {'note':'x'*501}, {'layout':{'text_position':'left'}}])
async def test_invalid_details_rejected_by_write_and_publish(n,updates):
    mid=await start(n)
    await fill_to_map(n,mid)
    await finish(n,mid)
    before=(await n.db.invite(mid))['details']
    assert not await n.db.update_ceremony_details(mid,1,updates)
    assert (await n.db.invite(mid))['details']==before
    corrupted=json.loads(before); corrupted.update(updates)
    await n.db.run('UPDATE q_invites SET details=? WHERE id=?',(json.dumps(corrupted),mid))
    assert await n.db.publish(mid,1,3600) is None

@pytest.mark.parametrize('url,expected',[
 ('https://maps.google.com/?q=x',True),('https://maps.app.goo.gl/abc',True),('https://yandex.uz/maps/a',True),('https://2gis.uz/tashkent',True),('https://2gis.uz.evil.com/',False),('https://maps.google.com:444/',False),('https://evil@maps.google.com/',False)])
def test_map_host_allowlist(url,expected):
    assert valid_map_url(url)==expected
