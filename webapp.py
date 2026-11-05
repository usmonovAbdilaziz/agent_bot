"""Receiver-only Mini App API. Acceptance never starts a relay session."""
import io
import time
import asyncio
from collections import OrderedDict
from aiohttp import web
from designs import valid_design
from invitation_store import parse_details, valid_ceremony_details
from web_common import BOT_APP, STATIC, ApiProblem, protect, page, healthz

MAX_MEDIA=20*1024*1024
PHOTO_CACHE_BYTES=16*1024*1024
PHOTO_CACHE_ITEM_BYTES=2*1024*1024
PHOTO_CACHE_ENTRIES=64
PHOTO_CACHE_TTL=15*60
PHOTO_CACHE=web.AppKey('photo_cache', object)
PHOTO_LOCK=web.AppKey('photo_lock', object)

class PhotoCache:
    def __init__(self):
        self.items=OrderedDict()
        self.size=0

    def get(self, key):
        entry=self.items.get(key)
        if entry is None: return None
        if entry[0]<=time.monotonic():
            self.remove(key)
            return None
        self.items.move_to_end(key)
        return entry[1]

    def put(self, key, data):
        if len(data)>PHOTO_CACHE_ITEM_BYTES: return
        self.remove(key)
        while self.items and (self.size+len(data)>PHOTO_CACHE_BYTES or len(self.items)>=PHOTO_CACHE_ENTRIES):
            self.remove(next(iter(self.items)))
        timer=asyncio.get_running_loop().call_later(PHOTO_CACHE_TTL,self.remove,key)
        self.items[key]=(time.monotonic()+PHOTO_CACHE_TTL,data,timer)
        self.size+=len(data)

    def remove(self,key):
        entry=self.items.pop(key,None)
        if entry:
            entry[2].cancel()
            self.size-=len(entry[1])

    def clear(self):
        for key in list(self.items): self.remove(key)

async def invite_for(request):
    app=request.app[BOT_APP]
    try: mid=int(request.match_info['mid'])
    except ValueError: raise ApiProblem('Taklif topilmadi.',404)
    item=await app.db.invite(mid)
    if not item or request['uid'] not in (item['sender'],item['receiver']):
        raise ApiProblem('Taklif topilmadi.',404)
    answered = item['type']=='ceremony' and request['uid']==item['receiver'] and await app.db.one('SELECT 1 FROM q_rsvps WHERE invite_id=?',(item['id'],))
    if request['uid']!=item['sender'] and not answered and item['status']!='accepted' and (
            item['status']!='ready' or item['expires_at']<=time.time()):
        raise ApiProblem('Taklif muddati tugagan.',409)
    return item

async def detail(request):
    item=await invite_for(request)
    details = parse_details(item['details'])
    if details is None or (item['type']=='ceremony' and not valid_ceremony_details(details,complete=True)):
        raise ApiProblem('Taklif ma’lumotlari noto‘g‘ri.',409)
    details['layout'] = {**details.get('layout', {}), 'text_position': details.get('layout', {}).get('text_position', 'bottom')}
    design = item['design'] if valid_design(item['design'], item['type']) else ('ceremony_elegant' if item['type']=='ceremony' else 'classic')
    response = await request.app[BOT_APP].db.one('SELECT attending,guests,responded_at FROM q_rsvps WHERE invite_id=?',(item['id'],)) if item['type']=='ceremony' else None
    return web.json_response({k:item[k] for k in ('id','title','description','media_kind','status')} | {
        'design':design,
        'type':item['type'], 'details':details,
        'preview':request['uid']==item['sender'], 'rsvp':dict(response) if response else None})

class BoundedBuffer(io.BytesIO):
    def write(self, data):
        if self.tell()+len(data)>MAX_MEDIA:
            raise ApiProblem('Media 20 MB dan katta.',413)
        return super().write(data)

async def media(request):
    app=request.app[BOT_APP]
    item=await invite_for(request)
    if item['media_kind']=='none': raise ApiProblem('Media yo‘q.',404)
    if item['media_kind']=='photo':
        async with request.app[PHOTO_LOCK]:
            item=await invite_for(request)
            data=request.app[PHOTO_CACHE].get(item['file_id'])
            if data is None:
                data=await download_media(app,item['file_id'])
                request.app[PHOTO_CACHE].put(item['file_id'],data)
        return web.Response(body=data,content_type='image/jpeg')
    data=await download_media(app,item['file_id'])
    return web.Response(body=data,content_type='video/mp4')

async def download_media(app,file_id):
    file=await app.bot.get_file(file_id)
    if not file.file_path or file.file_size is None or file.file_size>MAX_MEDIA:
        raise ApiProblem('Mediani yuklab bo‘lmadi.',502)
    buffer=BoundedBuffer()
    await app.bot.download_file(file.file_path,destination=buffer)
    return buffer.getvalue()

async def accept(request):
    app=request.app[BOT_APP]
    try:
        payload = await request.json() if request.can_read_body else {}
    except ValueError:
        raise ApiProblem('Javob formati noto‘g‘ri.',400)
    count = payload.get('no_attempts',0) if isinstance(payload,dict) else None
    if type(count) is not int or not 0 <= count <= 1000000:
        raise ApiProblem('Urinishlar soni noto‘g‘ri.',400)
    # Serialize invitation completion with bot updates; new links remain independent.
    async with app.lock:
        item=await invite_for(request)
        if request['uid']!=item['receiver']: raise ApiProblem('Faqat oluvchi tasdiqlaydi.',403)
        async with request.app[PHOTO_LOCK]:
            if not await app.db.accept(item['id'],request['uid'],count):
                raise ApiProblem('Taklifni qabul qilib bo‘lmadi.',409)
            if item['media_kind']=='photo': request.app[PHOTO_CACHE].remove(item['file_id'])
    await app.notify_acceptance(item['id'])
    return web.json_response({'accepted':True})

async def rsvp(request):
    app=request.app[BOT_APP]
    try: payload=await request.json()
    except (ValueError,TypeError): raise ApiProblem('Javob formati noto‘g‘ri.',400)
    if not isinstance(payload,dict): raise ApiProblem('Javob formati noto‘g‘ri.',400)
    attending=payload.get('attending'); guests=payload.get('guests')
    if type(attending) is not int or attending not in (0,1) or type(guests) is not int or (attending==1 and not 1<=guests<=10) or (attending==0 and guests not in (0,1)):
        raise ApiProblem('Javob yoki mehmonlar soni noto‘g‘ri.',400)
    person=request['telegram_user']
    name=' '.join(filter(None,[person.first_name,person.last_name])) or 'Oluvchi'
    async with app.lock:
        item=await invite_for(request)
        if item['receiver']!=request['uid']: raise ApiProblem('Faqat oluvchi javob beradi.',403)
        if item['type']!='ceremony': raise ApiProblem('Bu taklifda RSVP mavjud emas.',409)
        async with request.app[PHOTO_LOCK]:
            response=await app.db.rsvp(item['id'],request['uid'],attending,guests if attending else 0,name)
            if response is None: raise ApiProblem('Javobni saqlab bo‘lmadi.',409)
            if item['media_kind']=='photo': request.app[PHOTO_CACHE].remove(item['file_id'])
    await app.notify_rsvp(item['id'])
    return web.json_response({'rsvp':response})

@web.middleware
async def media_policy(request, handler):
    response=await handler(request)
    response.headers['Content-Security-Policy']=(
        "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self'; "
        "img-src 'self' blob:; media-src 'self' blob:; connect-src 'self'; base-uri 'none'; object-src 'none'; form-action 'none'")
    return response

def create_web_app(app):
    server=web.Application(middlewares=[media_policy,protect],client_max_size=16384)
    server[BOT_APP]=app
    server[PHOTO_CACHE]=PhotoCache()
    server[PHOTO_LOCK]=app.photo_lock
    app.photo_cache=server[PHOTO_CACHE]
    async def clear_cache(application):
        application[PHOTO_CACHE].clear()
    server.on_cleanup.append(clear_cache)
    server.router.add_get('/',page)
    server.router.add_get('/healthz',healthz)
    server.router.add_get('/api/invites/{mid}',detail)
    server.router.add_get('/api/invites/{mid}/media',media)
    server.router.add_post('/api/invites/{mid}/accept',accept)
    server.router.add_post('/api/invites/{mid}/rsvp',rsvp)
    server.router.add_static('/assets',STATIC,show_index=False)
    return server

async def start_web_app(app):
    runner=web.AppRunner(create_web_app(app),access_log=None)
    await runner.setup()
    try: await web.TCPSite(runner,'127.0.0.1',app.cfg.webapp_port).start()
    except BaseException:
        await runner.cleanup()
        raise
    return runner
