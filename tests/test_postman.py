"""Ixtiyoriy Postman HTTP/polling sinovi; POSTMAN_TEST_URL bilan yoqiladi."""
import asyncio
import contextlib
import os
import socket
import json
import time

import aiohttp
import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.exceptions import TelegramForbiddenError, TelegramServerError
from aiogram.types import Update

from db import DB
from legacy_bot import App, Config, dispatcher

URL=os.getenv('POSTMAN_TEST_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Postman simulyatsiyasi alohida ishga tushiriladi')


async def test_full_main_starts_webapp_menu_and_polling(tmp_path,monkeypatch):
    import main as entry
    token='123456:TEST_ONLY_NOT_A_REAL_TOKEN'
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0))
        port=probe.getsockname()[1]
    cfg=Config(token,'998900000000',db_path=str(tmp_path/'startup.sqlite3'),
               webapp_url='https://mini.example.test',webapp_port=port)
    bot=Bot(token,session=AiohttpSession(api=TelegramAPIServer.from_base(URL)))
    monkeypatch.setattr(entry.Config,'load',lambda:cfg)
    monkeypatch.setattr(entry,'Bot',lambda *args,**kwargs:bot)
    async with aiohttp.ClientSession() as http:
        async with http.post(URL+'/_test/reset',json={}) as response:
            assert response.status==200
        task=asyncio.create_task(entry.main())
        try:
            async with asyncio.timeout(10):
                while True:
                    if task.done():
                        await task
                        pytest.fail('main exited before readiness')
                    try:
                        async with http.get(f'http://127.0.0.1:{port}/healthz') as response:
                            if response.status==200:
                                assert await response.json()=={'ready':True}
                                break
                    except aiohttp.ClientConnectionError:
                        pass
                    await asyncio.sleep(.05)
                while True:
                    async with http.get(URL+'/_test/calls') as response:
                        calls=await response.json()
                    if any(c['method']=='getUpdates' for c in calls):
                        break
                    await asyncio.sleep(.05)
            menu=next(c for c in calls if c['method']=='setChatMenuButton')
            assert json.loads(menu['body']['menu_button'])['type']=='commands'
            commands=next(c for c in calls if c['method']=='setMyCommands')
            assert [c['command'] for c in json.loads(commands['body']['commands'])]==['start','taklif','guests']
            async with http.get(f'http://127.0.0.1:{port}/') as response:
                assert response.status==200 and 'Siz uchun taklif' in await response.text()
            async with http.get(f'http://127.0.0.1:{port}/assets/app.js') as response:
                assert response.status==200 and 'Tanlovingiz uchun rahmat!' in await response.text()
            async with http.get(f'http://127.0.0.1:{port}/api/me') as response:
                assert response.status==401
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        with pytest.raises(aiohttp.ClientConnectionError):
            await http.get(f'http://127.0.0.1:{port}/healthz')


async def test_postman_http_polling_and_failures(tmp_path):
    token='123456:TEST_ONLY_NOT_A_REAL_TOKEN'
    bot=Bot(token,session=AiohttpSession(api=TelegramAPIServer.from_base(URL)),default=DefaultBotProperties(parse_mode='HTML'))
    db=DB(tmp_path/'postman.sqlite3')
    await db.init(False)
    app=App(bot,db,Config(token,'998937777453',moderation=False),'test_agent_bot')
    dp=dispatcher(app)
    async with aiohttp.ClientSession() as http, bot:
        async with http.post(URL+'/_test/reset',json={}) as resp: assert resp.status==200
        assert (await bot.get_me()).username=='test_agent_bot'
        await bot.delete_webhook(drop_pending_updates=False)
        await bot.set_my_commands([])
        def msg(uid,mid,**extra):
            return {'message_id':mid,'date':int(time.time()),'chat':{'id':uid,'type':'private'},
                    'from':{'id':uid,'is_bot':False,'first_name':f'Ism{uid}'},**extra}
        async def callback(uid,data,update_id):
            await dp.feed_update(bot,Update.model_validate({'update_id':update_id,'callback_query':{
                'id':str(update_id),'from':{'id':uid,'is_bot':False,'first_name':f'Ism{uid}'},
                'chat_instance':'test','data':data,'message':msg(uid,99)}}))
        initial=[{'update_id':1,'message':msg(2,1,text='/start')},
                 {'update_id':2,'message':msg(3,2,text='/start')},
                 {'update_id':3,'message':msg(2,3,photo=[{'file_id':'real_shape_file_id','file_unique_id':'unique','width':100,'height':100}])}]
        async with http.post(URL+'/_test/updates',json={'updates':initial}) as resp: assert resp.status==200
        polling=asyncio.create_task(dp.start_polling(bot,handle_as_tasks=False,handle_signals=False,close_bot_session=False,polling_timeout=1))
        try:
            async with asyncio.timeout(10):
                while not await db.one('SELECT * FROM messages'):
                    await asyncio.sleep(.05)
            async with app.lock: pass
            await dp.stop_polling()
            await polling
            await db.metadata(1,2,'Sinov sarlavhasi','Sinov tavsifi')
            await db.run('DELETE FROM message_inputs WHERE tg_id=2')
            await callback(2,'target:1:0',4)
            await callback(2,'confirm:1',5)
            link=await db.one('SELECT * FROM links')
            assert link
            await dp.feed_update(bot,Update.model_validate({'update_id':6,'message':msg(3,6,text=f'/start i_{link["token"]}')}))
            await callback(3,'view:1',7)
            assert len(await db.active_sessions(2))==1
            await dp.feed_update(bot,Update.model_validate({'update_id':8,'message':msg(2,8,text='Salom')}))
            assert await db.one('SELECT * FROM relay_map WHERE chat_id=2 AND msg_id=8')
            with pytest.raises(TelegramForbiddenError): await bot.send_message(403,'Sinov')
            with pytest.raises(TelegramServerError): await bot.send_message(500,'Sinov')
            async with http.get(URL+'/_test/calls') as resp: calls=await resp.json()
            methods={c['method'] for c in calls}
            assert {'getUpdates','getMe','sendPhoto','copyMessage','answerCallbackQuery'}<=methods
            assert not await db.one("SELECT * FROM logs WHERE action='xatolik'")
        finally:
            if not polling.done():
                polling.cancel()
                with contextlib.suppress(asyncio.CancelledError): await polling


@pytest.mark.parametrize('notice_error',[None,500,403])
async def test_minimal_video_invitation_through_postman(tmp_path,notice_error):
    from main import App as MinimalApp, dispatcher as minimal_dispatcher
    from invitation_store import InvitationDB
    from webapp import create_web_app
    from aiohttp import web
    from test_webapp import signed
    token='123456:TEST_ONLY_NOT_A_REAL_TOKEN'
    bot=Bot(token,session=AiohttpSession(api=TelegramAPIServer.from_base(URL)),default=DefaultBotProperties(parse_mode='HTML'))
    db=InvitationDB(tmp_path/'minimal.sqlite3'); await db.init()
    cfg=Config(token,'998900000000',webapp_url='https://mini.example.test')
    app=MinimalApp(bot,db,cfg,'test_agent_bot'); dp=minimal_dispatcher(app)
    runner=web.AppRunner(create_web_app(app)); await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0); await site.start()
    web_url=f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
    seq=0
    async def update(uid,text=None,callback=None,**extra):
        nonlocal seq
        seq+=1
        user={'id':uid,'is_bot':False,'first_name':'Sinov','last_name':'Sender'}
        message={'message_id':seq,'date':int(time.time()),'chat':{'id':uid,'type':'private'},'from':user,**extra}
        if text is not None: message['text']=text
        payload={'update_id':seq}
        if callback:
            payload['callback_query']={'id':str(seq),'from':user,'chat_instance':'test','data':callback,'message':message}
        else: payload['message']=message
        await dp.feed_update(bot,Update.model_validate(payload))
    try:
        async with aiohttp.ClientSession() as http, bot:
            async with http.post(URL+'/_test/reset',json={}) as response: assert response.status==200
            await update(1,'/start')
            await update(1,contact={'phone_number':'+998900000000','first_name':'Admin','user_id':1})
            await update(1,callback='q:self')
            await update(1,callback='q:ctype:1:fun')
            await update(1,video={'file_id':'video_id','file_unique_id':'unique','duration':60,'width':200,'height':200,'file_size':1024,'mime_type':'video/mp4'})
            await update(1,callback='q:name:1')
            await update(1,'Postman orqali video taklif')
            await update(1,callback='q:layout:1:bottom')
            await update(1,callback='q:confirm:1')
            item=await db.invite(1)
            assert item['token'] and item['link_sent'] and item['title']=='Sinov Sender'
            await update(2,f'/start i_{item["token"]}')
            headers={'X-Telegram-Init-Data':signed(token,2)}
            async with http.get(web_url+'/api/invites/1',headers=headers) as response:
                assert response.status==200 and (await response.json())['media_kind']=='video'
            if notice_error:
                async with http.post(URL+'/_test/fail-next',json={'method':'sendMessage','chat_id':1,'code':notice_error}) as response:
                    assert response.status==200
            async with http.post(web_url+'/api/invites/1/accept',headers=headers,json={'no_attempts':7}) as response:
                assert response.status==200 and (await response.json())['accepted']
            notice=await db.one('SELECT * FROM q_accept_notices WHERE invite_id=1')
            assert notice['status']==({500:'pending',403:'failed'}.get(notice_error,'sent'))
            if notice_error==500:
                restarted=MinimalApp(bot,db,cfg,'test_agent_bot')
                worker=asyncio.create_task(restarted.acceptance_notifications())
                try:
                    for _ in range(100):
                        if (await db.one('SELECT * FROM q_accept_notices WHERE invite_id=1'))['status']=='sent': break
                        await asyncio.sleep(.02)
                    assert (await db.one('SELECT * FROM q_accept_notices WHERE invite_id=1'))['status']=='sent'
                finally:
                    worker.cancel()
                    with contextlib.suppress(asyncio.CancelledError): await worker
            async with http.get(URL+'/_test/calls') as response: before=await response.json()
            notices=[c for c in before if c['method']=='sendMessage' and 'Taklifingiz qabul qilindi' in c['body'].get('text','')]
            assert len(notices)==(2 if notice_error==500 else 1)
            assert all(str(c['body']['chat_id'])=='1' and '7 marta' in c['body']['text'] for c in notices)
            async with http.post(web_url+'/api/invites/1/accept',headers=headers,json={'no_attempts':99}) as response:
                assert response.status==200
            assert (await db.invite(1))['no_attempts']==7
            await update(2,'Salom')
            async with http.get(URL+'/_test/calls') as response: after=await response.json()
            assert before==after
            await update(2,'/start')
            async with http.get(URL+'/_test/calls') as response: resumed=await response.json()
            assert 'ro‘yxatdan' in resumed[-1]['body']['text']
            assert {'sendMessage','sendVideo','answerCallbackQuery','editMessageReplyMarkup'}<={c['method'] for c in after}
            assert not await db.all('SELECT * FROM sessions')
            if notice_error is None:
                # Returning receiver requests one sender permission, creates one link,
                # then can still receive another independent invitation.
                await update(2,callback='q:request')
                await update(2,contact={'phone_number':'+998901234567','first_name':'Sender','user_id':2})
                async with http.post(URL+'/_test/fail-next',json={'method':'sendMessage','chat_id':1,'code':500}) as response:
                    assert response.status==200
                await update(2,callback='q:quota:1')
                request=await db.one("SELECT * FROM q_sender_requests WHERE uid=2 AND status='pending'")
                assert not request['admin_notified']
                restarted=MinimalApp(bot,db,cfg,'test_agent_bot')
                await restarted.notify_sender_request(request['id'])
                assert (await db.one('SELECT * FROM q_sender_requests WHERE id=?',(request['id'],)))['admin_notified']
                await update(2,callback=f'q:approve:{request["id"]}')
                assert not await app.is_sender(2)
                await update(1,callback=f'q:approve:{request["id"]}')
                assert await app.is_sender(2)
                await update(2,'/start')
                mid=(await db.flow(2))['invite_id']
                await update(2,callback=f'q:ctype:{mid}:fun')
                await update(2,callback=f'q:skip:{mid}')
                await update(2,callback=f'q:name:{mid}')
                await update(2,'Ruxsat bilan yaratilgan taklif')
                await update(2,callback=f'q:layout:{mid}:bottom')
                await update(2,callback=f'q:confirm:{mid}')
                assert (await db.invite(mid))['token'] and not await app.is_sender(2)
                await update(1,callback=f'q:approve:{request["id"]}')
                await update(2,callback='q:new')
                assert await db.begin(2) is None
                assert len(await db.all('SELECT * FROM q_invites WHERE sender=2'))==1
                await update(1,callback='q:self')
                fresh=(await db.flow(1))['invite_id']
                await update(1,callback=f'q:ctype:{fresh}:fun')
                await update(1,callback=f'q:skip:{fresh}')
                await update(1,callback=f'q:name:{fresh}')
                await update(1,'Avvalgi receiverga yangi taklif')
                await update(1,callback=f'q:layout:{fresh}:bottom')
                await update(1,callback=f'q:confirm:{fresh}')
                invitation=await db.invite(fresh)
                await update(2,f'/start i_{invitation["token"]}')
                assert (await db.invite(fresh))['receiver']==2
                async with http.post(web_url+f'/api/invites/{fresh}/accept',headers=headers,json={'no_attempts':3}) as response:
                    assert response.status==200
                await update(2,'/taklif')
                await update(2,'Yangi g‘oya')
                suggestion=await db.one('SELECT * FROM q_suggestions WHERE uid=2')
                await update(1,callback=f'q:idea_yes:{suggestion["id"]}')
                await update(1,callback=f'q:idea_yes:{suggestion["id"]}')
                assert (await db.one('SELECT remaining FROM q_sender_credits WHERE uid=2'))['remaining']==1
                async with http.get(URL+'/_test/calls') as response: flow_calls=await response.json()
                assert any(c['method']=='sendMessage' and str(c['body'].get('chat_id'))=='1' and 'Sender bo‘lish so‘rovi' in c['body'].get('text','') for c in flow_calls)
                assert any(c['method']=='sendMessage' and str(c['body'].get('chat_id'))=='2' and 'Admin 1 ta taklif' in c['body'].get('text','') for c in flow_calls)
                assert any(c['method']=='sendMessage' and str(c['body'].get('chat_id'))=='1' and 'Yangi g‘oya' in c['body'].get('text','') for c in flow_calls)
    finally:
        await runner.cleanup()

async def test_ceremony_rsvp_with_postman_notification_retry(tmp_path):
    from invitation_store import InvitationDB
    from main import App as MinimalApp
    from webapp import create_web_app
    from aiohttp import web
    from test_webapp import signed
    token='123456:TEST_ONLY_NOT_A_REAL_TOKEN'
    bot=Bot(token,session=AiohttpSession(api=TelegramAPIServer.from_base(URL)),default=DefaultBotProperties(parse_mode='HTML'))
    db=InvitationDB(tmp_path/'rsvp.sqlite3'); await db.init()
    details={'event_kind':'nikah','date':'01.01.2099','time':'10:00','address':'Toshkent','map_url':'','program':[],'note':'Xush kelibsiz','layout':{'text_position':'bottom'}}
    await db.run("INSERT INTO q_invites(id,sender,receiver,title,description,created_at,expires_at,status,type,design,details) VALUES(1,1,2,'Bayram','Xush kelibsiz',?,?, 'ready','ceremony','ceremony_elegant',?)",(time.time(),time.time()+3600,json.dumps(details)))
    from config import Config as CurrentConfig
    cfg=CurrentConfig(token,'998900000000',webapp_url='https://mini.example.test')
    app=MinimalApp(bot,db,cfg,'test_agent_bot'); runner=web.AppRunner(create_web_app(app)); await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0); await site.start(); port=site._server.sockets[0].getsockname()[1]
    try:
        async with bot, aiohttp.ClientSession() as client:
            async with client.post(URL+'/_test/reset',json={}) as response: assert response.status==200
            async with client.post(URL+'/_test/fail-next',json={'method':'sendMessage','chat_id':1,'code':500}) as response: assert response.status==200
            address=f'http://127.0.0.1:{port}/api/invites/1/rsvp'; headers={'X-Telegram-Init-Data':signed(token,2)}
            async with client.post(address,headers=headers,json={'attending':1,'guests':3}) as response:
                assert response.status==200 and (await response.json())['rsvp']['guests']==3
            assert (await db.one('SELECT * FROM q_rsvps WHERE invite_id=1'))['notice_status']=='pending'
            await app.notify_rsvp(1)
            assert (await db.one('SELECT * FROM q_rsvps WHERE invite_id=1'))['notice_status']=='sent'
            await app.guests(1,1)
            async with client.get(URL+'/_test/guest-messages') as response: guest_messages=await response.json()
            assert len(guest_messages)==1 and 'jami 3 kishi' in guest_messages[0]['body']['text']
            async with client.get(URL+'/_test/rsvp-notices') as response: notices=await response.json()
            assert len(notices)==2 and all('Ism2' in x['body']['text'] and 'Mehmonlar soni: 3' in x['body']['text'] for x in notices)
            async with client.post(address,headers=headers,json={'attending':0,'guests':0}) as response:
                assert response.status==200 and (await response.json())['rsvp']['guests']==3
    finally:
        await runner.cleanup()
