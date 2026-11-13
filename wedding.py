"""Wedding invitation validation and replaceable image template."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parent / 'wedding_assets'
UZ_TZ = timezone(timedelta(hours=5))
MONTHS = ('yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr')
WEEKDAYS = ('Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba')
FIELDS = ('groom', 'bride', 'date', 'time', 'address')


def parse_date(value):
    return datetime.strptime(value, '%d.%m.%Y').date()


def validate_field(field, value):
    value = ' '.join(value.split())
    if field in ('groom', 'bride'):
        if not 1 <= len(value) <= 60: raise ValueError('Ism 1–60 belgidan iborat bo‘lsin.')
    elif field == 'address':
        if not 1 <= len(value) <= 160: raise ValueError('Manzil 1–160 belgidan iborat bo‘lsin.')
    elif field == 'date':
        try: date = parse_date(value)
        except ValueError: raise ValueError('Sanani KK.OO.YYYY shaklida kiriting, masalan 12.11.2027.')
        if date < datetime.now(UZ_TZ).date(): raise ValueError('Kelajakdagi sanani kiriting.')
        value = date.strftime('%d.%m.%Y')
    elif field == 'time':
        try: value = datetime.strptime(value, '%H:%M').strftime('%H:%M')
        except ValueError: raise ValueError('Vaqtni SS:DD shaklida kiriting, masalan 17:00.')
    else:
        raise ValueError('Noma’lum maydon.')
    return value


def validated_details(raw):
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        result = {field: validate_field(field, data[field]) for field in FIELDS if field != 'date'}
        result['date'] = parse_date(data['date']).strftime('%d.%m.%Y')
        return result
    except (ValueError, KeyError, TypeError):
        return None


def expires_at(data):
    date = parse_date(data['date'])
    return datetime(date.year, date.month, date.day, 23, 59, 59, tzinfo=UZ_TZ).timestamp()


def render_wedding(data, design='wedding_classic'):
    """Draw a neutral initial template; replace background/layout when artwork is supplied."""
    image = Image.new('RGB', (720, 1280), '#eee9e1')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((36, 36, 684, 1244), radius=300, fill='#fcfaf6', outline='#c6ad91', width=3)
    draw.rounded_rectangle((47, 47, 673, 1233), radius=290, outline='#e8dbc9', width=2)
    regular, bold = ASSETS / 'DejaVuSerif.ttf', ASSETS / 'DejaVuSerif-Bold.ttf'

    def center(text, y, max_width=560, size=32, strong=False, color='#514339'):
        font_path = bold if strong else regular
        while size > 9:
            font = ImageFont.truetype(str(font_path), size)
            if draw.textbbox((0, 0), text, font=font)[2] <= max_width: break
            size -= 1
        draw.text((360, y), text, fill=color, font=font, anchor='mt')

    center('TO‘Y TAKLIFNOMASI', 155, size=26)
    draw.polygon([(360,230),(371,241),(360,252),(349,241)], fill='#bd9a73')
    draw.line((270,241,335,241), fill='#d8c4aa', width=2)
    draw.line((385,241,450,241), fill='#d8c4aa', width=2)
    center(data['groom'], 330, size=53, strong=True)
    center('&', 408, size=38, color='#bd9a73')
    center(data['bride'], 475, size=53, strong=True)
    center('Sizni to‘y marosimimizga taklif etamiz', 610, size=25)
    date = parse_date(data['date'])
    center(f"{date.day} {MONTHS[date.month - 1]} {date.year}", 720, size=34, strong=True)
    center(f"{WEEKDAYS[date.weekday()]}  ·  {data['time']}", 780, size=26)
    center('MANZIL', 900, size=20, color='#a18363')
    for size in range(25, 11, -1):
        font = ImageFont.truetype(str(regular), size)
        lines = ['']
        for word in data['address'].split():
            for char in word + ' ':
                if draw.textlength(lines[-1] + char, font=font) > 520:
                    lines.append('')
                lines[-1] += char
        if len(lines) <= 6: break
    for i, line in enumerate(lines): center(line.strip(), 945 + i * (size + 12), size=size)
    output = BytesIO()
    image.save(output, 'PNG', optimize=True)
    return output.getvalue()
