"""Optional wedding path through the repository's local Postman Telegram mock."""
import os
import pytest
import aiohttp
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from config import Config
from invitation_store import InvitationDB
from main import App, dispatcher
from conftest import Harness, TOKEN

URL = os.getenv('POSTMAN_TEST_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Postman simulyatsiyasi alohida ishga tushiriladi')

async def test_wedding_preview_upload_and_shared_link(tmp_path):
    async with aiohttp.ClientSession() as http:
        async with http.post(URL+'/_test/reset',json={}) as response: assert response.status == 200
        h=Harness()
        h.bot=Bot(TOKEN,session=AiohttpSession(api=TelegramAPIServer.from_base(URL)),default=DefaultBotProperties(parse_mode='HTML'))
        h.db=InvitationDB(tmp_path/'wedding.sqlite3')
        await h.db.init()
        h.cfg=Config(TOKEN,'998937777453',webapp_url='https://mini.example.test')
        h.app=App(h.bot,h.db,h.cfg,'test_agent_bot')
        h.dp=dispatcher(h.app)
        # Harness assertions inspect calls; the stand-in records them over HTTP.
        async def refresh_calls():
            async with http.get(URL+'/_test/calls') as response:
                calls=await response.json()
            h.calls=[(call['method'],call['body']) for call in calls]
        await h.msg(1,'/start')
        await h.msg(1,contact={'phone_number':'+998937777453','first_name':'Admin','user_id':1})
        # Feed the same wizard inputs without relying on the harness's in-memory HTTP log.
        await h.cb(1,'q:choose'); await h.cb(1,'q:ceremony'); await h.cb(1,'q:wedding')
        mid=(await h.db.flow(1))['invite_id']
        from datetime import datetime, timedelta
        from wedding import UZ_TZ
        for value in ('Farrux','Nasiba',(datetime.now(UZ_TZ)+timedelta(days=20)).strftime('%d.%m.%Y'),'17:00','Toshkent, to‘yxona'):
            await h.msg(1,value)
        await refresh_calls()
        photo=next(body for method,body in h.calls if method=='sendPhoto')
        attached=photo['photo'].removeprefix('attach://')
        assert photo[attached]['filename']=='taklifnoma.png' and photo[attached]['size'] > 0
        assert 'To‘y taklifnomasini tekshiring' in h.sent(1)[-1]['text']
        await h.cb(1,f'q:confirm:{mid}')
        item=await h.db.invite(mid)
        assert item['token']
        for uid in (2,3): await h.msg(uid,f'/start i_{item["token"]}')
        assert len(await h.db.all('SELECT * FROM q_wedding_guests WHERE invite_id=?',(mid,)))==2
        await h.bot.session.close()
