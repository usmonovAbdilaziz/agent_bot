import sqlite3
import subprocess
import sys
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[1]/'scripts'/'sqlite_safe_backup.py'

def init(path,value):
    with sqlite3.connect(path) as c:
        c.executescript('CREATE TABLE settings(v); CREATE TABLE users(v); CREATE TABLE q_invites(v);')
        c.execute('INSERT INTO q_invites VALUES(?)',(value,))

def run(*args): return subprocess.run([sys.executable,str(SCRIPT),*map(str,args)],capture_output=True,text=True)
def value(path):
    with sqlite3.connect(path) as c: return c.execute('SELECT v FROM q_invites').fetchone()[0]

def test_verified_backup_and_restore(tmp_path):
    current=tmp_path/'current.db'; backup=tmp_path/'backup.db'; safety=tmp_path/'safety.db'
    init(current,'before'); assert run('backup',current,backup).returncode==0
    with sqlite3.connect(current) as c: c.execute("UPDATE q_invites SET v='after'")
    assert run('restore',backup,current,'--safety',safety).returncode==0
    assert value(current)=='before' and value(safety)=='after'
    assert run('restore',backup,current,'--safety',safety).returncode!=0

def test_missing_corrupt_or_invalid_backup_cannot_replace_target(tmp_path):
    current=tmp_path/'current.db'; init(current,'protected')
    missing=tmp_path/'missing.db'; safety=tmp_path/'safety.db'
    assert run('restore',missing,current,'--safety',safety).returncode!=0
    assert not missing.exists() and not safety.exists() and value(current)=='protected'
    invalid=tmp_path/'invalid.db'; sqlite3.connect(invalid).close()
    assert run('restore',invalid,current,'--safety',safety).returncode!=0
    assert not safety.exists() and value(current)=='protected'
