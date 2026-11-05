"""Telegram Mini App HTTP qatlami. Imzo serverda tekshiriladi; token brauzerga berilmaydi."""
import logging
import time
from pathlib import Path

from aiohttp import web
from aiogram.exceptions import TelegramAPIError
from aiogram.utils.web_app import safe_parse_webapp_init_data

STATIC = Path(__file__).resolve().parent / 'web_minimal'
BOT_APP = web.AppKey('bot_app', object)


class ApiProblem(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


@web.middleware
async def protect(request, handler):
    try:
        if request.path.startswith('/api/'):
            app = request.app[BOT_APP]
            raw = request.headers.get('X-Telegram-Init-Data', '')
            if not raw or len(raw) > 16384:
                raise ApiProblem('Sahifani Telegram botidagi tugma orqali oching.', 401)
            try:
                signed = safe_parse_webapp_init_data(token=app.cfg.token, init_data=raw)
            except (ValueError, TypeError):
                raise ApiProblem('Telegram tasdig‘i yaroqsiz. Sahifani botdan qayta oching.', 401)
            age = time.time() - signed.auth_date.timestamp()
            if not signed.user or age < -30 or age > 3600:
                raise ApiProblem('Kirish muddati tugadi. Sahifani botdan qayta oching.', 401)
            await app.db.register(signed.user)
            user = await app.db.one('SELECT * FROM users WHERE tg_id=?', (signed.user.id,))
            if user['is_blocked'] or not user['active']:
                raise ApiProblem('Botda xabar olish o‘chirilgan yoki foydalanish cheklangan. /start ni tekshiring.', 403)
            request['uid'] = signed.user.id
            request['user'] = user
            request['telegram_user'] = signed.user
        response = await handler(request)
    except ApiProblem as exc:
        response = web.json_response({'error': exc.message}, status=exc.status)
    except web.HTTPException as exc:
        if request.path.startswith('/api/'):
            response = web.json_response({'error': 'So‘rov bajarilmadi. Ma’lumotni tekshirib qayta urinib ko‘ring.'}, status=exc.status)
        else:
            response = exc
    except TelegramAPIError as exc:
        logging.warning('Mini App Telegram xatosi: %s', type(exc).__name__)
        response = web.json_response({'error': 'Telegram vaqtincha javob bermadi. Qayta urinib ko‘ring.'}, status=502)
    except Exception as exc:
        logging.error('Mini App xatosi: %s', type(exc).__name__)
        response = web.json_response({'error': 'Amal bajarilmadi. Keyinroq qayta urinib ko‘ring.'}, status=500)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self'; "
        "img-src 'self' blob:; connect-src 'self'; base-uri 'none'; object-src 'none'; form-action 'self'")
    return response


async def page(request):
    return web.FileResponse(STATIC/'index.html')


async def healthz(request):
    ready = bool(getattr(request.app[BOT_APP], 'ready', False))
    return web.json_response({'ready': ready}, status=200 if ready else 503)
