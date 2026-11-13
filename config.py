from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
import os
import re
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parent

@dataclass
class Config:
    token: str
    admin_phone: str
    moderation: bool = True
    ttl: float = 48 * 3600
    idle: float = 24 * 3600
    db_path: str = str(ROOT / 'data/bot.sqlite3')
    webapp_url: str = ''
    webapp_port: int = 8080

    rsvp_max_responses: int = 500
    rsvp_rate_limit: int = 30
    enable_ceremony: bool = False
    media_concurrency: int = 4
    media_rate_limit: int = 120

    @classmethod
    def load(cls, env_file=None):
        load_dotenv(env_file or ROOT / '.env')
        token = os.getenv('BOT_TOKEN','').strip()
        phone = re.sub(r'\D','',os.getenv('ADMIN_PHONE',''))
        if not token or not phone:
            raise ValueError(".env faylida BOT_TOKEN va ADMIN_PHONE ni to'ldiring.")
        mode = os.getenv('MODERATION','on').lower()
        if mode not in ('on','off'):
            raise ValueError('MODERATION on yoki off bo‘lishi kerak.')
        ttl = float(os.getenv('LINK_TTL_HOURS','48')) * 3600
        idle = float(os.getenv('SESSION_IDLE_HOURS','24')) * 3600
        if ttl <= 0 or idle <= 0:
            raise ValueError('Muddatlar musbat son bo‘lishi kerak.')
        path = Path(os.getenv('DB_PATH','data/bot.sqlite3'))
        webapp_url = os.getenv('WEBAPP_URL','').strip().rstrip('/')
        if webapp_url:
            parsed = urlsplit(webapp_url)
            if parsed.scheme != 'https' or not parsed.netloc or parsed.query or parsed.fragment or parsed.username:
                raise ValueError('WEBAPP_URL ochiq HTTPS manzil bo‘lishi kerak, query va fragment qo‘shmang.')
        port = int(os.getenv('WEBAPP_PORT','8080'))
        if not 1 <= port <= 65535:
            raise ValueError('WEBAPP_PORT 1–65535 oralig‘ida bo‘lsin.')
        flag=os.getenv('ENABLE_CEREMONY','false').strip().lower()
        if flag not in ('true','false','1','0','on','off'): raise ValueError('ENABLE_CEREMONY true yoki false bo‘lishi kerak.')
        max_responses = int(os.getenv('RSVP_MAX_RESPONSES','500'))
        rate_limit = int(os.getenv('RSVP_RATE_LIMIT_PER_MINUTE','30'))
        media_concurrency=int(os.getenv('MEDIA_DOWNLOAD_CONCURRENCY','4'))
        media_rate_limit=int(os.getenv('MEDIA_RATE_LIMIT_PER_MINUTE','120'))
        if media_concurrency < 1 or media_rate_limit < 1: raise ValueError('Media limitlari musbat bo‘lishi kerak.')
        if max_responses < 1 or rate_limit < 1: raise ValueError('RSVP limitlari musbat bo‘lishi kerak.')
        return cls(token,phone,mode=='on',ttl,idle,str(path if path.is_absolute() else ROOT/path),webapp_url,port,max_responses,rate_limit,flag in ('true','1','on'),media_concurrency,media_rate_limit)
