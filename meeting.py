"""Meeting configuration and receiver choices; all times use Uzbekistan time."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import hashlib
import hmac
from wedding import UZ_TZ, MONTHS, WEEKDAYS

PLANS = {p['id']: p['label'] for p in json.loads(
    (Path(__file__).resolve().parent / 'react_src/meeting-data.json').read_text())}


def name(value):
    if not isinstance(value, str):
        raise ValueError('Ismni matn ko‘rinishida kiriting.')
    value = ' '.join(value.split())
    if not 1 <= len(value) <= 120:
        raise ValueError('Ism 1–120 belgidan iborat bo‘lsin.')
    return value


def check_time(value, now=None):
    now = now or datetime.now(UZ_TZ)
    if value.tzinfo is None or value.utcoffset() != timedelta(hours=5):
        raise ValueError('Vaqtni O‘zbekiston vaqti bilan kiriting.')
    value = value.astimezone(UZ_TZ).replace(second=0, microsecond=0)
    if not now < value <= now + timedelta(days=366):
        raise ValueError('Kelgusi bir yil ichidagi, hali o‘tmagan vaqtni tanlang.')
    return value.isoformat(timespec='minutes')


def slots(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not 1 <= len(lines) <= 3:
        raise ValueError('1–3 ta vaqt kiriting, har biri alohida qatorda.')
    result = []
    for line in lines:
        try:
            value = datetime.strptime(line, '%d.%m.%Y %H:%M').replace(tzinfo=UZ_TZ)
        except ValueError:
            raise ValueError('Har bir qator KK.OO.YYYY SS:DD shaklida bo‘lsin. Masalan: 25.12.2026 19:00.') from None
        normalized = check_time(value)
        if normalized in result:
            raise ValueError('Bir xil vaqtni ikki marta kiritmang.')
        result.append(normalized)
    return result


def time_label(value):
    date = datetime.fromisoformat(value).astimezone(UZ_TZ)
    return f'{date.day}-{MONTHS[date.month-1]} {date.year}, {WEEKDAYS[date.weekday()]} · {date:%H:%M}'


def requires_plan(item):
    return item['design'] == 'meeting' and bool(json.loads(item['details']).get('meeting_configured'))


def validate_response(payload, now=None):
    if not isinstance(payload, dict):
        raise ValueError('Kun, vaqt va uchrashuv rejasini tanlang.')
    try:
        value = payload['when']
        if not isinstance(value, str) or len(value) > 40:
            raise ValueError
        date = datetime.fromisoformat(value)
    except (ValueError, KeyError, TypeError):
        raise ValueError('Kelajakdagi kun va vaqtni O‘zbekiston vaqti bilan tanlang.') from None
    when = check_time(date, now)
    plan = payload.get('plan')
    if not isinstance(plan, str) or plan not in PLANS:
        raise ValueError('Uchrashuv rejasini tanlang.')
    note = payload.get('note', '')
    if not isinstance(note, str) or len(note) > 300 or any(ord(c) < 32 and c not in '\n\t' for c in note):
        raise ValueError('Izoh 300 belgidan oshmasin.')
    return {'when': when, 'plan': plan, 'note': note.strip()}


def public_config(item):
    data = json.loads(item['details'])
    # Explicit allowlist; private fields belonging to other designs never leak.
    return {'meeting_kind': 'friendship' if data.get('meeting_kind') == 'friendship' else 'love',
            'meeting_recipient': data.get('meeting_recipient', item['title']),
            'meeting_sender': data.get('meeting_sender', ''),
            'meeting_slots': data.get('meeting_slots', []),
            'meeting_configured': bool(data.get('meeting_configured'))}


def calendar_signature(secret, mid, uid, expires):
    value = f'qadam-meeting-calendar-v1:{mid}:{uid}:{expires}'.encode()
    return hmac.new(secret.encode(), value, hashlib.sha256).hexdigest()


def calendar_file(item, response, namespace):
    """RFC 5545 event from the frozen response, with UTC times and UTF-8 folding."""
    config = public_config(item)
    def text(value):
        return str(value).replace('\\', '\\\\').replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')

    def fold(value):
        parts, line, size = [], '', 0
        for char in value:
            length = len(char.encode('utf-8'))
            if size + length > 75:
                parts.append(line)
                line, size = ' ', 1
            line += char
            size += length
        return '\r\n'.join(parts + [line])

    start = datetime.fromisoformat(response['when_value']).astimezone(timezone.utc)
    stamp = datetime.fromtimestamp(item['accepted_at'], timezone.utc)
    description = [f'O‘zbekiston vaqti: {time_label(response["when_value"])}',
                   f'Kimga: {config["meeting_recipient"]}']
    if config['meeting_sender']:
        description.append(f'Kimdan: {config["meeting_sender"]}')
    if response['note']:
        description.append(f'Izoh: {response["note"]}')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Qadam//Uchrashuv//UZ',
             'CALSCALE:GREGORIAN', 'BEGIN:VEVENT', f'UID:meeting-{item["id"]}@{namespace}.qadam',
             f'DTSTAMP:{stamp:%Y%m%dT%H%M%SZ}', f'DTSTART:{start:%Y%m%dT%H%M%SZ}',
             'SUMMARY:' + text('Uchrashuv — ' + PLANS[response['plan']]),
             'DESCRIPTION:' + text('\n'.join(description)), 'STATUS:CONFIRMED',
             'END:VEVENT', 'END:VCALENDAR']
    return ('\r\n'.join(fold(line) for line in lines) + '\r\n').encode('utf-8')
