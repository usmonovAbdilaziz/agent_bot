"""Per-invitation receiving and one-link sender approvals through real Dispatcher."""
import asyncio
import pytest

from main import App, dispatcher
from test_minimal import n, api, draft, ready


async def request(n, uid=2):
    await n.msg(uid,'/start')
    await n.cb(uid,'q:request')
    await n.msg(uid,contact={'phone_number':f'+9989012345{uid:02d}','first_name':'User','user_id':uid})
    await n.cb(uid,'q:quota:1')
    return await n.db.one("SELECT * FROM q_sender_requests WHERE uid=? AND status='pending'",(uid,))


async def test_request_needs_confirmation_and_only_admin_can_approve(n):
    await n.msg(2,'/start')
    assert not await n.db.all('SELECT * FROM q_sender_requests')
    await n.cb(2,'q:later')
    assert not await n.db.all('SELECT * FROM q_sender_requests')
    row=await request(n)
    assert 'Sender bo‘lish so‘rovi' in n.sent(1)[-1]['text']
    assert 'Ism &lt;2&gt;' in n.sent(1)[-1]['text']
    count=len(n.sent(1))
    await n.cb(2,'q:request'); await n.msg(2,'/start')
    assert len(n.sent(1))==count
    assert len(await n.db.all('SELECT * FROM q_sender_requests'))==1
    await n.cb(2,f'q:approve:{row["id"]}'); await n.cb(3,f'q:deny:{row["id"]}')
    assert not await n.app.is_sender(2)
    assert await n.db.decide_sender(row['id'],2,True) is None
    await n.cb(1,f'q:approve:{row["id"]}')
    assert await n.app.is_sender(2)
    assert '1 ta taklif' in n.sent(2)[-1]['text']


async def test_one_approval_one_link_and_stale_buttons_cannot_regrant(n):
    row=await request(n)
    await n.cb(1,f'q:approve:{row["id"]}')
    mid=await draft(n,uid=2)
    await n.cb(2,f'q:confirm:{mid}')
    token=(await n.db.invite(mid))['token']
    assert token and not await n.app.is_sender(2)
    before=len(n.sent(2))
    await n.cb(2,f'q:confirm:{mid}')
    assert len(n.sent(2))==before
    await n.cb(1,f'q:approve:{row["id"]}')
    assert not await n.app.is_sender(2)
    await n.cb(2,'q:new')
    assert 'ro‘yxatdan' in n.sent(2)[-1]['text']
    assert await n.db.begin(2) is None
    assert len(await n.db.all('SELECT * FROM q_invites WHERE sender=2'))==1
    assert (await n.db.invite(mid))['token']==token
    next_request=await request(n)
    assert next_request['id']!=row['id']
    await n.cb(1,f'q:approve:{next_request["id"]}')
    newer=await draft(n,uid=2)
    await n.cb(2,f'q:confirm:{newer}')
    assert (await n.db.invite(newer))['token']!=token
    assert not await n.app.is_sender(2)


async def test_denied_request_new_request_and_old_approve_cannot_override(n):
    row=await request(n)
    await n.cb(1,f'q:deny:{row["id"]}')
    assert 'rad etdi' in n.sent(2)[-1]['text']
    newer=await request(n)
    await n.cb(1,f'q:approve:{row["id"]}')
    assert not await n.app.is_sender(2)
    assert (await n.db.one('SELECT * FROM q_sender_requests WHERE id=?',(newer['id'],)))['status']=='pending'


async def test_cancel_retains_permission_and_publish_is_atomic(n):
    row=await request(n)
    await n.cb(1,f'q:approve:{row["id"]}')
    await n.msg(2,'/start')
    await n.msg(2,'/cancel')
    assert await n.app.is_sender(2)
    mid=await draft(n,uid=2)
    results=await asyncio.gather(*(n.db.publish(mid,2,3600) for _ in range(3)))
    assert len({r['token'] for r in results})==1
    assert not await n.app.is_sender(2)
    assert await n.db.begin(2) is None


async def test_permission_is_enforced_at_publish_even_with_existing_draft(n):
    row=await request(n)
    await n.cb(1,f'q:approve:{row["id"]}')
    mid=await draft(n,uid=2)
    await n.db.run('DELETE FROM q_senders WHERE uid=2')
    assert await n.db.publish(mid,2,3600) is None
    assert (await n.db.invite(mid))['status']=='draft'


async def test_failed_link_delivery_recovers_after_permission_consumed(n):
    row=await request(n)
    await n.cb(1,f'q:approve:{row["id"]}')
    mid=await draft(n,uid=2)
    n.fail[('sendMessage',2)]=500
    await n.cb(2,f'q:confirm:{mid}')
    item=await n.db.invite(mid)
    assert item['token'] and not item['link_sent'] and not await n.app.is_sender(2)
    n.app=App(n.bot,n.db,n.cfg,'test_agent_bot'); n.dp=dispatcher(n.app)
    await n.msg(2,'/start')
    assert item['token'] in n.sent(2)[-1]['text']
    assert (await n.db.invite(mid))['link_sent']
    assert not await n.app.is_sender(2)


async def test_pending_and_decision_notifications_recover_on_restart(n):
    n.fail[('sendMessage',1)]=500
    row=await request(n)
    assert not row['admin_notified']
    n.app=App(n.bot,n.db,n.cfg,'test_agent_bot'); n.dp=dispatcher(n.app)
    await n.cb(1,'q:requests')
    assert f'q:approve:{row["id"]}' in n.sent(1)[-1]['reply_markup']
    n.fail[('sendMessage',2)]=500
    await n.cb(1,f'q:approve:{row["id"]}')
    assert await n.app.is_sender(2)
    assert not (await n.db.one('SELECT * FROM q_sender_requests WHERE id=?',(row['id'],)))['decision_notified']
    restarted=App(n.bot,n.db,n.cfg,'test_agent_bot')
    await restarted.notify_sender_request(row['id'])
    assert 'Admin 1 ta' in n.sent(2)[-1]['text']
    await n.msg(2,'/start')
    assert (await n.db.flow(2))['stage']=='media'


async def test_new_deep_link_preserves_sender_draft_and_previous_receiver_history(n,api):
    old=await ready(n)
    await n.msg(2,f'/start i_{old["token"]}')
    assert (await api('POST',f'/api/invites/{old["id"]}/accept'))[0]==200
    row=await request(n)
    await n.cb(1,f'q:approve:{row["id"]}')
    mid=await draft(n,uid=2)
    flow=dict(await n.db.flow(2))
    newer=await ready(n)
    await n.msg(2,f'/start i_{newer["token"]}')
    assert 'Taklifni ochish' in n.sent(2)[-1]['reply_markup']
    assert dict(await n.db.flow(2))==flow
    assert (await api('POST',f'/api/invites/{newer["id"]}/accept'))[0]==200
    await n.msg(2,'/start')
    assert f'q:confirm:{mid}' in n.sent(2)[-1]['reply_markup']
    assert await n.app.is_sender(2)


async def test_previous_plain_start_user_can_receive_fresh_link(n):
    await n.msg(2,'/start')
    item=await ready(n)
    await n.msg(2,f'/start i_{item["token"]}')
    assert (await n.db.invite(item['id']))['receiver']==2
    assert 'Taklifni ochish' in n.sent(2)[-1]['reply_markup']


async def test_phone_grant_is_consumed_and_contact_replay_does_not_renew(n):
    await n.cb(1,'q:phone'); await n.msg(1,'+998901234567')
    await n.msg(2,'/start')
    contact={'phone_number':'+998901234567','first_name':'Own','user_id':2}
    await n.msg(2,contact=contact)
    assert not await n.db.all('SELECT * FROM q_phone_grants')
    mid=await draft(n,uid=2)
    await n.cb(2,f'q:confirm:{mid}')
    await n.msg(2,contact=contact)
    assert not await n.app.is_sender(2)
    assert not await n.db.flow(2)
    await n.cb(1,'q:phone'); await n.msg(1,'+998901234567')
    assert await n.app.is_sender(2)
    assert not await n.db.all('SELECT * FROM q_phone_grants')


async def test_migration_preserves_drafts_and_retires_old_bound_phone_grants(n):
    await n.msg(2,'/start')
    await n.db.run('INSERT INTO q_senders VALUES(2)')
    mid=await draft(n,uid=2)
    await n.db.run("UPDATE q_profiles SET phone_hash='old-bound' WHERE uid=2")
    await n.db.run("INSERT INTO q_phone_grants VALUES('old-bound')")
    await n.db.run("INSERT INTO q_phone_grants VALUES('not-yet-bound')")
    await n.db.run("DELETE FROM settings WHERE key='q_one_link_permissions'")
    await n.db.init(); await n.db.init()
    assert await n.app.is_sender(2)
    assert (await n.db.invite(mid))['status']=='draft'
    assert [r['phone_hash'] for r in await n.db.all('SELECT * FROM q_phone_grants')]==['not-yet-bound']


async def test_blocked_user_cannot_request_or_be_approved(n):
    row=await request(n)
    await n.db.run('UPDATE users SET is_blocked=1 WHERE tg_id=2')
    await n.cb(1,f'q:approve:{row["id"]}')
    assert not await n.app.is_sender(2)
    before=len(n.sent(1))
    await n.cb(2,'q:request')
    assert len(n.sent(1))==before


@pytest.mark.parametrize('quantity',[1,10,30])
async def test_registration_contact_quota_and_atomic_consumption(n,quantity):
    await n.msg(2,'/start')
    await n.cb(2,'q:request')
    assert not await n.db.all('SELECT * FROM q_sender_requests')
    await n.msg(2,contact={'phone_number':'+998901234567','first_name':'Other','user_id':3})
    await n.cb(2,f'q:quota:{quantity}')
    assert not await n.db.all('SELECT * FROM q_sender_requests')
    await n.msg(2,contact={'phone_number':'+998901234567','first_name':'Own','user_id':2})
    await n.cb(2,f'q:quota:{quantity}')
    row=await n.db.one("SELECT * FROM q_sender_requests WHERE uid=2 AND status='pending'")
    assert row['quantity']==quantity and row['phone']=='+998901234567'
    assert f'{quantity} ta' in n.sent(1)[-1]['text']
    await n.cb(1,f'q:approve:{row["id"]}')
    await n.cb(1,f'q:approve:{row["id"]}')
    assert (await n.db.one('SELECT remaining FROM q_sender_credits WHERE uid=2'))['remaining']==quantity
    for _ in range(quantity):
        mid=await n.db.begin(2)
        await n.db.run("UPDATE q_invites SET description='Test' WHERE id=?",(mid,))
        outcomes=await asyncio.gather(n.db.publish(mid,2,3600),n.db.publish(mid,2,3600))
        assert outcomes[0]['token']==outcomes[1]['token']
    assert not await n.app.is_sender(2)
    assert await n.db.begin(2) is None


async def test_suggestion_approval_adds_one_credit_once_and_preserves_draft(n):
    row=await request(n)
    await n.cb(1,f'q:approve:{row["id"]}')
    mid=await draft(n,uid=2)
    await n.msg(2,'/taklif')
    await n.msg(2,'Botga yangi g‘oya')
    suggestion=await n.db.one('SELECT * FROM q_suggestions WHERE uid=2')
    assert 'Botga yangi g‘oya' in n.sent(1)[-1]['text']
    await n.cb(3,f'q:idea_yes:{suggestion["id"]}')
    assert (await n.db.one('SELECT remaining FROM q_sender_credits WHERE uid=2'))['remaining']==1
    await n.cb(1,f'q:idea_yes:{suggestion["id"]}')
    await n.cb(1,f'q:idea_yes:{suggestion["id"]}')
    assert (await n.db.one('SELECT remaining FROM q_sender_credits WHERE uid=2'))['remaining']==2
    assert (await n.db.invite(mid))['status']=='draft'
    assert '1 ta havola' in n.sent(2)[-1]['text']


async def test_suggestion_requires_verified_contact_and_deny_does_not_grant(n):
    await n.msg(3,'/taklif')
    assert not await n.db.one('SELECT * FROM q_suggestion_drafts WHERE uid=3')
    await request(n)
    await n.msg(2,'/taklif')
    await n.msg(2,'Bir fikr')
    suggestion=await n.db.one('SELECT * FROM q_suggestions WHERE uid=2')
    await n.cb(1,f'q:idea_no:{suggestion["id"]}')
    assert not await n.app.is_sender(2)
    assert (await n.db.one('SELECT * FROM q_suggestions WHERE id=?',(suggestion['id'],)))['status']=='denied'
