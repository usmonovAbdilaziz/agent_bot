"""Launcher lifecycle checks without a live Tailscale or Telegram service."""
import subprocess
import sys
from types import SimpleNamespace

import pytest

import launch


def test_launcher_lock_rejects_second_process_and_releases(tmp_path, monkeypatch):
    monkeypatch.setattr(launch, 'ROOT', tmp_path)
    script = ('import launch; from pathlib import Path; '
              f'launch.ROOT=Path({str(tmp_path)!r}); '
              'ctx=launch.single_instance(); ctx.__enter__()')
    with launch.single_instance():
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
        assert result.returncode != 0
    assert subprocess.run([sys.executable, '-c', script], capture_output=True).returncode == 0


def test_stop_child_terminates_real_process():
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    launch.stop_child(child)
    assert child.poll() is not None


@pytest.mark.parametrize('bot_exit,tunnel_exit', [(1, None), (None, 1)])
def test_readiness_rejects_dead_process(bot_exit, tunnel_exit):
    bot = SimpleNamespace(poll=lambda: bot_exit)
    tunnel = SimpleNamespace(poll=lambda: tunnel_exit)
    with pytest.raises(RuntimeError):
        launch.wait_ready(bot, tunnel, 'http://127.0.0.1:1', timeout=1)


def configure(monkeypatch, tmp_path, serve_config):
    from config import Config
    monkeypatch.setattr(launch, 'ROOT', tmp_path)
    monkeypatch.setattr(launch, 'prepare_config', lambda: None)
    monkeypatch.setattr(launch, 'load_dotenv', lambda *args: None)
    monkeypatch.setattr(Config, 'load', lambda: Config('123456:test', '998900000000', webapp_port=0))
    monkeypatch.setattr(launch.shutil, 'which', lambda name: '/usr/bin/tailscale')
    def status(executable, *args):
        if args == ('status',):
            return {'BackendState': 'Running', 'Self': {'DNSName': 'test.example.ts.net.'}}
        return serve_config
    monkeypatch.setattr(launch, 'tailscale_json', status)


def test_existing_serve_configuration_is_preserved(tmp_path, monkeypatch):
    configure(monkeypatch, tmp_path, {'Web': {'existing': {}}})
    monkeypatch.setattr(launch.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('must not start'))
    with pytest.raises(RuntimeError, match='allaqachon sozlangan'):
        launch.run()


def test_tunnel_failure_cleans_up_bot_and_passes_dns_name(tmp_path, monkeypatch):
    configure(monkeypatch, tmp_path, {})
    children = []
    class Child:
        def __init__(self, exited=False):
            self.exited = exited
        def poll(self):
            return 1 if self.exited else None
        def terminate(self):
            self.exited = True
        def wait(self, timeout=None):
            return 0
    def start(command, **kwargs):
        if len(children) == 0:
            assert kwargs['env']['WEBAPP_URL'] == 'https://test.example.ts.net'
        child = Child(exited=len(children) == 1)
        children.append(child)
        return child
    monkeypatch.setattr(launch.subprocess, 'Popen', start)
    monkeypatch.setattr(launch, 'health', lambda url: True)
    with pytest.raises(RuntimeError, match='Funnel ishga tushmadi'):
        launch.run()
    assert children[0].exited
