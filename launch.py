"""Tailscale Funnel, Mini App va botning ishlashini boshqaradi."""
import contextlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

from dotenv import load_dotenv
from setup_config import prepare_config

ROOT = Path(__file__).resolve().parent


@contextlib.contextmanager
def single_instance():
    runtime = ROOT / '.runtime'
    runtime.mkdir(mode=0o700, exist_ok=True)
    with (runtime / 'launcher.lock').open('a+b') as lock:
        try:
            if os.name == 'nt':
                import msvcrt
                lock.seek(0)
                lock.write(b'0')
                lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError('Bot allaqachon ishlayapti. Avval uni to‘xtating.') from None
        yield runtime


def stop_child(child):
    if child is None or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)


def tailscale_json(executable, *arguments):
    result = subprocess.run([executable, *arguments, '--json'], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError('Tailscale holatini tekshirib bo‘lmadi. Tailscale ulanganini tekshiring.')
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise RuntimeError('Tailscale holati noto‘g‘ri qaytdi.') from None


def health(url):
    try:
        with urlopen(url.rstrip('/') + '/healthz', timeout=3) as response:
            return response.status == 200 and json.load(response).get('ready') is True
    except (OSError, URLError, ValueError):
        return False


def wait_ready(child, tunnel, url, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError('Bot ishga tushmadi. Yuqoridagi xabarni tekshiring.')
        if tunnel is not None and tunnel.poll() is not None:
            raise RuntimeError('Tailscale Funnel ishga tushmadi. Yuqoridagi ruxsat yoki xato xabarini tekshiring.')
        if health(url):
            return
        time.sleep(.5)
    raise RuntimeError('Bot yoki HTTPS sahifa tayyor bo‘lmadi. Tailscale Funnel ruxsati va internetni tekshiring.')


def run():
    prepare_config()
    load_dotenv(ROOT / '.env')
    from main import Config
    cfg = Config.load()
    executable = shutil.which('tailscale')
    if not executable:
        raise RuntimeError('Tailscale CLI topilmadi. Tailscale o‘rnating va hisobga kiring.')
    mac_executable = Path('/Applications/Tailscale.app/Contents/MacOS/Tailscale')
    if sys.platform == 'darwin' and executable == '/usr/local/bin/tailscale' and mac_executable.exists():
        executable = str(mac_executable)
    with single_instance():
        status = tailscale_json(executable, 'status')
        name = (status.get('Self') or {}).get('DNSName', '').rstrip('.')
        if status.get('BackendState') != 'Running' or not name.endswith('.ts.net'):
            raise RuntimeError('Tailscale ulanmagan yoki MagicDNS mavjud emas.')
        if tailscale_json(executable, 'serve', 'status'):
            raise RuntimeError('Tailscale Serve/Funnel allaqachon sozlangan. Mavjud sozlamani o‘zgartirishdan oldin tekshiring.')
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(('127.0.0.1', cfg.webapp_port))
            except OSError:
                raise RuntimeError(f'{cfg.webapp_port}-port band. Avval eski bot/serverni to‘xtating.') from None
        url = 'https://' + name
        child = None
        tunnel = None
        try:
            child_env = os.environ.copy()
            child_env['WEBAPP_URL'] = url
            child_env['WEBAPP_PORT'] = str(cfg.webapp_port)
            child_env['PYTHONUNBUFFERED'] = '1'
            child = subprocess.Popen([sys.executable, str(ROOT / 'main.py')], cwd=ROOT, env=child_env)
            wait_ready(child, None, f'http://127.0.0.1:{cfg.webapp_port}')
            print('Tailscale Funnel ochilmoqda. Ruxsat so‘ralsa ko‘rsatilgan yo‘riqnomaga amal qiling.', flush=True)
            tunnel = subprocess.Popen([executable, 'funnel', f'http://127.0.0.1:{cfg.webapp_port}'], cwd=ROOT)
            wait_ready(child, tunnel, url, timeout=90)
            print(f'To‘liq ishga tushdi: {url}\nTo‘xtatish: Ctrl+C.', flush=True)
            while child.poll() is None:
                if tunnel.poll() is not None:
                    raise RuntimeError('Tailscale Funnel to‘xtadi.')
                time.sleep(.5)
            return child.returncode or 1
        finally:
            stop_child(tunnel)
            stop_child(child)


def main():
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    if os.name == 'nt':
        signal.signal(signal.SIGBREAK, interrupted)
    try:
        return run()
    except KeyboardInterrupt:
        print('\nBot va Tailscale Funnel to‘xtatildi.', flush=True)
        return 0
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f'Ishga tushirish tugamadi: {exc}', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
