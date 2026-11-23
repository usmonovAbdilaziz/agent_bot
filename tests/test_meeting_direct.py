import json
from test_minimal import n, api
from main import App, dispatcher

async def test_fun_direct_meeting_resume_edit_and_publish(n, api):
    await n.cb(1, 'q:choose')
    await n.cb(1, 'q:fun')
    flow = await n.db.flow(1)
    mid = flow['invite_id']
    assert flow['stage'] == 'meeting_recipient'
    assert (await n.db.invite(mid))['design'] == 'meeting'
    assert 'q:mskip' not in n.sent(1)[-1]['reply_markup']
    await n.msg(1, 'Shaxzoda')
    await n.msg(1, 'Javohir')
    n.app = App(n.bot, n.db, n.cfg, 'test_agent_bot')
    n.dp = dispatcher(n.app)
    await n.cb(1, 'q:continue')
    assert (await n.db.flow(1))['stage'] == 'meeting_slots'
    await n.cb(1, f'q:mskip:{mid}')
    assert (await n.db.flow(1))['stage'] == 'preview'
    markup = n.sent(1)[-1]['reply_markup']
    assert 'q:design' not in markup
    assert any(button['text'] == 'Ma’lumotlarni tahrirlash' for row in json.loads(markup)['inline_keyboard'] for button in row)
    await n.cb(1, f'q:style:{mid}:classic')
    assert (await n.db.invite(mid))['design'] == 'meeting'
    await n.cb(1, f'q:edit:{mid}')
    assert (await n.db.flow(1))['stage'] == 'meeting_recipient'
    await n.msg(1, 'Malika')
    await n.cb(1, 'q:back')
    assert (await n.db.flow(1))['stage'] == 'meeting_recipient'
    await n.msg(1, 'Malika')
    await n.msg(1, 'Javohir')
    await n.cb(1, f'q:mskip:{mid}')
    await n.cb(1, f'q:confirm:{mid}')
    item = await n.db.invite(mid)
    assert item['status'] == 'ready'
    assert item['title'] == 'Malika'
    assert json.loads(item['details'])['meeting_configured']
    await n.msg(2, f'/start i_{item["token"]}')
    status, data = await api('GET', f'/api/invites/{mid}', uid=2)
    assert status == 200
    assert data['design'] == 'meeting'

async def test_ceremony_still_starts_wedding(n):
    await n.cb(1, 'q:ceremony')
    await n.cb(1, 'q:wedding')
    assert (await n.db.flow(1))['stage'] == 'wedding_groom'
