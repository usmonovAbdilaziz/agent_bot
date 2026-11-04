"""Mini App haqiqiy HTTP: Telegram imzosi, ruxsat, metadata va rozilik."""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import aiohttp
import pytest_asyncio
from aiohttp import web

from legacy_webapp import create_web_app


def signed(token, uid, age=0):
    data = {'auth_date':str(int(time.time()-age)), 'user':json.dumps({'id':uid,'first_name':f'Ism{uid}'},separators=(',',':'))}
    check = '\n'.join(f'{k}={v}' for k,v in sorted(data.items()))
    key = hmac.new(b'WebAppData',token.encode(),hashlib.sha256).digest()
    data['hash'] = hmac.new(key,check.encode(),hashlib.sha256).hexdigest()
    return urlencode(data)


@pytest_asyncio.fixture
async def browser_api(h):
    runner = web.AppRunner(create_web_app(h.app))
    await runner.setup()
    site = web.TCPSite(runner,'127.0.0.1',0)
    await site.start()
    url = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
    async with aiohttp.ClientSession() as client:
        async def request(method, path, uid=2, auth=None, **kwargs):
            headers = {'X-Telegram-Init-Data':signed(h.cfg.token,uid) if auth is None else auth}
            async with client.request(method,url+path,headers=headers,**kwargs) as response:
                payload = await response.json() if response.content_type=='application/json' else await response.read()
                return response.status, payload
        yield request
    await runner.cleanup()


async def test_title_description_required_and_restart(h):
    await h.prepare()
    await h.msg(2,photo=True)
    await h.cb(2,'target:1:0')
    await h.cb(2,'confirm:1')
    assert not await h.db.one('SELECT * FROM links')
    await h.msg(2,' ')
    assert (await h.db.one('SELECT * FROM message_inputs'))['field']=='title'
    await h.msg(2,'A'*121)
    assert (await h.db.one('SELECT * FROM messages'))['title']==''
    await h.msg(2,'<b>Sarlavha & nom</b>')
    from legacy_bot import App, dispatcher
    h.app = App(h.bot,h.db,h.cfg,'test_agent_bot')
    h.dp = dispatcher(h.app)
    await h.msg(2,'<script>Tavsif</script>')
    await h.cb(2,'confirm:1')
    assert await h.db.one('SELECT * FROM links')
    assert any('&lt;script&gt;' in d['text'] for d in h.sent(2))
    assert not await h.db.one('SELECT * FROM message_inputs')


async def test_health_only_ready_after_bot_startup(h,browser_api):
    status,data=await browser_api('GET','/healthz',auth='')
    assert status==503 and data=={'ready':False}
    h.app.ready=True
    status,data=await browser_api('GET','/healthz',auth='')
    assert status==200 and data=={'ready':True}


async def test_mini_auth_rejects_forged_expired_and_stopped(h,browser_api):
    await h.prepare()
    for auth in ('', 'hash=bad',signed(h.cfg.token,2,age=3700),signed(h.cfg.token,2,age=-120)):
        status,_ = await browser_api('GET','/api/me',auth=auth)
        assert status==401
    status,data = await browser_api('GET','/api/me')
    assert status==200 and data['name']=='Ism2'
    await h.msg(2,'/stop')
    status,_ = await browser_api('GET','/api/me')
    assert status==403
    assert (await h.db.one('SELECT active FROM users WHERE tg_id=2'))['active']==0


async def test_mini_metadata_owner_validation_and_submit(h,browser_api):
    await h.prepare(True)
    await h.msg(2,photo=True)
    status,_ = await browser_api('PATCH','/api/messages/1',uid=3,json={'title':'N','description':'D'})
    assert status==404
    status,_ = await browser_api('PATCH','/api/messages/1',json={'title':'','description':'D'})
    assert status==400
    status,data = await browser_api('PATCH','/api/messages/1',json={'title':'Nomi','description':'Tavsifi'})
    assert status==200 and data['title']=='Nomi'
    status,_ = await browser_api('POST','/api/messages/1/submit',json={'confirmed':False})
    assert status==400
    status,data = await browser_api('POST','/api/messages/1/submit',json={'confirmed':True})
    assert status==200 and data['status']=='pending'
    assert not await h.db.one('SELECT * FROM links')
    await h.cb(1,'approve:1')
    status,data = await browser_api('GET','/api/messages/1')
    assert status==200 and '?start=i_' in data['link']
    await browser_api('POST','/api/messages/1/submit',json={'confirmed':True})
    assert len(await h.db.all('SELECT * FROM links'))==1


async def test_mini_photo_preview_is_private_and_accept_is_idempotent(h,browser_api):
    await h.prepare()
    mid = await h.draft(target=3)
    status,photo = await browser_api('GET',f'/api/messages/{mid}/photo',uid=3)
    assert status==200 and photo==b'\xff\xd8\xff\xd9'
    assert not await h.db.active_sessions(2)
    assert (await h.db.one('SELECT status FROM messages WHERE id=?',(mid,)))['status']=='approved'
    assert not h.sent(3,'sendPhoto')
    status,_ = await browser_api('GET',f'/api/messages/{mid}/photo',uid=4)
    assert status==404
    status,_ = await browser_api('POST',f'/api/messages/{mid}/accept',uid=4)
    assert status==404
    before = len(h.sent(3,'sendPhoto'))
    status,data = await browser_api('POST',f'/api/messages/{mid}/accept',uid=3)
    assert status==200 and data['status']=='delivered' and data['can_view']
    await browser_api('POST',f'/api/messages/{mid}/accept',uid=3)
    assert len(await h.db.active_sessions(2))==1
    assert len(h.sent(3,'sendPhoto'))==before  # Rasm chatga qayta yuborilmaydi.
    assert not await h.db.one('SELECT * FROM session_notices WHERE notice_msg_id IS NULL')
    assert 'file_id' not in data and h.cfg.token not in str(data)


async def test_mini_decline_blocks_and_cannot_accept(h,browser_api):
    await h.prepare()
    mid=await h.draft(target=3)
    status,_=await browser_api('POST',f'/api/messages/{mid}/decline',uid=3)
    assert status==200
    assert not await h.db.available(2,3)
    status,_=await browser_api('POST',f'/api/messages/{mid}/accept',uid=3)
    assert status==409
    assert not await h.db.active_sessions(2)


async def test_mini_upload_keeps_file_id_and_requires_fields(h,browser_api):
    await h.prepare()
    def form(title='Sarlavha', description='Tavsif', photo=b'\xff\xd8\xff\xd9'):
        data=aiohttp.FormData()
        data.add_field('title',title)
        data.add_field('description',description)
        data.add_field('photo',photo,filename='photo.jpg',content_type='image/jpeg')
        return data
    status,_=await browser_api('POST','/api/messages',data=form(title=''))
    assert status==400 and not h.sent(2,'sendPhoto')
    status,_=await browser_api('POST','/api/messages',data=form(photo=b'<svg>bad</svg>'))
    assert status==400 and not h.sent(2,'sendPhoto')
    status,data=await browser_api('POST','/api/messages',data=form())
    assert status==201 and data['status']=='draft' and data['title']=='Sarlavha'
    m=await h.db.one('SELECT * FROM messages')
    assert m['file_id']=='telegram_photo_id'
    assert not await h.db.one('SELECT * FROM links')
    assert len(h.sent(2,'sendPhoto'))==1
    assert len(h.sent(2,'deleteMessage'))==1
    await browser_api('POST',f'/api/messages/{m["id"]}/submit',json={'confirmed':True})
    assert await h.db.one('SELECT * FROM links')


async def test_mini_no_chat_photo_and_web_button(h):
    await h.prepare()
    h.cfg.webapp_url='https://example.test'
    mid=await h.draft(target=3)
    consent=h.sent(3)[-1]
    assert 'web_app' in consent['reply_markup']
    before=len(h.sent(3,'sendPhoto'))
    await h.cb(3,f'view:{mid}')
    assert len(h.sent(3,'sendPhoto'))==before
    assert not await h.db.active_sessions(3)
