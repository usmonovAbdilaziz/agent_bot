import pytest
from invitation_store import InvitationDB

class Interrupted(BaseException): pass

class FaultDB(InvitationDB):
    stage=None
    async def _migration_step(self,step):
        if step==self.stage: raise Interrupted(step)

async def legacy(db):
    await db.init()
    await db.run("INSERT INTO q_invites(id,sender,receiver,title,created_at) VALUES(1,1,2,'old',0)")
    await db.run('DROP TABLE q_rsvps')
    await db.run("CREATE TABLE q_rsvps(invite_id INTEGER PRIMARY KEY, attending INTEGER, guests INTEGER, responded_at REAL, receiver_name TEXT, notice_status TEXT)")
    await db.run("INSERT INTO q_rsvps VALUES(1,1,3,123,'Old','pending')")

@pytest.mark.parametrize('stage',['rename','create','insert','before_drop'])
async def test_atomic_interruption(tmp_path,stage):
    db=FaultDB(tmp_path/'db.sqlite');await legacy(db);db.stage=stage
    with pytest.raises(Interrupted): await db.init()
    db.stage=None;await db.init();await db.init()
    rows=await db.all('SELECT * FROM q_rsvps');assert len(rows)==1 and rows[0]['telegram_user_id']==2 and rows[0]['guests']==3
    assert not await db.one("SELECT 1 FROM sqlite_master WHERE name='q_rsvps_old'")

@pytest.mark.parametrize('state',['rename','create','insert'])
async def test_recover_previous_partial_migration(tmp_path,state):
    db=FaultDB(tmp_path/'db.sqlite');await legacy(db)
    await db.run('ALTER TABLE q_rsvps RENAME TO q_rsvps_old')
    if state in ('create','insert'):
        await db.run("CREATE TABLE q_rsvps(invite_id INTEGER NOT NULL,telegram_user_id INTEGER,attending INTEGER,guests INTEGER,responded_at REAL,receiver_name TEXT,notice_status TEXT,UNIQUE(invite_id,telegram_user_id))")
    if state=='insert': await db.run("INSERT INTO q_rsvps VALUES(1,2,1,3,123,'Old','pending')")
    await db.init();await db.init()
    rows=await db.all('SELECT * FROM q_rsvps');assert len(rows)==1 and rows[0]['telegram_user_id']==2 and rows[0]['guests']==3
    assert not await db.one("SELECT 1 FROM sqlite_master WHERE name='q_rsvps_old'")

@pytest.mark.parametrize('stage',['rename','create','insert','before_drop'])
async def test_process_kill_during_migration_restarts_without_loss(tmp_path,stage):
    import subprocess,sys
    from pathlib import Path
    db=InvitationDB(tmp_path/'crash.sqlite');await legacy(db)
    code='''import asyncio,os,sys\nfrom invitation_store import InvitationDB\nclass Fault(InvitationDB):\n async def _migration_step(self,step):\n  if step==sys.argv[2]: os._exit(91)\nasyncio.run(Fault(sys.argv[1]).init())\n'''
    result=subprocess.run([sys.executable,'-c',code,db.path,stage],cwd=Path(__file__).resolve().parents[1],timeout=30)
    assert result.returncode==91
    await db.init();await db.init()
    rows=await db.all('SELECT * FROM q_rsvps')
    assert len(rows)==1 and rows[0]['telegram_user_id']==2 and rows[0]['guests']==3
