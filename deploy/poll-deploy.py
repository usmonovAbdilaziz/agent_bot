#!/usr/bin/env python3
"""Install as a root systemd timer: deploy only verified main commits."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import Request, urlopen

BASE = Path('/home/ubuntu/apps/agent_bot')
REPO = BASE / 'repository'
STATE = BASE / 'deployed-commit'
API = 'https://api.github.com/repos/usmonovAbdilaziz/agent_bot'

def cmd(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)

def read_api(path):
    req = Request(API + path, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'qadam-deployer'})
    with urlopen(req, timeout=20) as response:
        return json.load(response)

def git(*args, **kwargs):
    return cmd('sudo', '-u', 'ubuntu', 'git', '-C', str(REPO), *args, **kwargs)

def health():
    try:
        with urlopen('http://127.0.0.1:18081/healthz', timeout=3) as response:
            return response.status == 200 and json.load(response).get('ready') is True
    except Exception:
        return False

with (BASE / 'deploy.lock').open('w') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    branch = read_api('/commits/main')['sha']
    if STATE.exists() and STATE.read_text().strip() == branch:
        print('Already deployed:', branch)
        raise SystemExit(0)
    runs = read_api('/actions/workflows/verify.yml/runs?branch=main&event=push&per_page=20')['workflow_runs']
    if not any(run['head_sha'] == branch and run['status'] == 'completed' and run['conclusion'] == 'success' for run in runs):
        print('Waiting for successful Verify run:', branch)
        raise SystemExit(0)
    status = git('status', '--porcelain', capture_output=True).stdout
    if status:
        raise SystemExit('Repository has local changes; refusing to deploy.')
    git('fetch', 'origin', 'main')
    fetched = git('rev-parse', 'FETCH_HEAD', capture_output=True).stdout.strip()
    if fetched != branch:
        raise SystemExit('main changed during verification; retry later.')
    git('checkout', '--detach', branch)
    image = 'qadam-agent:' + branch[:12]
    failed_name = 'qadam-agent-failed-' + branch[:12]
    if subprocess.run(['docker', 'inspect', failed_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        raise SystemExit('This commit previously failed deployment; manual review required.')
    cmd('docker', 'build', '-t', image, str(REPO))
    # A consistent backup is retained before starting code that might migrate SQLite.
    backup = '/app/data/backup-before-' + branch[:12] + '.sqlite3'
    cmd('docker', 'exec', 'qadam-agent', 'python', '-c',
        'import sqlite3,sys; a=sqlite3.connect("/app/data/bot.sqlite3"); b=sqlite3.connect(sys.argv[1]); a.backup(b); b.close(); a.close()', backup)
    previous = 'qadam-agent-previous'
    existing = subprocess.run(['docker', 'inspect', previous], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if existing.returncode == 0:
        raise SystemExit('Previous deployment container exists; manual review required.')
    cmd('docker', 'stop', '-t', '30', 'qadam-agent')
    cmd('docker', 'rename', 'qadam-agent', previous)
    try:
        cmd('docker', 'run', '-d', '--name', 'qadam-agent', '--restart', 'unless-stopped', '--network', 'host',
            '--env-file', str(BASE / '.env'), '-e', 'WEBAPP_URL=https://api.unumdor.uz/bot',
            '-e', 'WEBAPP_PORT=18081', '-e', 'DB_PATH=/app/data/bot.sqlite3',
            '-v', str(BASE / 'data') + ':/app/data', image)
        for _ in range(30):
            if health():
                break
            time.sleep(2)
        else:
            raise RuntimeError('New container did not become healthy')
        temporary = STATE.with_suffix('.tmp')
        temporary.write_text(branch + '\n')
        os.replace(temporary, STATE)
    except BaseException:
        subprocess.run(['docker', 'stop', '-t', '10', 'qadam-agent'], check=False)
        subprocess.run(['docker', 'rename', 'qadam-agent', failed_name], check=False)
        cmd('docker', 'rename', previous, 'qadam-agent')
        cmd('docker', 'start', 'qadam-agent')
        raise
    # Previous image and database backup remain available for manual rollback.
    cmd('docker', 'rm', previous)
    print('Deployed:', branch)
