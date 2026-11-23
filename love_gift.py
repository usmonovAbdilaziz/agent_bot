"""Configuration and secret-code helpers for the optional love-gift design."""
import hashlib
import hmac
import re
import secrets
from urllib.parse import urlsplit

DESIGN = 'love_gift'
MUSIC_HOSTS = {'open.spotify.com', 'music.apple.com', 'music.youtube.com',
               'www.youtube.com', 'youtube.com', 'youtu.be', 't.me'}


def code_hash(code):
    if not re.fullmatch(r'[0-9]{4}', code):
        raise ValueError('Kod aynan 4 ta raqamdan iborat bo‘lsin. Masalan: 1402')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', code.encode(), salt.encode(), 120_000).hex()
    return salt + ':' + digest


def check_code(code, stored):
    if not isinstance(code, str) or not re.fullmatch(r'[0-9]{4}', code):
        return False
    salt, _, expected = stored.partition(':')
    actual = hashlib.pbkdf2_hmac('sha256', code.encode(), salt.encode(), 120_000).hex()
    return hmac.compare_digest(actual, expected)


def music_url(value):
    value = value.strip()
    try:
        url = urlsplit(value)
        valid = (len(value) <= 500 and url.scheme == 'https' and url.hostname in MUSIC_HOSTS
                 and not url.username and not url.password and url.port in (None, 443)
                 and url.path not in ('', '/') and not any(c.isspace() for c in value))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Spotify, YouTube, Apple Music yoki Telegram musiqasining to‘liq HTTPS havolasini yuboring.')
    return value
