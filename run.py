"""Boshqa kompyuterda: python run.py. Virtual muhitni o'zi tayyorlaydi."""
import os
from pathlib import Path
import subprocess
import signal
import sys
import venv
import time

ROOT=Path(__file__).resolve().parent


def prepare_environment(env):
    executable=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    healthy=False
    if executable.exists():
        try:
            probe=f'import sys, venv; assert sys.version_info[:2] == {sys.version_info[:2]!r}'
            result=subprocess.run([str(executable),'-I','-c',probe],
                                  cwd=ROOT,capture_output=True)
            healthy=result.returncode==0
        except OSError:
            pass
    if not healthy:
        if env.exists():
            backup=env.with_name(f'.venv-backup-{time.time_ns()}')
            env.rename(backup)
            print(f'Eski virtual muhit saqlandi: {backup.name}',flush=True)
        print('Virtual muhit tayyorlanmoqda...',flush=True)
        venv.EnvBuilder(with_pip=True).create(env)
    return executable


def ensure_pip(executable):
    result=subprocess.run([str(executable),'-m','pip','--version'],cwd=ROOT,capture_output=True)
    if result.returncode:
        subprocess.run([str(executable),'-m','ensurepip','--upgrade'],check=True,cwd=ROOT)


def dependencies_available(executable):
    result = subprocess.run(
        [str(executable), '-c', 'import dotenv, aiogram, aiosqlite'],
        cwd=ROOT, capture_output=True,
    )
    return result.returncode == 0


def prepare_dependencies(executable, env):
    requirements = ROOT / 'requirements.txt'
    stamp = env / '.agent-bot-requirements'
    expected = requirements.read_text(encoding='utf-8')
    available = dependencies_available(executable)
    if not available or not stamp.exists() or stamp.read_text(encoding='utf-8') != expected:
        print('Kerakli kutubxonalar o‘rnatilmoqda...', flush=True)
        ensure_pip(executable)
        command = [str(executable), '-m', 'pip', 'install']
        if not available:
            # Repair missing files even when pip's package metadata still exists.
            command.append('--force-reinstall')
        subprocess.run(command + ['-r', str(requirements)], check=True, cwd=ROOT)
        if not dependencies_available(executable):
            raise RuntimeError('Kutubxonalar yuklanmadi. .venv muhitini qayta yarating va start.bat ni oching.')
        stamp.write_text(expected, encoding='utf-8')


def main():
    if sys.version_info < (3,11):
        print('Python 3.11 yoki yangirog‘i kerak. Tavsiya: Python 3.12 yoki 3.13.')
        return 1
    env=ROOT/'.venv'
    executable=prepare_environment(env)
    prepare_dependencies(executable, env)
    print('Tailscale Funnel, Mini App va bot ishga tushmoqda. To‘xtatish: Ctrl+C.',flush=True)
    child=subprocess.Popen([str(executable),str(ROOT/'launch.py')],cwd=ROOT,
                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
    try:
        return child.wait()
    finally:
        if child.poll() is None:
            if os.name=='nt':
                child.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                child.terminate()
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                if os.name=='nt':
                    subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True)
                child.kill()
                child.wait()


if __name__=='__main__':
    def interrupted(signum,frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\nTo‘xtatildi.')
    except RuntimeError as exc:
        print(f'Ishga tushirish tugamadi: {exc}')
        raise SystemExit(1)
    except (OSError,subprocess.CalledProcessError) as exc:
        print(f'Ishga tushirish tugamadi: {type(exc).__name__}. Python va internetni tekshiring.')
        raise SystemExit(1)
