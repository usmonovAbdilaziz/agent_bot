"""Receiver-only Mini App API. Acceptance never starts a relay session."""
import io
import time
import asyncio
from collections import OrderedDict
from aiohttp import web
from designs import DESIGNS, valid_design
from invitation_store import parse_details, valid_ceremony_details, ceremony_passed
from web_common import BOT_APP, STATIC, ApiProblem, protect, page, healthz

MAX_MEDIA=20*1024*1024
PHOTO_CACHE_BYTES=16*1024*1024
PHOTO_CACHE_ITEM_BYTES=2*1024*1024
PHOTO_CACHE_ENTRIES=64
PHOTO_CACHE_TTL=15*60
PHOTO_CACHE=web.AppKey('photo_cache', object)
PHOTO_LOCK=web.AppKey('photo_lock', object)
MEDIA_SEMAPHORE=web.AppKey('media_semaphore', object)
MEDIA_FLIGHTS=web.AppKey('media_flights', object)
MEDIA_RATES=web.AppKey('media_rates', object)

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
    permitted = item and (request['uid'] in (item['sender'],item['receiver']) or (item['type']=='ceremony' and item['share_mode']=='open' and await app.db.one('SELECT 1 FROM q_open_views WHERE invite_id=? AND telegram_user_id=?',(mid,request['uid']))))
    if not permitted:
        raise ApiProblem('Taklif topilmadi.',404)
    answered = item['type']=='ceremony' and await app.db.one('SELECT 1 FROM q_rsvps WHERE invite_id=? AND telegram_user_id=?',(item['id'],request['uid']))
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
    if item['design'] in DESIGNS and not valid_design(item['design'],item['type']): raise ApiProblem('Taklif dizayni turiga mos emas.',409)
    design = item['design'] if valid_design(item['design'], item['type']) else ('nafis' if item['type']=='ceremony' else 'classic')
    response = await request.app[BOT_APP].db.one('SELECT attending,guests,responded_at FROM q_rsvps WHERE invite_id=? AND telegram_user_id=?',(item['id'],request['uid'])) if item['type']=='ceremony' else None
    return web.json_response({k:item[k] for k in ('id','title','description','media_kind','status')} | {
        'design':design,
        'type':item['type'], 'share_mode':item['share_mode'], 'details':details,
        'preview':request['uid']==item['sender'], 'rsvp':dict(response) if response else None,
        'rsvp_closed':item['type']=='ceremony' and ceremony_passed(details)})

class BoundedBuffer(io.BytesIO):
    def write(self, data):
        if self.tell()+len(data)>MAX_MEDIA:
            raise ApiProblem('Media 20 MB dan katta.',413)
        return super().write(data)

async def media(request):
    app=request.app[BOT_APP]
    item=await invite_for(request)
    if item['media_kind']=='none': raise ApiProblem('Media yo‘q.',404)
    now=time.monotonic(); rates=request.app[MEDIA_RATES]
    for uid in list(rates):
        if rates[uid][-1]<=now-60: del rates[uid]
    times=rates.setdefault(request['uid'],[])
    times[:]=[t for t in times if t>now-60]
    if len(times)>=getattr(app.cfg,'media_rate_limit',120): raise ApiProblem('Media so‘rovlari juda ko‘p. Bir daqiqadan so‘ng qayta urinib ko‘ring.',429)
    times.append(now)
    cache=request.app[PHOTO_CACHE]; flights=request.app[MEDIA_FLIGHTS]; key=item['file_id']
    async with request.app[PHOTO_LOCK]:
        data=cache.get(key)
        if data is None:
            task=flights.get(key)
            if task is None:
                async def fetch():
                    async with request.app[MEDIA_SEMAPHORE]:
                        result=await download_media(app,key)
                    async with request.app[PHOTO_LOCK]: cache.put(key,result)
                    return result
                task=asyncio.create_task(fetch()); flights[key]=task
                def finish(done):
                    if flights.get(key) is done: flights.pop(key,None)
                    if not done.cancelled(): done.exception()
                task.add_done_callback(finish)
    if data is None: data=await asyncio.shield(task)
    content_type='image/jpeg' if item['media_kind']=='photo' else 'video/mp4'
    headers={'Accept-Ranges':'bytes'}
    range_header=request.headers.get('Range')
    if range_header:
        import re
        match=re.fullmatch(r'bytes=(\d*)-(\d*)',range_header.strip())
        if not match or (not match[1] and not match[2]):
            return web.Response(status=416,headers={'Content-Range':f'bytes */{len(data)}','Accept-Ranges':'bytes'})
        if match[1]:
            start=int(match[1]); end=min(int(match[2]) if match[2] else len(data)-1,len(data)-1)
        else:
            suffix=int(match[2]); start=max(0,len(data)-suffix); end=len(data)-1
        if start>=len(data) or start>end:
            return web.Response(status=416,headers={'Content-Range':f'bytes */{len(data)}','Accept-Ranges':'bytes'})
        headers['Content-Range']=f'bytes {start}-{end}/{len(data)}'
        return web.Response(status=206,body=memoryview(data)[start:end+1],content_type=content_type,headers=headers)
    return web.Response(body=data,content_type=content_type,headers=headers)

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
    now=time.monotonic()
    app.rsvp_requests={uid:times for uid,times in app.rsvp_requests.items() if times and now-times[-1]<60}
    times=app.rsvp_requests.setdefault(request['uid'],[])
    times[:]=[t for t in times if now-t<60]
    if len(times)>=app.cfg.rsvp_rate_limit: raise ApiProblem('So‘rovlar juda ko‘p. Bir daqiqadan so‘ng qayta urinib ko‘ring.',429)
    times.append(now)
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
        if item['sender']==request['uid'] or (item['share_mode']=='single' and item['receiver']!=request['uid']): raise ApiProblem('Faqat oluvchi javob beradi.',403)
        if item['type']!='ceremony': raise ApiProblem('Bu taklifda RSVP mavjud emas.',409)
        async with request.app[PHOTO_LOCK]:
            response=await app.db.rsvp(item['id'],request['uid'],attending,guests if attending else 0,name,app.cfg.rsvp_max_responses)
            if response=='passed': raise ApiProblem('Marosim o‘tib ketgan.',409,'rsvp_closed')
            if response=='limit': raise ApiProblem('Bu taklif uchun javoblar soni chegaraga yetdi.',409)
            if response is None: raise ApiProblem('Javobni saqlab bo‘lmadi.',409)
            if item['media_kind']=='photo': request.app[PHOTO_CACHE].remove(item['file_id'])
    await app.notify_rsvp(item['id'],request['uid'])
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
    server[MEDIA_SEMAPHORE]=asyncio.Semaphore(getattr(app.cfg,'media_concurrency',4))
    server[MEDIA_FLIGHTS]={}
    server[MEDIA_RATES]={}
    app.photo_cache=server[PHOTO_CACHE]
    async def clear_cache(application):
        for task in list(application[MEDIA_FLIGHTS].values()): task.cancel()
        if application[MEDIA_FLIGHTS]: await asyncio.gather(*list(application[MEDIA_FLIGHTS].values()),return_exceptions=True)
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
