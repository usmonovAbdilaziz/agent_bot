import asyncio
import time

from db import DB
from legacy_bot import App, dispatcher


async def test_admin_own_contact_only(h):
    await h.msg(1,'/start')
    await h.msg(1,contact={'phone_number':'+998937777453','first_name':'A','user_id':2})
    assert await h.db.setting('admin') is None
    await h.msg(1,contact={'phone_number':'+998900000000','first_name':'A','user_id':1})
    assert await h.db.setting('admin') is None
    await h.msg(1,contact={'phone_number':'+998937777453','first_name':'A','user_id':1})
    assert await h.db.setting('admin')=='1'
    await h.msg(2,'/start')
    await h.cb(2,'moderation:0')
    assert await h.db.setting('moderation')=='1'


async def test_link_moderation_consent_and_relay(h):
    await h.prepare(True)
    mid=await h.draft()
    assert not await h.db.one('SELECT * FROM links')
    await h.cb(2,f'approve:{mid}')
    assert not await h.db.one('SELECT * FROM links')
    await h.cb(1,f'approve:{mid}')
    link=await h.db.one('SELECT * FROM links')
    await h.msg(2,f'/start i_{link["token"]}')
    assert (await h.db.one('SELECT * FROM links'))['status']=='new'
    await h.msg(3,f'/start i_{link["token"]}')
    assert not h.sent(3,'sendPhoto')
    await h.cb(4,f'view:{mid}')
    assert not h.sent(4,'sendPhoto')
    await h.cb(3,f'view:{mid}')
    assert len(h.sent(3,'sendPhoto'))==1
    assert h.sent(3,'sendPhoto')[0]['caption']=='&lt;b&gt;Izoh &amp; maxsus&lt;/b&gt;'
    await h.cb(3,f'view:{mid}')
    assert len(h.sent(3,'sendPhoto'))==1
    assert len(await h.db.active_sessions(2))==1
    await h.msg(3,'SALOM_PRIVATE_TEXT')
    assert len(h.sent(2,'copyMessage'))==1
    assert 'SALOM_PRIVATE_TEXT' not in str(await h.db.all('SELECT * FROM logs'))
    assert not await h.db.one("SELECT * FROM logs WHERE action='xatolik'")


async def test_atomic_claim_40_connections(h):
    await h.prepare()
    await h.draft()
    link=await h.db.one('SELECT * FROM links')
    outcomes=await asyncio.gather(*(DB(h.db.path).claim(link['token'],uid,3600) for uid in range(10,50)))
    assert sum(result=='won' for result,_ in outcomes)==1
    assert sum(result=='used' for result,_ in outcomes)==39
    final=await h.db.one('SELECT * FROM links')
    m=await h.db.one('SELECT * FROM messages')
    assert final['claimed_by']==m['receiver_tg_id']


async def test_used_link_admin_request_and_daily_limit(h):
    await h.prepare()
    await h.draft()
    link=await h.db.one('SELECT * FROM links')
    await h.msg(3,f'/start i_{link["token"]}')
    await h.msg(4,f'/start i_{link["token"]}')
    await h.cb(4,f'ask:{link["token"]}')
    await h.cb(4,f'ask:{link["token"]}')
    assert len(await h.db.all('SELECT * FROM admin_requests'))==1
    await h.cb(3,'accept:1')
    assert not await h.db.active_sessions(4)
    await h.cb(1,'accept:1')
    await h.cb(1,'accept:1')
    s=await h.db.active_sessions(4)
    assert len(s)==1 and s[0]['kind']=='admin_user'
    await h.msg(4,'Yordam kerak')
    assert len(h.sent(1,'copyMessage'))==1


async def test_request_denial(h):
    await h.prepare()
    await h.draft()
    link=await h.db.one('SELECT * FROM links')
    await h.msg(3,f'/start i_{link["token"]}')
    await h.cb(4,f'ask:{link["token"]}')
    await h.cb(1,'deny:1')
    assert (await h.db.one('SELECT * FROM admin_requests'))['status']=='rejected'
    assert not await h.db.active_sessions(4)


async def test_reply_routing_multiple_sessions_and_unknown_reply(h):
    await h.prepare()
    sid=await h.session(1,2)
    await h.session(1,3)
    before=len(h.sent(2,'copyMessage'))
    await h.msg(1,'Qayerga?')
    assert len(h.sent(2,'copyMessage'))==before
    mapped=await h.db.one('SELECT * FROM relay_map WHERE chat_id=1 AND session_id=?',(sid,))
    await h.msg(1,'Aniq javob',reply=mapped['msg_id'])
    assert len(h.sent(2,'copyMessage'))==before+1
    assert not h.sent(3,'copyMessage')
    await h.msg(1,'Begona reply',reply=987654)
    assert len(h.sent(2,'copyMessage'))==before+1


async def test_photo_voice_relay_and_explicit_new(h):
    await h.prepare()
    await h.session()
    await h.msg(2,photo=True)
    await h.msg(3,voice=True)
    assert len(h.sent(3,'copyMessage'))==1
    assert len(h.sent(2,'copyMessage'))==1
    assert len(await h.db.all('SELECT * FROM messages'))==1
    await h.msg(2,'/yangi')
    await h.msg(2,photo=True)
    assert len(await h.db.all('SELECT * FROM messages'))==2


async def test_block_decline_and_unblock(h):
    await h.prepare()
    mid=await h.draft(target=3)
    await h.cb(3,f'decline:{mid}')
    assert not h.sent(3,'sendPhoto')
    assert not await h.db.available(2,3)
    await h.cb(2,'unblock:3')
    assert not await h.db.available(2,3)
    await h.cb(3,'unblock:2')
    assert await h.db.available(2,3)
    sid=await h.session()
    await h.cb(4,f'block:{sid}')
    assert await h.db.active_sessions(2)
    await h.cb(3,f'block:{sid}')
    assert not await h.db.active_sessions(2)
    assert not await h.db.available(2,3)


async def test_report_only_member_deduplicated(h):
    await h.prepare()
    sid=await h.session()
    await h.msg(2,'SHIKOYAT_MATNI')
    mapped=await h.db.one('SELECT * FROM relay_map WHERE chat_id=3 ORDER BY msg_id DESC')
    await h.cb(4,f'report:{sid}',mapped['msg_id'])
    assert not await h.db.one('SELECT * FROM reports')
    await h.cb(3,f'report:{sid}',mapped['msg_id'])
    await h.cb(3,f'report:{sid}',mapped['msg_id'])
    assert len(await h.db.all('SELECT * FROM reports'))==1
    assert len(h.sent(1,'copyMessage'))==1
    assert 'SHIKOYAT_MATNI' not in str(await h.db.all('SELECT * FROM logs'))


async def test_revoke_expiry_and_non_owner(h):
    await h.prepare()
    await h.draft()
    link=await h.db.one('SELECT * FROM links')
    await h.cb(4,f'revoke:{link["token"]}')
    assert (await h.db.one('SELECT * FROM links'))['status']=='new'
    await h.cb(2,f'revoke:{link["token"]}')
    assert (await h.db.claim(link['token'],3,3600))[0]=='invalid'
    await h.draft()
    link=await h.db.one('SELECT * FROM links ORDER BY created_at DESC')
    await h.db.run('UPDATE links SET created_at=0 WHERE token=?',(link['token'],))
    assert (await h.db.claim(link['token'],3,3600))[0]=='invalid'
    assert (await h.db.one('SELECT * FROM links WHERE token=?',(link['token'],)))['status']=='expired'


async def test_idle_closed_before_relay(h):
    await h.prepare()
    sid=await h.session()
    await h.db.run('UPDATE sessions SET last_activity=0 WHERE id=?',(sid,))
    await h.msg(2,'Eskirgan')
    assert not await h.db.active_sessions(2)
    assert not h.sent(3,'copyMessage')


async def test_stop_restart_and_closed_reply(h):
    await h.prepare()
    sid=await h.session()
    mapped=await h.db.one('SELECT * FROM relay_map WHERE chat_id=2')
    await h.msg(3,'/stop')
    assert not await h.db.active_sessions(2)
    await h.msg(3,'Oddiy xabar')
    assert (await h.db.one('SELECT * FROM users WHERE tg_id=3'))['active']==0
    await h.msg(2,'Yopilgan suhbat',reply=mapped['msg_id'])
    assert not h.sent(3,'copyMessage')
    await h.msg(3,'/start')
    assert (await h.db.one('SELECT * FROM users WHERE tg_id=3'))['active']==1


async def test_forbidden_closes_sessions(h):
    await h.prepare()
    await h.session()
    h.fail[('copyMessage',3)]=403
    await h.msg(2,'Yetkazib bo‘lmaydi')
    assert (await h.db.one('SELECT * FROM users WHERE tg_id=3'))['active']==0
    assert not await h.db.active_sessions(2)


async def test_upstream_failure_does_not_kill_bot_or_open_session(h):
    await h.prepare()
    mid=await h.draft(target=3)
    h.fail[('sendPhoto',3)]=500
    await h.cb(3,f'view:{mid}')
    assert not await h.db.active_sessions(3)
    assert (await h.db.one('SELECT * FROM messages WHERE id=?',(mid,)))['status']=='approved'
    await h.cb(3,f'view:{mid}')
    assert await h.db.active_sessions(3)
    await h.msg(3,'/help')
    assert '/yangi' in h.sent(3)[-1]['text']


async def test_hourly_limit_atomic_and_duplicate_source(h):
    await h.prepare()
    mids=await asyncio.gather(*(h.db.draft(2,'file','',i) for i in range(20,40)))
    assert sum(x is not None for x in mids)==10
    assert len(await h.db.all('SELECT * FROM messages'))==10
    first=await h.db.one('SELECT * FROM messages LIMIT 1')
    assert await h.db.draft(2,'file','',first['source_msg_id'])==first['id']


async def test_restart_recovers_consent_and_routing(h):
    await h.prepare()
    mid=await h.draft(target=3)
    h.app=App(h.bot,DB(h.db.path),h.cfg,'test_agent_bot')
    h.dp=dispatcher(h.app)
    await h.msg(3,'/kirishlar')
    await h.cb(3,f'view:{mid}')
    h.app=App(h.bot,DB(h.db.path),h.cfg,'test_agent_bot')
    h.dp=dispatcher(h.app)
    await h.msg(2,'Restartdan keyin')
    assert len(h.sent(3,'copyMessage'))==1


async def test_admin_panels_pagination_and_global_block(h):
    await h.prepare()
    for uid in range(10,20): await h.msg(uid,'/start')
    await h.session()
    for action in ('admin','users:0','users:1','links:0','logs','reviews:0','requests:0','asessions:0'):
        await h.cb(1,action)
    await h.cb(1,'globalblock:3:1')
    assert not await h.db.active_sessions(2)
    assert not await h.db.available(2,3)
    await h.cb(1,'globalblock:3:0')
    assert await h.db.available(2,3)
    await h.cb(1,'globalblock:1:1')
    assert not (await h.db.one('SELECT * FROM users WHERE tg_id=1'))['is_blocked']
    assert not await h.db.one("SELECT * FROM logs WHERE action='xatolik'")


async def test_admin_bypasses_moderation_and_reject(h):
    await h.prepare(True)
    mid=await h.draft(1,3)
    assert (await h.db.one('SELECT * FROM messages WHERE id=?',(mid,)))['status']=='approved'
    mid=await h.draft(2,3)
    await h.cb(1,f'reject:{mid}')
    assert (await h.db.one('SELECT * FROM messages WHERE id=?',(mid,)))['status']=='rejected'
    await h.cb(3,f'view:{mid}')
    assert not h.sent(3,'sendPhoto')


async def test_telegram_429_retries_once(h):
    await h.prepare()
    await h.session()
    h.fail[('copyMessage',3)]=429
    await h.msg(2,'Tezlik cheklovi')
    assert len(h.sent(3,'copyMessage'))==2
    assert len(await h.db.active_sessions(2))==1
    assert not await h.db.one("SELECT * FROM logs WHERE action='xatolik'")


async def test_stop_suppresses_pending_notifications(h):
    await h.prepare(True)
    mid=await h.draft(2,3)
    await h.msg(2,'/stop')
    before=len(h.sent(2))
    await h.cb(1,f'reject:{mid}')
    assert len(h.sent(2))==before
    await h.msg(1,'/stop')
    before=len(h.sent(1,'sendPhoto'))
    await h.msg(2,'/start')
    await h.draft(2,3)
    assert len(h.sent(1,'sendPhoto'))==before


async def test_duplicate_callbacks_create_one_link_and_session(h):
    await h.prepare()
    await h.msg(2,photo=True)
    await h.msg(2,'Sinov sarlavhasi')
    await h.msg(2,'Sinov tavsifi')
    await h.cb(2,'target:1:0')
    await asyncio.gather(*(h.cb(2,'confirm:1') for _ in range(8)))
    assert len(await h.db.all('SELECT * FROM links'))==1
    link=await h.db.one('SELECT * FROM links')
    await h.msg(3,f'/start i_{link["token"]}')
    await asyncio.gather(*(h.cb(3,'view:1') for _ in range(8)))
    assert len(h.sent(3,'sendPhoto'))==1
    assert len(await h.db.active_sessions(2))==1
