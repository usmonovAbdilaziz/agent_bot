"""Wedding invitation validation and replaceable image template."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont, ImageOps

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
    """Render the selected invitation with bounded, dynamically fitted text."""
    floral = design == 'wedding_floral'
    artwork = 'ivory-floral.png' if floral else 'marble-gold.png'
    with Image.open(ASSETS / artwork) as source:
        image = ImageOps.fit(source.convert('RGB'), (720, 1280), method=Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)
    regular, bold = ASSETS / 'DejaVuSans.ttf', ASSETS / 'DejaVuSans-Bold.ttf'
    serif = ASSETS / 'DejaVuSerif.ttf'
    ink, gold = '#252323', '#907257'

    def wrapped(text, font, width):
        lines = []
        current = ''
        for word in text.split():
            candidate = (current + ' ' + word).strip()
            if draw.textlength(candidate, font=font) <= width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ''
            # A single long word still needs to fit within the card.
            for char in word:
                if current and draw.textlength(current + char, font=font) > width:
                    lines.append(current)
                    current = ''
                current += char
        if current:
            lines.append(current)
        return lines or ['']

    def text_box(text, box, size, *, strong=False, font_path=None, color=ink):
        left, top, right, bottom = box
        width, height = right - left, bottom - top
        path = font_path or (bold if strong else regular)
        for font_size in range(size, 8, -1):
            font = ImageFont.truetype(str(path), font_size)
            lines = wrapped(text, font, width)
            line_height = round(font_size * 1.3)
            if len(lines) * line_height <= height:
                break
        y = top + (height - len(lines) * line_height) / 2
        for line in lines:
            draw.text(((left + right) / 2, y), line, font=font, fill=color, anchor='mt')
            y += line_height

    date = parse_date(data['date'])
    month_year = f'{MONTHS[date.month - 1].capitalize()} {date.year}'
    if floral:
        text_box('TO‘Y TAKLIFNOMASI', (120, 155, 600, 210), 25, font_path=serif, color=gold)
        text_box(data['groom'], (130, 463, 320, 540), 30, strong=True)
        text_box('&', (325, 466, 395, 538), 30, font_path=serif, color=gold)
        text_box(data['bride'], (400, 463, 590, 540), 30, strong=True)
        text_box('Sizni nikoh to‘yimizga taklif etamiz', (160, 570, 560, 642), 22, font_path=serif)
        text_box('SANA', (190, 680, 530, 706), 15, color=gold)
        text_box(f'{date.day} {month_year}', (180, 711, 540, 754), 28, strong=True)
        text_box(f'{WEEKDAYS[date.weekday()]}  ·  {data["time"]}', (180, 769, 540, 811), 22)
        text_box('MANZIL', (190, 850, 530, 875), 15, color=gold)
        text_box(data['address'], (164, 890, 556, 1040), 23, strong=True)
    else:
        text_box('TO‘Y TAKLIFNOMASI', (120, 170, 600, 220), 27, font_path=serif, color=gold)
        text_box(data['groom'], (140, 268, 580, 340), 42, strong=True)
        text_box('&', (300, 341, 420, 395), 34, font_path=serif, color=gold)
        text_box(data['bride'], (140, 396, 580, 468), 42, strong=True)
        text_box('Sizni hayotimizdagi eng baxtiyor kun — nikoh to‘yimizga taklif etamiz.',
                 (135, 505, 585, 610), 22, font_path=serif)
        draw.line((127, 662, 270, 662), fill=gold, width=2)
        draw.line((450, 662, 593, 662), fill=gold, width=2)
        text_box(data['time'], (130, 675, 265, 720), 23, strong=True)
        text_box(str(date.day), (285, 650, 435, 732), 48, strong=True)
        text_box(WEEKDAYS[date.weekday()], (450, 675, 590, 720), 21, strong=True)
        draw.line((127, 730, 270, 730), fill=gold, width=2)
        draw.line((450, 730, 593, 730), fill=gold, width=2)
        text_box(month_year, (215, 744, 505, 790), 26, strong=True)
        text_box('MANZIL', (108, 842, 382, 876), 16, color=gold)
        text_box(data['address'], (105, 880, 383, 1070), 23, strong=True)
    output = BytesIO()
    image.save(output, 'PNG', optimize=True)
    return output.getvalue()
