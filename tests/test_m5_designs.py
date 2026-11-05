import json
import pytest
from test_minimal import n, api
from test_ceremony import start, fill_to_map
from designs import DESIGNS

@pytest.mark.parametrize('design',['atlas','nafis','gold','envelope','ticket'])
async def test_ceremony_design_selection_preview_and_receiver(n,api,design):
    mid=await start(n); await fill_to_map(n,mid)
    await n.cb(1,f'q:cskip:{mid}'); await n.cb(1,f'q:cskip:{mid}')
    await n.msg(1,'Mehmon bo‘ling'); await n.cb(1,f'q:cskip:{mid}')
    await n.cb(1,f'q:clayout:{mid}:bottom')
    rows=json.loads(n.sent(1)[-1]['reply_markup'])['inline_keyboard']
    options=[b for row in rows for b in row if ':cdesign:' in b.get('callback_data','')]
    assert {b['callback_data'].split(':')[-1] for b in options}=={k for k,v in DESIGNS.items() if v['type']=='ceremony'}
    assert all(len(row)<=2 for row in rows)
    await n.cb(1,f'q:cdesign:{mid}:{design}'); await n.cb(1,f'q:cshare:{mid}:open')
    assert (await n.db.invite(mid))['design']==design
    status,preview=await api('GET',f'/api/invites/{mid}',uid=1)
    assert status==200 and preview['preview'] and preview['design']==design
    await n.cb(1,f'q:confirm:{mid}'); item=await n.db.invite(mid)
    await n.msg(2,f'/start i_{item["token"]}')
    status,received=await api('GET',f'/api/invites/{mid}',uid=2)
    assert status==200 and received['design']==design and received['share_mode']=='open'

async def test_old_ceremony_design_migrates_idempotently(n):
    await n.db.run("INSERT INTO q_invites(sender,title,created_at,type,design) VALUES(1,'old',0,'ceremony','ceremony_elegant')")
    await n.db.init(); await n.db.init()
    assert (await n.db.one("SELECT design FROM q_invites WHERE title='old'"))['design']=='nafis'
