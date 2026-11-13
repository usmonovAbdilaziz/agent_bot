"""Start only with a complete, separate staging configuration."""
import asyncio
import logging
import os
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
path = ROOT / '.env.test'
values = dotenv_values(path)
required = ('BOT_TOKEN', 'ADMIN_PHONE', 'DB_PATH', 'WEBAPP_URL', 'WEBAPP_PORT')
if any(not values.get(key) or 'REPLACE_' in values[key] for key in required):
    raise SystemExit('Complete BOT_TOKEN, ADMIN_PHONE, DB_PATH, WEBAPP_URL and WEBAPP_PORT in .env.test.')
database = Path(values['DB_PATH'])
database = (ROOT / database).resolve() if not database.is_absolute() else database.resolve()
if database == (ROOT / 'data/bot.sqlite3').resolve():
    raise SystemExit('Use a separate staging database, not data/bot.sqlite3.')
database.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
for key, value in values.items():
    if value is not None:
        os.environ[key] = value
os.environ['CONFIG_ENV_FILE'] = str(path)

from main import main
logging.basicConfig(level=logging.WARNING, format='%(asctime)s %(levelname)s %(message)s')
asyncio.run(main())
