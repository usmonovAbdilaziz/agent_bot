"""Current product: real Dispatcher + local HTTP Bot API + authenticated HTTP app."""
import asyncio
import json
import time
import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web
from aiogram.types import Update
from invitation_store import InvitationDB
from main import App, dispatcher, MAX_MEDIA
from webapp import create_web_app
from test_webapp import signed

@pytest_asyncio.fixture
async def n(h):
    h.db=InvitationDB(h.db.path)
    await h.db.init()
    h.cfg.webapp_url='https://mini.example.test'
    h.cfg.enable_ceremony=True
    h.cfg.rsvp_rate_limit=30
    h.cfg.rsvp_max_responses=500
    h.app=App(h.bot,h.db,h.cfg,'test_agent_bot')
    h.dp=dispatcher(h.app)
    await h.msg(1,'/start')
    await h.msg(1,contact={'phone_number':'+998937777453','first_name':'Admin','user_id':1})
    return h

@pytest_asyncio.fixture
async def api(n):
    runner=web.AppRunner(create_web_app(n.app))
    await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0); await site.start()
    url=f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
    async with aiohttp.ClientSession() as client:
        async def request(method,path,uid=2,auth=None,**kwargs):
            async with client.request(method,url+path,headers={'X-Telegram-Init-Data':signed(n.cfg.token,uid) if auth is None else auth},**kwargs) as response:
                return response.status, await response.json() if response.content_type=='application/json' else await response.read()
        yield request
    await runner.cleanup()

async def draft(n, media=False, uid=1):
    await n.cb(uid,'q:self' if uid==1 else 'q:new')
    flow=await n.db.flow(uid); mid=flow['invite_id']
    if flow['stage']=='type': await n.cb(uid,f'q:ctype:{mid}:fun')
    if media: await n.msg(uid,photo=True)
    else: await n.cb(uid,f'q:skip:{mid}')
    await n.cb(uid,f'q:name:{mid}')
    await n.msg(uid,'Siz bilan uchrashsam bo‘ladimi?')
    await n.cb(uid,f'q:layout:{mid}:bottom')
    return mid

async def ready(n,media=False):
    mid=await draft(n,media)
    await n.cb(1,f'q:confirm:{mid}')
    return await n.db.invite(mid)

async def test_design_selection_persists_and_is_returned_to_receiver(n,api):
    mid=await draft(n)
    assert (await n.db.invite(mid))['design']=='classic'
    await n.cb(1,f'q:design:{mid}')
    await n.cb(1,f'q:style:{mid}:romantic')
    assert (await n.db.invite(mid))['design']=='romantic'
    await n.cb(1,f'q:confirm:{mid}')
    item=await n.db.invite(mid)
    await n.msg(2,f'/start i_{item["token"]}')
    status,data=await api('GET',f'/api/invites/{mid}',2)
    assert status==200 and data['design']=='romantic'
    await n.cb(1,f'q:style:{mid}:elegant')
    assert (await n.db.invite(mid))['design']=='romantic'

async def test_fun_registry_options_are_available_in_two_column_rows(n):
    from designs import DESIGNS
    mid=await draft(n)
    await n.cb(1,f'q:design:{mid}')
    rows=json.loads(n.sent(1)[-1]['reply_markup'])['inline_keyboard']
    assert [len(row) for row in rows]==[2,2,2,1]
    assert {button['callback_data'].split(':')[-1] for row in rows for button in row}=={key for key, value in DESIGNS.items() if value['type']=='fun'}
    for design in ('birthday','neon','newyear'):
        await n.cb(1,f'q:style:{mid}:{design}')
        assert (await n.db.invite(mid))['design']==design

async def video(n,duration=60,size=1024,note=False):
    n.update_id+=1
    v={'file_id':'video_id','file_unique_id':'video_unique','duration':duration,'file_size':size}
    v.update({'length':200} if note else {'width':200,'height':200,'mime_type':'video/mp4'})
    payload={'message_id':n.update_id,'date':int(time.time()),'chat':{'id':1,'type':'private'},'from':n.user(1),'video_note' if note else 'video':v}
    await n.dp.feed_update(n.bot,Update.model_validate({'update_id':n.update_id,'message':payload}))

async def test_admin_has_two_choices_and_only_admin_assigns(n):
    menu=json.loads(n.sent(1)[-1]['reply_markup'])['inline_keyboard']
    assert [b['text'] for row in menu for b in row]==['O‘zim','Boshqa raqam','Sender so‘rovlari','Takliflar']
    await n.msg(2,'/start'); await n.cb(2,'q:self'); await n.cb(2,'q:phone')
    assert not await n.db.all('SELECT * FROM q_invites')
    assert not await n.db.flow(2)

async def test_phone_sender_requires_own_verified_contact(n):
    await n.cb(1,'q:phone'); await n.msg(1,'+998901234567')
    await n.msg(2,'/start')
    await n.msg(2,contact={'phone_number':'+998901234567','first_name':'Fake','user_id':3})
    assert not await n.app.is_sender(2)
    await n.msg(2,contact={'phone_number':'+998901234567','first_name':'Own','user_id':2})
    assert await n.app.is_sender(2)
    assert (await n.db.flow(2))['stage']=='type'
    assert '998901234567' not in str(await n.db.all('SELECT * FROM q_profiles'))
    mid=await draft(n,uid=2)
    await n.cb(2,f'q:confirm:{mid}')
    assert (await n.db.invite(mid))['token']

async def test_verified_existing_phone_can_be_selected(n):
    await n.msg(2,'/start')
    await n.msg(2,contact={'phone_number':'+998901234567','first_name':'Own','user_id':2})
    await n.cb(1,'q:phone'); await n.msg(1,'+998901234567')
    assert await n.app.is_sender(2)
    assert (await n.db.flow(2))['stage']=='type'

async def test_full_name_optional_media_edit_and_one_confirmation(n):
    original=n.user
    n.user=lambda uid:dict(original(uid),last_name='Familiya')
    mid=await draft(n)
    item=await n.db.invite(mid)
    assert item['title']=='Ism <1> Familiya' and item['media_kind']=='none'
    assert not item['token']
    await n.cb(1,f'q:edit:{mid}')
    await n.cb(1,f'q:skip:{mid}')
    await n.msg(1,'Yangi ism')
    await n.msg(1,'<script>Matn & izoh</script>')
    await n.cb(1,f'q:layout:{mid}:bottom')
    await n.cb(1,f'q:confirm:{mid}')
    token=(await n.db.invite(mid))['token']
    link_count=len(n.sent(1))
    await n.cb(1,f'q:confirm:{mid}')
    assert (await n.db.invite(mid))['token']==token
    assert len(n.sent(1))==link_count
    assert len(await n.db.all('SELECT * FROM q_invites'))==1
    assert not await n.db.all('SELECT * FROM sessions')
    assert any('&lt;script&gt;' in x['text'] for x in n.sent(1))

async def test_stale_buttons_duplicate_updates_and_restart(n):
    await n.cb(1,'q:self'); mid=(await n.db.flow(1))['invite_id']; await n.cb(1,f'q:ctype:{mid}:fun')
    await n.cb(1,f'q:skip:{mid}')
    await n.msg(1,'Asl ism',message_id=7777)
    await n.msg(1,'Asl ism',message_id=7777)
    assert (await n.db.flow(1))['stage']=='description'
    await n.cb(1,f'q:skip:{mid}')
    assert (await n.db.flow(1))['stage']=='description'
    n.app=App(n.bot,n.db,n.cfg,'test_agent_bot'); n.dp=dispatcher(n.app)
    await n.msg(1,'/start')
    assert 'Tavsif yuboring' in n.sent(1)[-1]['text']
    await n.msg(1,'Davom etgan tavsif')
    await n.cb(1,f'q:layout:{mid}:bottom')
    await n.cb(1,f'q:confirm:{mid}')
    assert (await n.db.invite(mid))['status']=='ready'

@pytest.mark.parametrize('note',[False,True])
async def test_video_boundary_and_preview(n,note):
    await n.cb(1,'q:self'); mid=(await n.db.flow(1))['invite_id']; await n.cb(1,f'q:ctype:{mid}:fun')
    await video(n,61,note=note)
    assert (await n.db.flow(1))['stage']=='media'
    await video(n,60,MAX_MEDIA+1,note=note)
    assert (await n.db.flow(1))['stage']=='media'
    await video(n,60,MAX_MEDIA,note=note)
    assert (await n.db.flow(1))['stage']=='title'
    await n.cb(1,f'q:name:{mid}'); await n.msg(1,'Video taklif')
    await n.cb(1,f'q:layout:{mid}:bottom')
    assert n.sent(1,'sendVideoNote' if note else 'sendVideo')
    assert (await n.db.invite(mid))['media_kind']==('video_note' if note else 'video')

async def test_text_bounds_and_unauthorized_confirm(n):
    await n.cb(1,'q:self'); mid=(await n.db.flow(1))['invite_id']; await n.cb(1,f'q:ctype:{mid}:fun')
    await n.cb(1,f'q:skip:{mid}')
    await n.msg(1,'X'*121)
    assert (await n.db.flow(1))['stage']=='title'
    await n.cb(1,f'q:name:{mid}'); await n.msg(1,' '); await n.msg(1,'X'*2001)
    assert (await n.db.flow(1))['stage']=='description'
    await n.msg(1,'Matn')
    await n.cb(2,f'q:confirm:{mid}')
    assert (await n.db.invite(mid))['status']=='draft'

async def test_claim_is_atomic_and_own_link_does_not_claim(n):
    item=await ready(n)
    assert await n.db.claim(item['token'],1) is None
    results=await asyncio.gather(n.db.claim(item['token'],2),n.db.claim(item['token'],3))
    assert sum(x is not None for x in results)==1
    owner=(await n.db.invite(item['id']))['receiver']
    assert await n.db.claim(item['token'],owner)==item['id']

async def test_receiver_completion_is_per_invitation_and_start_offers_sender(n,api):
    item=await ready(n)
    await n.msg(2,f'/start i_{item["token"]}')
    buttons=json.loads(n.sent(2)[-1]['reply_markup'])['inline_keyboard']
    assert len(buttons)==1 and len(buttons[0])==1 and 'web_app' in buttons[0][0]
    assert (await api('GET',f'/api/invites/{item["id"]}',2))[0]==200
    for _ in range(2):
        assert await api('POST',f'/api/invites/{item["id"]}/accept',2)==(200,{'accepted':True})
    before=len(n.calls)
    await n.msg(2,'Salom')
    assert len(n.calls)==before
    assert not await n.db.all('SELECT * FROM sessions')
    n.app=App(n.bot,n.db,n.cfg,'test_agent_bot'); n.dp=dispatcher(n.app)
    await n.msg(2,'/start')
    assert 'ro‘yxatdan' in n.sent(2)[-1]['text']
    await n.msg(2,f'/start i_{item["token"]}')
    assert 'ishlatilgan' in n.sent(2)[-1]['text']
    newer=await ready(n)
    await n.msg(2,f'/start i_{newer["token"]}')
    assert 'Taklifni ochish' in n.sent(2)[-1]['reply_markup']
    assert (await n.db.invite(newer['id']))['receiver']==2
    assert (await api('POST',f'/api/invites/{newer["id"]}/accept'))[0]==200

async def test_auth_permissions_photo_privacy_and_expiry(n,api):
    item=await ready(n,True); mid=item['id']
    for auth in ('','hash=bad',signed(n.cfg.token,2,3700),signed(n.cfg.token,2,-120)):
        assert (await api('GET',f'/api/invites/{mid}',auth=auth))[0]==401
    assert (await api('GET',f'/api/invites/{mid}',3))[0]==404
    assert (await api('POST',f'/api/invites/{mid}/accept',1))[0]==403
    assert (await api('GET',f'/api/invites/{mid}/media',3))[0]==404
    await n.msg(2,f'/start i_{item["token"]}')
    status,data=await api('GET',f'/api/invites/{mid}',2)
    assert status==200 and not data['preview'] and 'file_id' not in data and 'token' not in data
    assert await api('GET',f'/api/invites/{mid}/media',2)==(200,b'\xff\xd8\xff\xd9')
    await n.db.run('UPDATE q_invites SET expires_at=0 WHERE id=?',(mid,))
    assert (await api('POST',f'/api/invites/{mid}/accept',2))[0]==409
    assert not await n.db.one('SELECT * FROM q_done WHERE uid=2')

async def test_photo_uses_smaller_variant_and_cache_still_enforces_permissions(n,api):
    await n.cb(1,'q:self')
    mid=(await n.db.flow(1))['invite_id']
    await n.cb(1,f'q:ctype:{mid}:fun')
    n.update_id+=1
    photos=[{'file_id':name,'file_unique_id':name,'width':size,'height':size,'file_size':100}
            for name,size in [('small',320),('medium',800),('large',1280)]]
    payload={'message_id':n.update_id,'date':int(time.time()),'chat':{'id':1,'type':'private'},
             'from':n.user(1),'photo':photos}
    await n.dp.feed_update(n.bot,Update.model_validate({'update_id':n.update_id,'message':payload}))
    assert (await n.db.invite(mid))['file_id']=='medium'
    await n.cb(1,f'q:name:{mid}')
    await n.msg(1,'Taklif matni')
    await n.cb(1,f'q:layout:{mid}:bottom')
    await n.cb(1,f'q:confirm:{mid}')
    item=await n.db.invite(mid)
    await n.msg(2,f'/start i_{item["token"]}')
    before=sum(method=='getFile' for method,_ in n.calls)
    assert (await api('GET',f'/api/invites/{mid}/media',2))[0]==200
    assert (await api('GET',f'/api/invites/{mid}/media',2))[0]==200
    assert sum(method=='getFile' for method,_ in n.calls)==before+1
    assert (await api('GET',f'/api/invites/{mid}/media',3))[0]==404
    await n.db.run('UPDATE q_invites SET expires_at=0 WHERE id=?',(mid,))
    assert (await api('GET',f'/api/invites/{mid}/media',2))[0]==409

@pytest.mark.parametrize('sizes,expected', [([320,800,1280],800), ([320],320), ([1280],1280), ([320,600],600)])
def test_photo_width_selection(sizes, expected, caplog):
    from types import SimpleNamespace
    from main import select_photo
    photos=[SimpleNamespace(width=size,height=100,file_id='private') for size in sizes]
    assert select_photo(photos).width==expected
    assert 'private' not in caplog.text

async def test_cache_cleared_after_accept(n,api):
    item=await ready(n,True); mid=item['id']
    await n.msg(2,f'/start i_{item["token"]}')
    assert (await api('GET',f'/api/invites/{mid}/media',2))[0]==200
    assert n.app.photo_cache.get(item['file_id']) is not None
    assert (await api('POST',f'/api/invites/{mid}/accept',2))[0]==200
    assert n.app.photo_cache.get(item['file_id']) is None

async def test_cache_cleared_after_draft_cancel(n,api):
    mid=await draft(n,True)
    item=await n.db.invite(mid)
    assert (await api('GET',f'/api/invites/{mid}/media',1))[0]==200
    assert n.app.photo_cache.get(item['file_id']) is not None
    await n.msg(1,'/cancel')
    assert await n.db.invite(mid) is None
    assert n.app.photo_cache.get(item['file_id']) is None

async def test_photo_cache_expiry_and_size_bounds(monkeypatch):
    import webapp
    clock=[1000]
    monkeypatch.setattr(webapp.time,'monotonic',lambda:clock[0])
    cache=webapp.PhotoCache()
    cache.put('first',b'photo')
    assert cache.get('first')==b'photo'
    clock[0]+=webapp.PHOTO_CACHE_TTL
    assert cache.get('first') is None and cache.size==0
    cache.put('large',b'x'*(webapp.PHOTO_CACHE_ITEM_BYTES+1))
    assert cache.get('large') is None
    for index in range(webapp.PHOTO_CACHE_ENTRIES+1):
        cache.put(str(index),b'x')
    assert len(cache.items)==webapp.PHOTO_CACHE_ENTRIES and cache.get('0') is None

async def test_unavailable_telegram_and_retry_keep_one_link(n):
    mid=await draft(n)
    n.fail[('sendMessage',1)]=500
    await n.cb(1,f'q:confirm:{mid}')
    item=await n.db.invite(mid)
    assert item['status']=='ready' and item['token']
    await n.msg(1,'/start')
    assert (await n.db.invite(mid))['token']==item['token']
    assert item['token'] in n.sent(1)[-1]['text']

async def test_old_actions_and_routes_are_disabled(n,api):
    await n.cb(1,'admin'); await n.cb(1,'moderation'); await n.cb(1,'compose_link')
    assert not await n.db.all('SELECT * FROM q_invites')
    assert (await api('GET','/api/messages',1))[0]==404
    assert (await api('GET','/healthz',auth=''))==(503,{'ready':False})
    n.app.ready=True
    assert (await api('GET','/healthz',auth=''))==(200,{'ready':True})

async def test_no_media_endpoint_and_pending_resume(n,api):
    item=await ready(n)
    await n.msg(2,f'/start i_{item["token"]}')
    await n.msg(2,'/start')
    assert 'ro‘yxatdan' in n.sent(2)[-1]['text']
    await n.msg(2,f'/start i_{item["token"]}')
    assert 'Taklifni ochish' in n.sent(2)[-1]['reply_markup']
    assert (await api('GET',f'/api/invites/{item["id"]}/media',2))[0]==404

@pytest.mark.parametrize('count',[0,7])
async def test_accept_notifies_sender_once_and_freezes_count(n,api,count):
    item=await ready(n)
    await n.msg(2,f'/start i_{item["token"]}')
    path=f'/api/invites/{item["id"]}/accept'
    before=len(n.sent(1))
    results=await asyncio.gather(*(api('POST',path,json={'no_attempts':count}) for _ in range(3)))
    assert all(result==(200,{'accepted':True}) for result in results)
    assert len(n.sent(1))==before+1
    assert f'{count} marta' in n.sent(1)[-1]['text']
    assert '“Ha”ni bosdi' in n.sent(1)[-1]['text']
    assert (await n.db.invite(item['id']))['no_attempts']==count
    await api('POST',path,json={'no_attempts':99})
    restarted=App(n.bot,n.db,n.cfg,'test_agent_bot')
    await restarted.notify_acceptance(item['id'])
    assert len(n.sent(1))==before+1
    assert (await n.db.invite(item['id']))['no_attempts']==count

@pytest.mark.parametrize('body',[{'no_attempts':-1},{'no_attempts':True},{'no_attempts':'7'},
    {'no_attempts':1.5},{'no_attempts':1000001},[],None])
async def test_invalid_attempt_count_does_not_accept(n,api,body):
    item=await ready(n)
    await n.msg(2,f'/start i_{item["token"]}')
    result=await api('POST',f'/api/invites/{item["id"]}/accept',data=json.dumps(body))
    assert result[0]==400
    assert (await n.db.invite(item['id']))['status']=='ready'
    assert not await n.db.all('SELECT * FROM q_accept_notices')

async def test_notification_recovers_after_telegram_failure_and_restart(n,api):
    item=await ready(n)
    await n.msg(2,f'/start i_{item["token"]}')
    n.fail[('sendMessage',1)]=500
    assert await api('POST',f'/api/invites/{item["id"]}/accept',json={'no_attempts':12})==(200,{'accepted':True})
    assert (await n.db.one('SELECT * FROM q_accept_notices'))['status']=='pending'
    restarted=App(n.bot,n.db,n.cfg,'test_agent_bot')
    await restarted.notify_acceptance(item['id'])
    assert (await n.db.one('SELECT * FROM q_accept_notices'))['status']=='sent'
    assert '12 marta' in n.sent(1)[-1]['text']

async def test_blocked_sender_does_not_break_acceptance(n,api):
    item=await ready(n)
    await n.msg(2,f'/start i_{item["token"]}')
    n.fail[('sendMessage',1)]=403
    assert await api('POST',f'/api/invites/{item["id"]}/accept')==(200,{'accepted':True})
    assert (await n.db.one('SELECT * FROM q_accept_notices'))['status']=='failed'

async def test_notification_goes_to_selected_sender_not_admin(n,api):
    await n.msg(2,'/start')
    await n.db.run('INSERT INTO q_senders VALUES(2)')
    mid=await draft(n,uid=2)
    await n.cb(2,f'q:confirm:{mid}')
    item=await n.db.invite(mid)
    await n.msg(3,f'/start i_{item["token"]}')
    before_admin, before_sender=len(n.sent(1)),len(n.sent(2))
    assert (await api('POST',f'/api/invites/{mid}/accept',uid=3,json={'no_attempts':4}))[0]==200
    assert len(n.sent(1))==before_admin
    assert len(n.sent(2))==before_sender+1
    assert '4 marta' in n.sent(2)[-1]['text']

async def test_schema_upgrade_preserves_old_acceptance_without_backfill(n):
    item=await ready(n)
    await n.db.claim(item['token'],2)
    await n.db.accept(item['id'],2)
    await n.db.run('DROP TABLE q_accept_notices')
    await n.db.run('ALTER TABLE q_invites DROP COLUMN no_attempts')
    await n.db.init()
    await n.db.init()
    restored=await n.db.invite(item['id'])
    assert restored['status']=='accepted' and restored['no_attempts']==0
    assert await n.db.accept(item['id'],2,10)
    assert not await n.db.all('SELECT * FROM q_accept_notices')

async def test_design_registry_migration_is_idempotent(n, api):
    item = await ready(n)
    await n.db.run('ALTER TABLE q_invites DROP COLUMN type')
    await n.db.run('ALTER TABLE q_invites DROP COLUMN details')
    await n.db.init()
    await n.db.init()
    migrated = await n.db.invite(item['id'])
    assert migrated['type'] == 'fun' and json.loads(migrated['details']) == {}
    await n.msg(2, f'/start i_{item["token"]}')
    status, data = await api('GET', f'/api/invites/{item["id"]}', 2)
    assert status == 200 and data['type'] == 'fun' and data['details']['layout']['text_position'] == 'bottom'
    status, data = await api('POST', f'/api/invites/{item["id"]}/accept', 2, json={})
    assert status == 200 and data['accepted']

async def test_invalid_design_and_type_are_rejected(n):
    mid = await draft(n)
    await n.cb(1, f'q:style:{mid}:unknown')
    assert (await n.db.invite(mid))['design'] == 'classic'
    await n.db.run("UPDATE q_invites SET type='ceremony' WHERE id=?", (mid,))
    await n.cb(1, f'q:style:{mid}:romantic')
    assert (await n.db.invite(mid))['design'] == 'classic'
    assert await n.db.publish(mid, 1, n.cfg.ttl) is None
    await n.db.run("UPDATE q_invites SET type='fun', design='unknown' WHERE id=?", (mid,))
    assert await n.db.publish(mid, 1, n.cfg.ttl) is None


@pytest.mark.parametrize('legacy_design', ['', 'old-design'])
async def test_unknown_legacy_design_opens_as_classic_and_can_be_accepted(n, api, legacy_design):
    item = await ready(n)
    await n.db.run('UPDATE q_invites SET design=? WHERE id=?', (legacy_design, item['id']))
    await n.msg(2, f'/start i_{item["token"]}')
    status, data = await api('GET', f'/api/invites/{item["id"]}', 2)
    assert status == 200 and data['design'] == 'classic'
    status, data = await api('POST', f'/api/invites/{item["id"]}/accept', 2, json={})
    assert status == 200 and data['accepted']
    assert (await n.db.invite(item['id']))['design'] == legacy_design


@pytest.mark.parametrize('position', ['top','center','bottom'])
async def test_layout_selection_and_api(n, api, position):
    await n.cb(1,'q:self'); mid=(await n.db.flow(1))['invite_id']; await n.cb(1,f'q:ctype:{mid}:fun')
    await n.cb(1,f'q:skip:{mid}'); await n.cb(1,f'q:name:{mid}')
    await n.msg(1,'Matn')
    assert (await n.db.flow(1))['stage']=='layout'
    await n.cb(1,f'q:layout:{mid}:invalid')
    assert (await n.db.flow(1))['stage']=='layout'
    await n.cb(1,f'q:layout:{mid}:{position}')
    assert (await n.db.flow(1))['stage']=='preview'
    status, data=await api('GET',f'/api/invites/{mid}',1)
    assert status==200 and data['details']['layout']['text_position']==position
    await n.cb(1,f'q:confirm:{mid}')
    assert (await n.db.invite(mid))['status']=='ready'

@pytest.mark.parametrize('bad', ['{"layout":{"text_position":"left"}}','{"layout":[]}', '[]', 'broken'])
async def test_invalid_layout_cannot_be_published(n, bad):
    mid=await draft(n)
    await n.db.run('UPDATE q_invites SET details=? WHERE id=?',(bad,mid))
    assert await n.db.publish(mid,1,n.cfg.ttl) is None
