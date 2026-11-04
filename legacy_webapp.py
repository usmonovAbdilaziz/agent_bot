"""Telegram Mini App HTTP qatlami. Imzo serverda tekshiriladi; token brauzerga berilmaydi."""
import io
import logging
import time
from pathlib import Path

from aiohttp import web
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile
from aiogram.utils.web_app import safe_parse_webapp_init_data

STATIC = Path(__file__).resolve().parent / 'web'
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


async def body(request):
    try:
        data = await request.json()
    except (ValueError, TypeError):
        raise ApiProblem('So‘rov ma’lumotlari noto‘g‘ri.')
    if not isinstance(data, dict):
        raise ApiProblem('So‘rov ma’lumotlari noto‘g‘ri.')
    return data


async def message_for(request):
    app = request.app[BOT_APP]
    try:
        mid = int(request.match_info['mid'])
    except (ValueError, KeyError):
        raise ApiProblem('Rasm topilmadi.', 404)
    m = await app.db.one('SELECT * FROM messages WHERE id=?', (mid,))
    if not m or request['uid'] not in (m['sender_tg_id'], m['receiver_tg_id']):
        raise ApiProblem('Bu rasm mavjud emas yoki sizga tegishli emas.', 404)
    return m


async def serialize(app, m, uid):
    owner = uid == m['sender_tg_id']
    sender = await app.db.one('SELECT first_name FROM users WHERE tg_id=?', (m['sender_tg_id'],))
    result = {
        'id': m['id'], 'title': m['title'], 'description': m['description'],
        'status': m['status'], 'sender_name': sender['first_name'] if sender else '',
        'owner': owner, 'can_view': owner or m['status'] in ('approved','delivered'),
    }
    if owner:
        link = await app.db.one('SELECT token,status FROM links WHERE message_id=?', (m['id'],))
        if link:
            result['link'] = f"https://t.me/{app.username}?start=i_{link['token']}"
            result['link_status'] = link['status']
    session = await app.db.one('SELECT id,status FROM sessions WHERE message_id=?', (m['id'],))
    if session:
        result['session'] = session
    return result


async def me(request):
    app = request.app[BOT_APP]
    return web.json_response({'name': request['user']['first_name'], 'bot_url': f'https://t.me/{app.username}',
                              'is_admin': request['uid']==await app.admin()})


async def listing(request):
    app, uid = request.app[BOT_APP], request['uid']
    rows = await app.db.all('''SELECT * FROM messages WHERE sender_tg_id=? OR
      (receiver_tg_id=? AND status IN ('approved','delivered')) ORDER BY id DESC LIMIT 50''', (uid, uid))
    return web.json_response({'messages': [await serialize(app,m,uid) for m in rows]})


async def upload(request):
    app, uid = request.app[BOT_APP], request['uid']
    if request.content_type != 'multipart/form-data':
        raise ApiProblem('Rasm, sarlavha va tavsifni to‘ldiring.')
    reader = await request.multipart()
    values, image, total = {}, None, 0
    async for part in reader:
        chunks = bytearray()
        while True:
            chunk = await part.read_chunk()
            if not chunk:
                break
            total += len(chunk)
            if total > 10*1024*1024:
                raise ApiProblem('Rasm va matnlar hajmi 10 MB dan oshmasin.',413)
            chunks.extend(chunk)
            if part.name != 'photo' and len(chunks)>10000:
                raise ApiProblem('Matn juda uzun.')
        if part.name=='photo':
            if image is not None:
                raise ApiProblem('Faqat bitta rasm tanlang.')
            image = bytes(chunks)
        elif part.name in ('title','description'):
            try:
                values[part.name] = chunks.decode('utf-8').strip()
            except UnicodeDecodeError:
                raise ApiProblem('Matn formati noto‘g‘ri.')
    title, description = values.get('title',''), values.get('description','')
    if not 1<=len(title)<=120 or not 1<=len(description)<=2000:
        raise ApiProblem('Sarlavha 1–120, tavsif 1–2000 belgidan iborat bo‘lsin.')
    if not image or not (image.startswith(b'\xff\xd8\xff') or image.startswith(b'\x89PNG\r\n\x1a\n')):
        raise ApiProblem('JPG yoki PNG rasm tanlang.')
    async with app.lock:
        count = await app.db.one('SELECT count(*) n FROM messages WHERE sender_tg_id=? AND created_at>?',(uid,time.time()-3600))
        if count['n']>=10:
            raise ApiProblem('Bir soatda 10 ta yangi rasm yuborish mumkin.',429)
        # Telegram file_id olish uchun rasm avval faqat yuboruvchining o'z chatiga
        # yuklanadi. Brauzer fayli server diskiga saqlanmaydi.
        sent = await app.call(uid,app.bot.send_photo,photo=BufferedInputFile(image,filename='photo.jpg'),
                              caption='Rasm tayyorlanmoqda. Davomini ochiq sahifada to‘ldiring.',disable_notification=True)
        if not sent or not sent.photo:
            raise ApiProblem('Telegram rasmni qabul qilmadi. /start ni tekshiring.',502)
        mid = await app.db.draft(uid,sent.photo[-1].file_id,'',sent.message_id)
        if mid is None:
            raise ApiProblem('Bir soatda 10 ta yangi rasm yuborish mumkin.',429)
        await app.db.metadata(mid,uid,title,description)
        await app.db.run('DELETE FROM message_inputs WHERE tg_id=?',(uid,))
        try:
            await app.call(uid,app.bot.delete_message,message_id=sent.message_id)
        except TelegramAPIError:
            pass
        return web.json_response(await serialize(app,await app.db.one('SELECT * FROM messages WHERE id=?',(mid,)),uid),status=201)


async def people(request):
    app,uid = request.app[BOT_APP],request['uid']
    rows = await app.db.all('''SELECT tg_id,first_name FROM users u WHERE tg_id!=? AND active=1 AND is_blocked=0
      AND NOT EXISTS(SELECT 1 FROM pair_blocks b WHERE (b.blocker=? AND b.blocked=u.tg_id)
        OR (b.blocker=u.tg_id AND b.blocked=?)) ORDER BY first_name,tg_id LIMIT 100''',(uid,uid,uid))
    return web.json_response({'people':rows})


async def detail(request):
    app = request.app[BOT_APP]
    async with app.lock:
        await app.cleanup()
        m = await message_for(request)
        if request['uid'] != m['sender_tg_id'] and m['status'] not in ('approved','delivered'):
            raise ApiProblem('Rasm hali tasdiqlanmagan yoki rad etilgan.', 409)
        return web.json_response(await serialize(app,m,request['uid']))


async def update_metadata(request):
    app, uid = request.app[BOT_APP], request['uid']
    data = await body(request)
    title, description = data.get('title'), data.get('description')
    if not isinstance(title,str) or not isinstance(description,str):
        raise ApiProblem('Sarlavha va tavsifni to‘ldiring.')
    async with app.lock:
        m = await message_for(request)
        try:
            changed = await app.db.metadata(m['id'],uid,title,description)
        except ValueError as exc:
            raise ApiProblem(str(exc))
        if not changed:
            raise ApiProblem('Faqat o‘zingizning yuborilmagan rasmingizni tahrirlashingiz mumkin.',409)
        await app.db.run('DELETE FROM message_inputs WHERE tg_id=? AND message_id=?',(uid,m['id']))
        m = await message_for(request)
        return web.json_response(await serialize(app,m,uid))


async def submit(request):
    app, uid = request.app[BOT_APP], request['uid']
    data = await body(request)
    if data.get('confirmed') is not True:
        raise ApiProblem('Yuborishdan oldin rozilikni belgilang.')
    target = data.get('receiver_id',0)
    if type(target) is not int or target < 0:
        raise ApiProblem('Oluvchi noto‘g‘ri tanlangan.')
    async with app.lock:
        m = await message_for(request)
        if uid != m['sender_tg_id']:
            raise ApiProblem('Bu rasm sizga tegishli emas.',403)
        if m['status']=='draft':
            if not m['title'].strip() or not m['description'].strip():
                raise ApiProblem('Avval sarlavha va tavsifni to‘ldiring.')
            if target and not await app.db.available(uid,target):
                raise ApiProblem('Bu oluvchi hozir mavjud emas.',409)
            await app.db.run('UPDATE messages SET receiver_tg_id=?,mode=? WHERE id=?',
                             (target or None,'direct' if target else 'link',m['id']))
            await app.sender_callback(uid,['confirm',str(m['id'])])
        elif m['status']=='approved' and m['mode']=='link' and not await app.db.one('SELECT 1 FROM links WHERE message_id=?',(m['id'],)):
            await app.publish(m['id'])
        return web.json_response(await serialize(app,await message_for(request),uid))


async def accept(request):
    app, uid = request.app[BOT_APP], request['uid']
    async with app.lock:
        await app.cleanup()
        m = await message_for(request)
        if uid != m['receiver_tg_id']:
            raise ApiProblem('Faqat oluvchi rasmni qabul qilishi mumkin.',403)
        if not await app.db.available(uid,m['sender_tg_id']):
            raise ApiProblem('Bu suhbat hozir mavjud emas.',409)
        if m['status']=='approved':
            sid = await app.db.delivered(m,None)
            await app.db.log(uid,'suhbat_ochildi',sid)
            await app.announce(sid)
        elif m['status']!='delivered':
            raise ApiProblem('Rasm hali tasdiqlanmagan yoki rad etilgan.',409)
        return web.json_response(await serialize(app,await message_for(request),uid))


async def decline(request):
    app, uid = request.app[BOT_APP], request['uid']
    async with app.lock:
        m = await message_for(request)
        if uid != m['receiver_tg_id']:
            raise ApiProblem('Faqat oluvchi rad etishi mumkin.',403)
        await app.receiver_callback(uid,m['id'],'decline')
        return web.json_response({'ok':True})


async def photo(request):
    app, uid = request.app[BOT_APP], request['uid']
    m = await message_for(request)
    if uid != m['sender_tg_id']:
        if m['status'] not in ('approved','delivered') or not await app.db.available(uid,m['sender_tg_id']):
            raise ApiProblem('Bu rasm hozir mavjud emas.',403)
    file = await app.bot.get_file(m['file_id'])
    if not file.file_path or (file.file_size and file.file_size>20*1024*1024):
        raise ApiProblem('Rasmni olishning imkoni bo‘lmadi.',502)
    buffer = io.BytesIO()
    await app.bot.download_file(file.file_path,destination=buffer)
    # Telegram photo fayli JPEG bo‘ladi. Tokenli URL hech qachon klientga chiqmaydi.
    return web.Response(body=buffer.getvalue(),content_type='image/jpeg')


async def page(request):
    return web.FileResponse(STATIC/'index.html')


async def healthz(request):
    ready = bool(getattr(request.app[BOT_APP], 'ready', False))
    return web.json_response({'ready': ready}, status=200 if ready else 503)


def create_web_app(app):
    server = web.Application(middlewares=[protect],client_max_size=11*1024*1024)
    server[BOT_APP] = app
    server.router.add_get('/',page)
    server.router.add_get('/healthz',healthz)
    server.router.add_get('/api/me',me)
    server.router.add_get('/api/people',people)
    server.router.add_get('/api/messages',listing)
    server.router.add_post('/api/messages',upload)
    server.router.add_get('/api/messages/{mid}',detail)
    server.router.add_patch('/api/messages/{mid}',update_metadata)
    server.router.add_post('/api/messages/{mid}/submit',submit)
    server.router.add_post('/api/messages/{mid}/accept',accept)
    server.router.add_post('/api/messages/{mid}/decline',decline)
    server.router.add_get('/api/messages/{mid}/photo',photo)
    if STATIC.exists():
        server.router.add_static('/assets',STATIC,show_index=False)
    return server


async def start_web_app(app):
    runner = web.AppRunner(create_web_app(app),access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner,'127.0.0.1',app.cfg.webapp_port).start()
    except BaseException:
        await runner.cleanup()
        raise
    return runner
