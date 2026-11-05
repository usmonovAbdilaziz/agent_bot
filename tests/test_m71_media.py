import asyncio
import tracemalloc
import aiohttp
from aiohttp import web
from test_minimal import n,ready
from test_webapp import signed
from webapp import create_web_app
import webapp

async def server(n):
    runner=web.AppRunner(create_web_app(n.app));await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    return runner,f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'

async def test_100_parallel_media_singleflight_range_rate_and_memory(n,monkeypatch):
    item=await ready(n);mid=item['id'];await n.msg(2,f'/start i_{item["token"]}')
    await n.db.run("UPDATE q_invites SET media_kind='video',file_id='video' WHERE id=?",(mid,))
    n.cfg.media_rate_limit=100;n.cfg.media_concurrency=4
    calls=0; data=b'x'*(512*1024)
    async def download(app,key):
        nonlocal calls
        calls+=1;await asyncio.sleep(.5);return data
    monkeypatch.setattr(webapp,'download_media',download)
    runner,url=await server(n); headers={'X-Telegram-Init-Data':signed(n.cfg.token,2)}
    try:
        async with aiohttp.ClientSession() as client:
            async def get():
                async with client.get(url+f'/api/invites/{mid}/media',headers=headers) as response:
                    return response.status,len(await response.read())
            tracemalloc.start();baseline=tracemalloc.get_traced_memory()[0]
            results=await asyncio.gather(*(get() for _ in range(100)))
            peak=tracemalloc.get_traced_memory()[1]-baseline;tracemalloc.stop()
            print(f'100-media peak process+client tracemalloc growth: {peak/1024/1024:.2f} MiB')
            assert all(status==200 and length==len(data) for status,length in results) and calls==1
            async with client.get(url+f'/api/invites/{mid}/media',headers=headers) as r: assert r.status==429
            n.cfg.media_rate_limit=200
            for value,expected,body in [('bytes=0-9','bytes 0-9/524288',data[:10]),('bytes=-5','bytes 524283-524287/524288',data[-5:])]:
                async with client.get(url+f'/api/invites/{mid}/media',headers=headers|{'Range':value}) as r:
                    assert r.status==206 and r.headers['Content-Range']==expected and await r.read()==body
            async with client.get(url+f'/api/invites/{mid}/media',headers=headers|{'Range':'bytes=999999-'}) as r: assert r.status==416
    finally: await runner.cleanup()

async def test_media_global_semaphore(n,monkeypatch):
    item=await ready(n);await n.msg(2,f'/start i_{item["token"]}')
    for i in range(8):
        await n.db.run("INSERT INTO q_invites(id,sender,receiver,title,description,status,created_at,expires_at,media_kind,file_id) VALUES(?,1,2,'test','x','ready',0,?,'video',?)",(100+i,item['expires_at'],f'video{i}'))
    n.cfg.media_concurrency=4;active=0;maximum=0
    async def download(app,key):
        nonlocal active,maximum
        active+=1;maximum=max(maximum,active);await asyncio.sleep(.15);active-=1;return b'video'
    monkeypatch.setattr(webapp,'download_media',download);runner,url=await server(n);headers={'X-Telegram-Init-Data':signed(n.cfg.token,2)}
    try:
        async with aiohttp.ClientSession() as client:
            async def get(i):
                async with client.get(url+f'/api/invites/{100+i}/media',headers=headers) as r: return r.status
            assert all(x==200 for x in await asyncio.gather(*(get(i) for i in range(8))))
            assert maximum==4
    finally: await runner.cleanup()
