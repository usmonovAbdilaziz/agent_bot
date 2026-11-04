"""Auditda topilgan xatolar uchun regressiya testlari."""
from legacy_bot import App, dispatcher
from db import DB


async def test_notice_survives_reply_markup_failure(h):
    await h.prepare()
    mid = await h.draft(target=3)
    h.fail[('editMessageReplyMarkup', 3)] = 500
    await h.cb(3, f'view:{mid}')
    assert len(await h.db.active_sessions(2)) == 1
    assert (await h.db.one('SELECT status FROM messages WHERE id=?', (mid,)))['status'] == 'delivered'
    # Qayta bosish ham ogohlantirishni tiklashi kerak.
    await h.cb(3, f'view:{mid}')
    for uid in (2, 3):
        assert any("Xabarlar bot orqali o'tadi" in x['text'] for x in h.sent(uid))


async def test_close_notification_forbidden_closes_other_sessions(h):
    await h.prepare()
    sid = await h.session(2, 3)
    await h.session(4, 3)
    h.fail[('sendMessage', 3)] = 403
    await h.cb(2, f'close:{sid}')
    assert (await h.db.one('SELECT active FROM users WHERE tg_id=3'))['active'] == 0
    assert not await h.db.active_sessions(3)


async def test_stopped_admin_does_not_receive_report_copy(h):
    await h.prepare()
    sid = await h.session()
    await h.msg(2, 'Shikoyat qilinadigan xabar')
    mapped = await h.db.one('SELECT * FROM relay_map WHERE chat_id=3 ORDER BY msg_id DESC')
    await h.msg(1, '/stop')
    before = len(h.sent(1, 'copyMessage'))
    await h.cb(3, f'report:{sid}', mapped['msg_id'])
    assert len(h.sent(1, 'copyMessage')) == before


async def test_notice_retry_after_restart_and_before_relay(h):
    await h.prepare()
    mid = await h.draft(target=3)
    h.fail[('sendMessage', 2)] = 500
    await h.cb(3, f'view:{mid}')
    assert not await h.db.one('SELECT notice_msg_id FROM session_notices WHERE chat_id=2 AND notice_msg_id IS NOT NULL')
    assert await h.db.one('SELECT notice_msg_id FROM session_notices WHERE chat_id=3 AND notice_msg_id IS NOT NULL')
    h.app = App(h.bot, DB(h.db.path), h.cfg, 'test_agent_bot')
    h.dp = dispatcher(h.app)
    h.fail[('sendMessage', 2)] = 500
    await h.msg(3, 'Hali ogohlantirish kelmadi')
    assert not h.sent(2, 'copyMessage')
    await h.msg(3, 'Endi yetkazilsin')
    assert len(h.sent(2, 'copyMessage')) == 1
    for uid in (2, 3):
        assert sum("Xabarlar bot orqali o'tadi" in d['text'] for d in h.sent(uid)) == (3 if uid == 2 else 1)
    # 2 uchun ikkita muvaffaqiyatsiz HTTP urinish + bitta muvaffaqiyatli xabar.
    await h.app.recover_pending()
    assert len(await h.db.all('SELECT * FROM session_notices WHERE notice_msg_id IS NOT NULL')) == 2


async def test_report_waits_for_admin_start_and_survives_restart(h):
    await h.prepare()
    sid = await h.session()
    await h.msg(2, 'Suhbat matni')
    mapped = await h.db.one('SELECT * FROM relay_map WHERE chat_id=3 ORDER BY msg_id DESC')
    await h.msg(1, '/stop')
    await h.cb(3, f'report:{sid}', mapped['msg_id'])
    assert not h.sent(1, 'copyMessage')
    assert len(await h.db.all('SELECT * FROM reports')) == 1
    h.app = App(h.bot, DB(h.db.path), h.cfg, 'test_agent_bot')
    h.dp = dispatcher(h.app)
    await h.app.recover_pending()
    assert not h.sent(1, 'copyMessage')
    await h.msg(1, '/start')
    assert len(h.sent(1, 'copyMessage')) == 1
    assert await h.db.one('SELECT 1 FROM report_delivery WHERE delivered_at IS NOT NULL')
    await h.cb(1, 'reports')
    await h.cb(3, f'report:{sid}', mapped['msg_id'])
    assert len(h.sent(1, 'copyMessage')) == 1


async def test_report_copy_failure_retries_without_duplicate_header(h):
    await h.prepare()
    sid = await h.session()
    await h.msg(2, 'Suhbat matni')
    mapped = await h.db.one('SELECT * FROM relay_map WHERE chat_id=3 ORDER BY msg_id DESC')
    h.fail[('copyMessage', 1)] = 500
    await h.cb(3, f'report:{sid}', mapped['msg_id'])
    delivery = await h.db.one('SELECT * FROM report_delivery')
    assert delivery['header_msg_id'] is not None and delivery['delivered_at'] is None
    h.app = App(h.bot, DB(h.db.path), h.cfg, 'test_agent_bot')
    h.dp = dispatcher(h.app)
    await h.cb(1, 'reports')
    assert (await h.db.one('SELECT * FROM report_delivery'))['delivered_at'] is not None
    assert len(h.sent(1, 'copyMessage')) == 2  # bir xato + bir muvaffaqiyat
    assert sum(d['text'].startswith('🚩 Shikoyat:') for d in h.sent(1)) == 1


async def test_forbidden_notification_cascade_does_not_recurse(h):
    await h.prepare()
    sid = await h.session(2, 3)
    await h.session(3, 4)
    await h.session(4, 1)
    for uid in (1, 3, 4):
        h.fail[('sendMessage', uid)] = 403
    await h.cb(2, f'close:{sid}')
    assert not await h.db.all("SELECT * FROM sessions WHERE status='open'")
    assert len(await h.db.all('SELECT * FROM users WHERE active=0')) == 3
    assert not h.app.handling_unavailable and not h.app.unavailable_queue
    assert not await h.db.one("SELECT * FROM logs WHERE action='xatolik'")


async def test_control_edit_forbidden_also_closes_session(h):
    await h.prepare()
    mid = await h.draft(target=3)
    h.fail[('editMessageReplyMarkup', 3)] = 403
    await h.cb(3, f'view:{mid}')
    assert not await h.db.active_sessions(2)
    assert (await h.db.one('SELECT * FROM users WHERE tg_id=3'))['active'] == 0
    before = len(h.calls)
    await h.app.recover_pending()
    assert len(h.calls) == before


async def test_schema_upgrade_retains_existing_data_and_queues_notices(h):
    await h.prepare()
    sid = await h.session()
    # Avvalgi relizda bu ikki jadval bo'lmagan.
    await h.db.run('DROP TABLE session_notices')
    await h.db.run('DROP TABLE report_delivery')
    await h.db.init()
    assert await h.db.setting('admin') == '1'
    assert len(await h.db.active_sessions(2)) == 1
    assert len(await h.db.all('SELECT * FROM session_notices WHERE session_id=?', (sid,))) == 2
    await h.app.recover_pending()
    assert not await h.db.one('SELECT * FROM session_notices WHERE notice_msg_id IS NULL')
    before = len(h.calls)
    await h.db.init()
    await h.app.recover_pending()
    assert len(h.calls) == before


async def test_admin_request_notice_recovers_after_restart(h):
    await h.prepare()
    await h.draft()
    link = await h.db.one('SELECT * FROM links')
    await h.msg(3, f'/start i_{link["token"]}')
    await h.cb(4, f'ask:{link["token"]}')
    h.fail[('sendMessage', 4)] = 500
    await h.cb(1, 'accept:1')
    assert len(await h.db.active_sessions(4)) == 1
    assert await h.db.one('SELECT * FROM session_notices WHERE chat_id=4 AND notice_msg_id IS NULL')
    h.app = App(h.bot, DB(h.db.path), h.cfg, 'test_agent_bot')
    await h.app.recover_pending()
    assert not await h.db.one('SELECT * FROM session_notices WHERE notice_msg_id IS NULL')


async def test_sender_invite_and_receiver_shortcut_obey_existing_flow(h):
    await h.prepare(True)
    await h.cb(1, 'invite_sender')
    assert 'https://t.me/test_agent_bot' in h.sent(1)[-1]['text']
    assert not await h.db.one('SELECT * FROM links')
    await h.cb(2, 'new_link')
    # Tanlov ham restartdan keyin saqlanadi; yangi havola hali yo'q.
    h.app = App(h.bot, DB(h.db.path), h.cfg, 'test_agent_bot')
    h.dp = dispatcher(h.app)
    await h.msg(2, 'Receiver uchun', photo=True)
    await h.msg(2, 'Receiver sarlavhasi')
    await h.msg(2, 'Receiver tavsifi')
    m = await h.db.one('SELECT * FROM messages')
    assert m['mode'] == 'link' and m['status'] == 'draft'
    assert not await h.db.one('SELECT * FROM links')
    await h.cb(2, f'confirm:{m["id"]}')
    assert (await h.db.one('SELECT * FROM messages'))['status'] == 'pending'
    await h.cb(1, f'approve:{m["id"]}')
    link = await h.db.one('SELECT * FROM links')
    assert link['creator_tg_id'] == 2
    await h.msg(3, f'/start i_{link["token"]}')
    assert not h.sent(3, 'sendPhoto')
    await h.cb(3, f'view:{m["id"]}')
    assert len(h.sent(3, 'sendPhoto')) == 1
    assert len(await h.db.active_sessions(2)) == 1
    assert await h.db.setting('admin') == '1'
