"""Meeting wizard, real authenticated HTTP and atomic planning responses."""
import asyncio
from datetime import datetime, timedelta
import json
import pytest
from main import App, dispatcher
from meeting import slots, validate_response
from wedding import UZ_TZ
from test_minimal import n, api, draft


def future(days=2):
    return (datetime.now(UZ_TZ) + timedelta(days=days)).replace(second=0, microsecond=0)


async def meeting_draft(n, custom=False, verify_menu=True):
    mid = await draft(n)
    await n.cb(1, f'q:design:{mid}')
    if verify_menu: assert 'Uchrashuv' in n.sent(1)[-1]['reply_markup']
    await n.cb(1, f'q:style:{mid}:meeting')
    assert (await n.db.flow(1))['stage'] == 'meeting_recipient'
    await n.msg(1, 'Shaxzoda')
    await n.msg(1, 'Javohir')
    if custom:
        await n.cb(1, f'q:mskip:{mid}')
    else:
        await n.msg(1, '\n'.join(future(d).strftime('%d.%m.%Y %H:%M') for d in (2, 3, 4)))
    assert (await n.db.flow(1))['stage'] == 'preview'
    return mid


async def meeting_ready(n, custom=False, verify_menu=True):
    mid = await meeting_draft(n, custom, verify_menu)
    await n.cb(1, f'q:confirm:{mid}')
    item = await n.db.invite(mid)
    assert item['status'] == 'ready'
    await n.msg(2, f'/start i_{item["token"]}')
    return item


def response(when=None, **extra):
    return {'when': when or future().isoformat(timespec='minutes'), 'plan': 'coffee', 'note': 'Soatni kelishdik.', **extra}


async def test_meeting_setup_is_required_resumable_and_owner_only(n, api):
    mid = await draft(n)
    await n.cb(1, f'q:style:{mid}:meeting')
    assert await n.db.publish(mid, 1, n.cfg.ttl) is None
    await n.cb(2, f'q:mskip:{mid}')
    assert (await n.db.flow(1))['stage'] == 'meeting_recipient'
    await n.msg(1, 'Shaxzoda')
    await n.msg(1, 'Javohir')
    await n.msg(1, '31.02.2027 19:00')
    assert (await n.db.flow(1))['stage'] == 'meeting_slots'
    await n.msg(1, (datetime.now(UZ_TZ)-timedelta(days=1)).strftime('%d.%m.%Y %H:%M'))
    assert (await n.db.flow(1))['stage'] == 'meeting_slots'
    n.app = App(n.bot,n.db,n.cfg,'test_agent_bot'); n.dp = dispatcher(n.app)
    await n.msg(1,'/start'); await n.cb(1,'q:continue')
    assert '1–3 ta sana' in n.sent(1)[-1]['text']
    await n.cb(1, f'q:mskip:{mid}')
    details = json.loads((await n.db.invite(mid))['details'])
    assert {k:v for k,v in details.items() if k.startswith('meeting_')} == {'meeting_recipient':'Shaxzoda','meeting_sender':'Javohir','meeting_slots':[],'meeting_configured':True}
    await n.cb(2, f'q:meeting:{mid}')
    assert (await n.db.flow(1))['stage'] == 'preview'
    status, data = await api('GET', f'/api/invites/{mid}', uid=1)
    assert status == 200 and data['preview'] and data['details']['meeting_recipient']=='Shaxzoda'
    assert data['details']['meeting_response'] is None


@pytest.mark.parametrize('custom', [False, True])
async def test_full_meeting_choices_are_saved_and_notified_once(n, api, custom):
    item = await meeting_ready(n, custom)
    mid = item['id']; path = f'/api/invites/{mid}/accept'
    assert (await n.db.invite(mid))['status'] == 'ready'
    assert not await n.db.all('SELECT * FROM q_meeting_responses')
    assert (await api('POST',path,uid=1,json={'meeting_response':response()}))[0] == 403
    assert (await api('POST',path,uid=3,json={'meeting_response':response()}))[0] == 404
    assert (await api('POST',path,json={'no_attempts':4}))[0] == 400
    chosen = response(when=future(5).isoformat(timespec='minutes') if custom else json.loads(item['details'])['meeting_slots'][1],note='<b>Choy & suhbat</b>')
    before = len(n.sent(1))
    results = await asyncio.gather(*(api('POST',path,json={'no_attempts':4,'meeting_response':chosen}) for _ in range(3)))
    assert all(result == (200,{'accepted':True}) for result in results)
    assert len(n.sent(1)) == before + 1
    assert 'Qahva va uzoq suhbat' in n.sent(1)[-1]['text']
    assert '&lt;b&gt;Choy &amp; suhbat&lt;/b&gt;' in n.sent(1)[-1]['text']
    assert '4 marta' in n.sent(1)[-1]['text']
    stored = await n.db.one('SELECT * FROM q_meeting_responses WHERE invite_id=?',(mid,))
    assert stored['when_value'] == chosen['when'] and stored['note'] == chosen['note']
    assert len(await n.db.all('SELECT * FROM q_meeting_responses')) == 1
    assert (await n.db.invite(mid))['status'] == 'accepted'
    # A timeout retry cannot replace the original date, plan, note or evasion count.
    assert await api('POST',path,json={'meeting_response':response(plan='cinema'),'no_attempts':999}) == (200,{'accepted':True})
    assert await api('POST',path,json={}) == (200,{'accepted':True})
    await n.app.notify_acceptance(mid)
    assert len(n.sent(1)) == before + 1
    detail = (await api('GET',f'/api/invites/{mid}'))[1]
    assert detail['details']['meeting_response'] == chosen
    assert (await n.db.invite(mid))['no_attempts'] == 4


@pytest.mark.parametrize('changes', [
    {'plan':'unknown'}, {'note':'x'*301}, {'note':False}, {'when':'not-a-date'},
    {'when':'2020-01-01T19:00+05:00'}, {'when':'2026-12-25T19:00Z'},
])
async def test_invalid_meeting_choices_never_accept_or_notify(n, api, changes):
    item = await meeting_ready(n)
    before = len(n.sent(1))
    result = await api('POST',f'/api/invites/{item["id"]}/accept',json={'meeting_response':response(**changes)})
    assert result[0] == 400
    assert (await n.db.invite(item['id']))['status'] == 'ready'
    assert not await n.db.all('SELECT * FROM q_meeting_responses')
    assert not await n.db.all('SELECT * FROM q_accept_notices')
    assert len(n.sent(1)) == before


async def test_meeting_notice_recovers_with_saved_plan_after_failure(n,api):
    item=await meeting_ready(n)
    n.fail[('sendMessage',1)] = 500
    assert (await api('POST',f'/api/invites/{item["id"]}/accept',json={'meeting_response':response(plan='dinner')}))[0] == 200
    assert (await n.db.one('SELECT status FROM q_accept_notices'))['status']=='pending'
    restarted=App(n.bot,n.db,n.cfg,'test_agent_bot')
    await restarted.notify_acceptance(item['id'])
    assert (await n.db.one('SELECT status FROM q_accept_notices'))['status']=='sent'
    assert 'Ikki kishilik kechki ovqat' in n.sent(1)[-1]['text']


def test_meeting_time_validation():
    value=future().strftime('%d.%m.%Y %H:%M')
    assert len(slots(value)) == 1
    with pytest.raises(ValueError): slots(value+'\n'+value)
    with pytest.raises(ValueError): slots('not a date')
    assert validate_response(response())['plan']=='coffee'
    with pytest.raises(ValueError,match='bir yil'):
        validate_response(response(when=future(400).isoformat(timespec='minutes')))
