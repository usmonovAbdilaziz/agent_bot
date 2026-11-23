"""Meeting delivery and notice retry against the existing Postman simulation."""
import os
import aiohttp
import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from test_minimal import n, api
from test_meeting import meeting_ready, response

URL=os.getenv('POSTMAN_TEST_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Postman simulation is run separately')


@pytest.mark.parametrize('kind', ['legacy', 'love', 'friendship'])
async def test_meeting_plan_notification_through_postman(n,api,kind):
    original=n.bot.session
    n.bot.session=AiohttpSession(api=TelegramAPIServer.from_base(URL))
    try:
        async with aiohttp.ClientSession() as client:
            async with client.post(URL+'/_test/reset',json={}) as r: assert r.status==200
            if kind == 'legacy':
                item=await meeting_ready(n,verify_menu=False)
            else:
                await n.cb(1, 'q:choose')
                await n.cb(1, 'q:fun')
                assert await n.db.flow(1) is None
                await n.cb(1, 'q:' + kind)
                mid=(await n.db.flow(1))['invite_id']
                await n.msg(1, 'Ali')
                await n.msg(1, 'Vali')
                await n.cb(1, f'q:mskip:{mid}')
                await n.cb(1, f'q:confirm:{mid}')
                item=await n.db.invite(mid)
                await n.msg(2, f'/start i_{item["token"]}')
            status, detail=await api('GET', f'/api/invites/{item["id"]}')
            assert status==200
            assert detail['details']['meeting_kind']==('love' if kind=='legacy' else kind)
            async with client.post(URL+'/_test/fail-next',json={'method':'sendMessage','chat_id':1,'code':500}) as r: assert r.status==200
            payload={'meeting_response':response(),'no_attempts':2}
            assert (await api('POST',f'/api/invites/{item["id"]}/accept',json=payload))[0]==200
            await n.app.notify_acceptance(item['id'])
            assert (await n.db.one('SELECT status FROM q_accept_notices'))['status']=='sent'
            assert (await api('POST',f'/api/invites/{item["id"]}/accept',json={}))[0]==200
            async with client.get(URL+'/_test/calls') as r: calls=await r.json()
            notices=[c for c in calls if c['method']=='sendMessage' and 'Uchrashuv rejasi' in c['body'].get('text','')]
            assert len(notices)==2  # one injected failure, one delivered retry
            assert 'Qahva va uzoq suhbat' in notices[-1]['body']['text']
            assert 'Soatni kelishdik.' in notices[-1]['body']['text']
    finally:
        await n.bot.session.close(); n.bot.session=original
