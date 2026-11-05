import os
import subprocess
import sys
import time
from pathlib import Path
import pytest
from config import Config
from invitation_store import InvitationDB
from test_minimal import n,api
from test_open_link import make_open

async def test_flag_disabled_skips_type_and_rejects_stale_ceremony_callbacks(n):
    n.cfg.enable_ceremony=False
    await n.cb(1,'q:self'); flow=await n.db.flow(1); mid=flow['invite_id']
    assert flow['stage']=='media' and (await n.db.invite(mid))['type']=='fun'
    await n.cb(1,f'q:ctype:{mid}:ceremony')
    assert (await n.db.invite(mid))['type']=='fun' and (await n.db.flow(1))['stage']=='media'
    assert 'o‘chirilgan' in n.sent(1)[-1]['text']

async def test_flag_enabled_and_existing_ceremony_works_when_disabled(n,api):
    item=await make_open(n); mid=item['id']; n.cfg.enable_ceremony=False
    await n.msg(2,f'/start i_{item["token"]}')
    assert (await api('GET',f'/api/invites/{mid}',uid=2))[0]==200
    status,data=await api('POST',f'/api/invites/{mid}/rsvp',uid=2,json={'attending':1,'guests':2})
    assert status==200 and data['rsvp']['guests']==2

async def test_flag_disabled_preserves_ceremony_draft_and_blocks_callbacks(n):
    from test_ceremony import start
    mid=await start(n); before=dict(await n.db.invite(mid)); flow=dict(await n.db.flow(1))
    n.cfg.enable_ceremony=False
    await n.msg(1,'test'); await n.cb(1,f'q:cevent:{mid}:wedding'); await n.cb(1,f'q:confirm:{mid}')
    assert dict(await n.db.invite(mid))==before and dict(await n.db.flow(1))==flow

def test_flag_default_disabled(monkeypatch,tmp_path):
    monkeypatch.setenv('BOT_TOKEN','123456:test'); monkeypatch.setenv('ADMIN_PHONE','998900000000'); monkeypatch.delenv('ENABLE_CEREMONY',raising=False)
    assert not Config.load(tmp_path/'absent.env').enable_ceremony

@pytest.mark.parametrize('raw,expected',[('true',True),('1',True),('on',True),('false',False),('0',False),('off',False)])
def test_flag_env(monkeypatch,raw,expected):
    monkeypatch.setenv('BOT_TOKEN','123456:test'); monkeypatch.setenv('ADMIN_PHONE','998900000000'); monkeypatch.setenv('ENABLE_CEREMONY',raw)
    assert Config.load().enable_ceremony is expected

async def test_legacy_code_runs_against_new_schema(tmp_path):
    db=InvitationDB(tmp_path/'new.sqlite'); await db.init()
    await db.run("INSERT INTO q_invites(id,sender,receiver,title,description,status,token,created_at,expires_at) VALUES(1,1,2,'old','text','ready','legacy-token',?,?)",(time.time(),time.time()+3600))
    await db.run("INSERT INTO q_rsvps(invite_id,telegram_user_id,attending,guests,responded_at,receiver_name,notice_status) VALUES(1,2,1,1,1,'Test','sent')")
    fixture=Path(__file__).parent/'fixtures'/'m7_legacy'
    code="import asyncio,sys; from invitation_store import InvitationDB; db=InvitationDB(sys.argv[1]); asyncio.run(db.init()); assert asyncio.run(db.claim('legacy-token',2))==1; assert asyncio.run(db.accept(1,2))"
    result=subprocess.run([sys.executable,'-c',code,str(tmp_path/'new.sqlite')],cwd=fixture,env={**os.environ,'PYTHONPATH':str(fixture.resolve())},capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert (await db.one('SELECT guests FROM q_rsvps WHERE invite_id=1'))['guests']==1
