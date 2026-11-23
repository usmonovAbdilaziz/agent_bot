import asyncio
from datetime import datetime
from main import App
from test_minimal import n, api
from test_meeting import meeting_ready, response

async def scheduled(n, api):
    item = await meeting_ready(n)
    payload = response()
    status, _ = await api('POST', f'/api/invites/{item["id"]}/accept', json={'meeting_response':payload})
    assert status == 200
    return item['id'], datetime.fromisoformat(payload['when']).timestamp()

def reminders(n, uid):
    return [m for m in n.sent(uid) if 'Uchrashuv eslatmasi' in m.get('text','')]

async def test_reminders_due_for_both_once_across_restart(n, api):
    mid, when = await scheduled(n,api)
    await n.app.send_meeting_reminders(when-3601)
    assert not reminders(n,1) and not reminders(n,2)
    await asyncio.gather(n.app.send_meeting_reminders(when-3600),n.app.send_meeting_reminders(when-3600))
    assert len(reminders(n,1)) == len(reminders(n,2)) == 1
    assert '60 daqiqa' in reminders(n,1)[0]['text']
    assert 'O‘zbekiston' in reminders(n,2)[0]['text']
    n.app = App(n.bot,n.db,n.cfg,'test_agent_bot')
    await n.db.init()
    await n.app.send_meeting_reminders(when-3500)
    assert len(reminders(n,1)) == len(reminders(n,2)) == 1
    assert len(await n.db.all("SELECT * FROM q_meeting_reminders WHERE status='sent'")) == 2

async def test_reminder_failure_retries_only_failed_recipient(n, api, monkeypatch):
    mid, when = await scheduled(n,api)
    original = n.app.send
    failed = False
    async def send(uid,text,**kwargs):
        nonlocal failed
        if uid == 1 and not failed:
            failed=True
            raise OSError('temporary outage')
        return await original(uid,text,**kwargs)
    monkeypatch.setattr(n.app,'send',send)
    await n.app.send_meeting_reminders(when-3600)
    assert not reminders(n,1) and len(reminders(n,2))==1
    await n.app.send_meeting_reminders(when-3590)
    assert not reminders(n,1)
    await n.app.send_meeting_reminders(when-3540)
    assert len(reminders(n,1))==len(reminders(n,2))==1

async def test_late_reminder_and_blocked_recipient(n, api):
    mid, when=await scheduled(n,api)
    await n.db.run('UPDATE users SET is_blocked=1 WHERE tg_id=2')
    await n.app.send_meeting_reminders(when-1200)
    assert '20 daqiqa' in reminders(n,1)[0]['text']
    assert not reminders(n,2)
    row=await n.db.one('SELECT status FROM q_meeting_reminders WHERE uid=2 AND invite_id=?',(mid,))
    assert row['status']=='unavailable'

async def test_expired_meeting_never_sends_and_pending_lease_recovers(n, api):
    mid, when=await scheduled(n,api)
    await n.app.send_meeting_reminders(when-4000)
    await n.db.run('UPDATE q_meeting_reminders SET retry_at=?',(when-3500,))
    await n.app.send_meeting_reminders(when-3600)
    assert not reminders(n,1)
    await n.app.send_meeting_reminders(when)
    assert not reminders(n,1) and not reminders(n,2)
    assert all(r['status']=='expired' for r in await n.db.all('SELECT status FROM q_meeting_reminders'))
