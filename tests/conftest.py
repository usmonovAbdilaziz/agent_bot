"""Haqiqiy aiogram HTTP so'rovlari va Dispatcher; Telegram hisoblari kerak emas."""
import time

import pytest_asyncio
from aiohttp import web
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.types import Update

from db import DB
from legacy_bot import App, Config, dispatcher

TOKEN='123456:TEST_ONLY_NOT_A_REAL_TOKEN'


class Harness:
    def __init__(self):
        self.calls=[]
        self.counter=1000
        self.update_id=0
        self.fail={}

    async def telegram(self, request):
        method=request.match_info['method']
        data=dict(await request.post())
        self.calls.append((method,data))
        chat=int(data.get('chat_id',0))
        if (method,chat) in self.fail:
            code=self.fail.pop((method,chat))
            error={'ok':False,'error_code':code,'description':'simulated failure'}
            if code==429: error['parameters']={'retry_after':1}
            return web.json_response(error,status=code)
        if method in ('answerCallbackQuery','setMyCommands','deleteWebhook','deleteMessage','setChatMenuButton'):
            result=True
        elif method=='getFile':
            result={'file_id':data['file_id'],'file_unique_id':'photo_unique','file_size':4,'file_path':'photos/test.jpg'}
        elif method=='getMe':
            result={'id':123456,'is_bot':True,'first_name':'Sinov','username':'test_agent_bot'}
        elif method=='copyMessage':
            assert data.get('from_chat_id') and data.get('message_id')
            self.counter+=1
            result={'message_id':self.counter}
        elif method in ('sendMessage','sendPhoto','sendVideo','sendVideoNote','editMessageReplyMarkup'):
            assert chat
            if method=='sendPhoto': assert data.get('photo')
            if method=='sendMessage': assert 0<len(data.get('text',''))<=4096
            self.counter+=1
            result={'message_id':self.counter,'date':int(time.time()),'chat':{'id':chat,'type':'private'}}
            if method=='sendPhoto':
                result['photo']=[{'file_id':'telegram_photo_id','file_unique_id':'photo_unique','width':100,'height':100}]
        else:
            return web.json_response({'ok':False,'error_code':501,'description':'Endpoint not modeled'},status=501)
        return web.json_response({'ok':True,'result':result})

    def user(self, uid):
        return {'id':uid,'is_bot':False,'first_name':f'Ism <{uid}>','username':f'user{uid}'}

    async def msg(self, uid, text=None, photo=False, voice=False, reply=None, contact=None, message_id=None):
        self.update_id+=1
        payload={'message_id':message_id or self.update_id,'date':int(time.time()),'chat':{'id':uid,'type':'private'},'from':self.user(uid)}
        if photo:
            payload['photo']=[{'file_id':'telegram_photo_id','file_unique_id':'photo_unique','width':100,'height':100}]
            if text: payload['caption']=text
        elif voice:
            payload['voice']={'file_id':'voice_id','file_unique_id':'voice_unique','duration':2}
        elif text is not None:
            payload['text']=text
        if reply:
            payload['reply_to_message']={'message_id':reply,'date':int(time.time()),'chat':payload['chat']}
        if contact: payload['contact']=contact
        await self.dp.feed_update(self.bot,Update.model_validate({'update_id':self.update_id,'message':payload}))
        return payload['message_id']

    async def cb(self, uid, data, msg_id=999):
        self.update_id+=1
        await self.dp.feed_update(self.bot,Update.model_validate({'update_id':self.update_id,'callback_query':{
            'id':str(self.update_id),'from':self.user(uid),'chat_instance':'test','data':data,
            'message':{'message_id':msg_id,'date':int(time.time()),'chat':{'id':uid,'type':'private'}}}}))

    async def prepare(self, moderation=False):
        for uid in (1,2,3,4): await self.msg(uid,'/start')
        await self.msg(1,contact={'phone_number':'+998937777453','first_name':'Admin','user_id':1})
        await self.db.set_setting('moderation',int(moderation))

    async def draft(self, uid=2, target=0):
        await self.msg(uid,'/yangi')
        await self.msg(uid,'<b>Izoh & maxsus</b>',photo=True)
        await self.msg(uid,'Sinov sarlavhasi')
        await self.msg(uid,'Sinov tavsifi')
        m=await self.db.one('SELECT * FROM messages WHERE sender_tg_id=? ORDER BY id DESC',(uid,))
        await self.cb(uid,f'target:{m["id"]}:{target}')
        await self.cb(uid,f'confirm:{m["id"]}')
        return m['id']

    async def session(self,a=2,b=3):
        mid=await self.draft(a,b)
        await self.cb(b,f'view:{mid}')
        return (await self.db.one('SELECT * FROM sessions WHERE message_id=?',(mid,)))['id']

    def sent(self, uid, method='sendMessage'):
        return [d for m,d in self.calls if m==method and int(d.get('chat_id',0))==uid]


@pytest_asyncio.fixture
async def h(tmp_path):
    h=Harness()
    server=web.Application()
    server.router.add_post('/bot{token}/{method}',h.telegram)
    async def photo_file(request):
        return web.Response(body=b'\xff\xd8\xff\xd9',content_type='image/jpeg')
    server.router.add_get('/file/bot{token}/photos/test.jpg',photo_file)
    runner=web.AppRunner(server)
    await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0)
    await site.start()
    port=site._server.sockets[0].getsockname()[1]
    session=AiohttpSession(api=TelegramAPIServer.from_base(f'http://127.0.0.1:{port}'))
    h.bot=Bot(TOKEN,session=session,default=DefaultBotProperties(parse_mode='HTML'))
    h.db=DB(tmp_path/'test.sqlite3')
    await h.db.init()
    h.cfg=Config(TOKEN,'998937777453')
    h.app=App(h.bot,h.db,h.cfg,'test_agent_bot')
    h.dp=dispatcher(h.app)
    yield h
    await h.bot.session.close()
    await runner.cleanup()
