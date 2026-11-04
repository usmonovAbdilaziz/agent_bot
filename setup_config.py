"""First-run console setup, executed only inside the prepared virtual environment."""
import getpass
import os
from pathlib import Path
import re
import sys

from dotenv import load_dotenv, set_key

ROOT = Path(__file__).resolve().parent


def valid_setting(key, value):
    if key == 'BOT_TOKEN':
        return bool(re.fullmatch(r'\d+:[A-Za-z0-9_-]{20,}', value))
    if key == 'ADMIN_PHONE':
        return bool(re.fullmatch(r'\+?[\d ()-]+', value)) and 8 <= len(re.sub(r'\D', '', value)) <= 15
    return bool(value) and not any(c.isspace() for c in value)


def prepare_config():
    dotenv = ROOT / '.env'
    if not dotenv.exists():
        dotenv.write_text((ROOT / '.env.example').read_text(encoding='utf-8'), encoding='utf-8')
        if os.name != 'nt':
            dotenv.chmod(0o600)
    load_dotenv(dotenv)
    prompts = (
        ('BOT_TOKEN', 'BotFather bergan BOT_TOKEN (yozuv ko‘rinmaydi): ', True),
        ('ADMIN_PHONE', 'Admin telefon raqami, masalan +998901234567: ', False),
    )
    for key, prompt, secret in prompts:
        value = os.getenv(key, '').strip()
        while not valid_setting(key, value):
            if not sys.stdin.isatty():
                raise RuntimeError(f'.env faylida {key} ni to‘ldiring yoki start.bat ni oching.')
            if secret:
                print(f'{key}: kiritilgan belgilar ko‘rinmaydi; joylashtiring va Enter bosing.', flush=True)
            value = (getpass.getpass(prompt) if secret else input(prompt)).strip()
            if not value:
                raise RuntimeError(f'{key} kiritilmadi. start.bat ni qayta oching.')
            if not valid_setting(key, value):
                print(f'{key} formati noto‘g‘ri. Qayta kiriting.', flush=True)
                continue
            if key == 'ADMIN_PHONE':
                value = '+' + re.sub(r'\D', '', value)
            set_key(dotenv, key, value)
            os.environ[key] = value
