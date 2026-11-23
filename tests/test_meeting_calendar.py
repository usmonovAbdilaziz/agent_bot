"""Calendar export uses only frozen responses and narrowly scoped download links."""
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qs, urlencode
import time
import pytest
from test_minimal import n, api, ready
from test_meeting import meeting_ready, response
from meeting import calendar_signature


def target(url):
    value = urlsplit(url)
    return value.path + '?' + value.query


def changed(url, **values):
    value = urlsplit(url)
    params = {k: v[0] for k, v in parse_qs(value.query).items()}
    params.update(values)
    return value.path + '?' + urlencode(params)


async def test_calendar_exports_frozen_time_plan_and_unicode_safely(n, api):
    item = await meeting_ready(n)
    mid = item['id']
    assert (await api('POST', f'/api/invites/{mid}/calendar'))[0] == 409
    note = 'O‘zbekcha ♥, izoh; \\ ' + ('ko‘ngil ' * 25) + '\nBEGIN:VEVENT\nSUMMARY:injection'
    chosen = response(note=note)
    assert (await api('POST', f'/api/invites/{mid}/accept', json={'meeting_response': chosen}))[0] == 200
    before = len(n.sent(1))
    status, link = await api('POST', f'/api/invites/{mid}/calendar')
    assert status == 200 and link['file_name'] == f'uchrashuv-{mid}.ics'
    status, data = await api('GET', target(link['url']), auth='')
    assert status == 200 and data.startswith(b'BEGIN:VCALENDAR\r\n')
    assert all(len(line) <= 75 for line in data.split(b'\r\n'))
    assert data.decode('utf-8')  # folding never splits a UTF-8 codepoint
    unfolded = data.decode().replace('\r\n ', '')
    assert unfolded.count('\r\nBEGIN:VEVENT\r\n') == 1
    expected = datetime.fromisoformat(chosen['when']).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    assert f'DTSTART:{expected}\r\n' in unfolded
    assert 'SUMMARY:Uchrashuv — Qahva va uzoq suhbat\r\n' in unfolded
    assert 'O‘zbekcha ♥\\, izoh\\; \\\\ ' in unfolded
    assert '\\nBEGIN:VEVENT\\nSUMMARY:injection' in unfolded
    assert 'ATTENDEE:' not in unfolded and 'ORGANIZER:' not in unfolded
    assert 'DTEND:' not in unfolded  # no duration was supplied by the user
    assert (await api('GET', target(link['url']), auth='')) == (200, data)
    sender_link = (await api('POST', f'/api/invites/{mid}/calendar', uid=1))[1]
    assert (await api('GET', target(sender_link['url']), auth='')) == (200, data)
    assert (await api('POST', f'/api/invites/{mid}/calendar', uid=3))[0] == 404
    assert (await api('POST', f'/api/invites/{mid}/calendar', auth=''))[0] == 401
    assert len(n.sent(1)) == before
    assert len(await n.db.all('SELECT * FROM q_meeting_responses')) == 1


async def test_calendar_download_rejects_tampering_expiry_and_blocked_user(n, api):
    item = await meeting_ready(n)
    mid = item['id']
    await api('POST', f'/api/invites/{mid}/accept', json={'meeting_response': response()})
    link = (await api('POST', f'/api/invites/{mid}/calendar'))[1]['url']
    for path in (f'/files/meeting/{mid}.ics', changed(link, uid=3), changed(link, signature='x'*64),
                 changed(link, signature='♥'*64), target(link).replace(f'/meeting/{mid}.ics', f'/meeting/{mid+1}.ics')):
        assert (await api('GET', path, auth=''))[0] == 403
    for expires in (int(time.time())-1, int(time.time())+600):
        signature = calendar_signature(n.cfg.token, mid, 2, expires)
        assert (await api('GET', changed(link, expires=expires, signature=signature), auth=''))[0] == 403
    await n.db.run('UPDATE users SET is_blocked=1 WHERE tg_id=2')
    assert (await api('GET', target(link), auth=''))[0] == 404


async def test_calendar_unavailable_for_classic_and_old_unplanned_meeting(n, api):
    item = await ready(n)
    assert (await api('POST', f'/api/invites/{item["id"]}/calendar', uid=1))[0] == 409
    await n.msg(2, f'/start i_{item["token"]}')
    await api('POST', f'/api/invites/{item["id"]}/accept', json={})
    await n.db.run("UPDATE q_invites SET design='meeting' WHERE id=?", (item['id'],))
    assert (await api('POST', f'/api/invites/{item["id"]}/calendar'))[0] == 409
