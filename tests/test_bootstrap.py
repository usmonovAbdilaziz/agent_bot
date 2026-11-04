"""Dependency repair without network access or starting the bot."""
import subprocess
import sys
from types import SimpleNamespace
import venv

import pytest

import run


def test_probe_detects_empty_environment(tmp_path):
    env = tmp_path / 'empty'
    venv.EnvBuilder(with_pip=False).create(env)
    executable = env / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    assert not run.dependencies_available(executable)
    assert run.dependencies_available(sys.executable)


@pytest.mark.parametrize('available,stamp_matches,installs', [
    (False, True, True),  # Regression: stale success stamp with missing dotenv.
    (True, True, False),
    (True, False, True),
])
def test_dependency_repair(tmp_path, monkeypatch, available, stamp_matches, installs):
    monkeypatch.setattr(run, 'ensure_pip', lambda executable: None)
    monkeypatch.setattr(run, 'ROOT', tmp_path)
    expected = 'python-dotenv==1.1.1\n'
    (tmp_path / 'requirements.txt').write_text(expected)
    stamp = tmp_path / '.agent-bot-requirements'
    stamp.write_text(expected if stamp_matches else 'old')
    probes = iter([available, True])
    monkeypatch.setattr(run, 'dependencies_available', lambda executable: next(probes))
    calls = []
    monkeypatch.setattr(run.subprocess, 'run', lambda command, **kwargs: calls.append((command, kwargs)))
    executable = tmp_path / 'Scripts' / 'python.exe'
    run.prepare_dependencies(executable, tmp_path)
    assert len(calls) == int(installs)
    if installs:
        command, kwargs = calls[0]
        assert command[:4] == [str(executable), '-m', 'pip', 'install']
        assert ('--force-reinstall' in command) == (not available)
        assert kwargs['check'] is True
    assert stamp.read_text() == expected


@pytest.mark.parametrize('pip_fails', [True, False])
def test_failed_repair_does_not_record_success(tmp_path, monkeypatch, pip_fails):
    monkeypatch.setattr(run, 'ensure_pip', lambda executable: None)
    monkeypatch.setattr(run, 'ROOT', tmp_path)
    (tmp_path / 'requirements.txt').write_text('python-dotenv==1.1.1\n')
    monkeypatch.setattr(run, 'dependencies_available', lambda executable: False)

    def install(command, **kwargs):
        if pip_fails:
            raise subprocess.CalledProcessError(1, command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run.subprocess, 'run', install)
    with pytest.raises(subprocess.CalledProcessError if pip_fails else RuntimeError):
        run.prepare_dependencies(sys.executable, tmp_path)
    assert not (tmp_path / '.agent-bot-requirements').exists()


def test_copied_virtual_environment_is_preserved_and_rebuilt(tmp_path, monkeypatch):
    monkeypatch.setattr(run, 'ROOT', tmp_path)
    env=tmp_path/'.venv'
    env.mkdir()
    (env/'old-platform-marker').write_text('old environment')
    executable=run.prepare_environment(env)
    result=subprocess.run([str(executable),'-I','-c','import sys, pip; print(sys.prefix)'],capture_output=True,text=True)
    assert result.returncode==0 and str(env) in result.stdout
    backups=list(tmp_path.glob('.venv-backup-*'))
    assert len(backups)==1 and (backups[0]/'old-platform-marker').read_text()=='old environment'
    assert run.prepare_environment(env)==executable
    assert len(list(tmp_path.glob('.venv-backup-*')))==1


def test_missing_pip_is_restored_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(run, 'ROOT', tmp_path)
    env=tmp_path/'without-pip'
    venv.EnvBuilder(with_pip=False).create(env)
    executable=env/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    run.ensure_pip(executable)
    assert subprocess.run([str(executable),'-m','pip','--version'],capture_output=True).returncode==0


@pytest.mark.parametrize('stuck',[False,True])
def test_windows_shutdown_signals_owned_process_group(tmp_path,monkeypatch,stuck):
    monkeypatch.setattr(run,'ROOT',tmp_path)
    monkeypatch.setattr(run,'os',SimpleNamespace(name='nt'))
    monkeypatch.setattr(run.signal,'CTRL_BREAK_EVENT',123,raising=False)
    monkeypatch.setattr(run.subprocess,'CREATE_NEW_PROCESS_GROUP',512,raising=False)
    monkeypatch.setattr(run,'prepare_environment',lambda env:tmp_path/'python.exe')
    monkeypatch.setattr(run,'prepare_dependencies',lambda *args:None)
    actions=[]

    class Child:
        pid=4321
        def poll(self): return None
        def wait(self,timeout=None):
            if timeout is None and not actions: raise KeyboardInterrupt
            if timeout==20 and stuck: raise subprocess.TimeoutExpired('launcher',20)
            return 0
        def send_signal(self,signal): actions.append(('signal',signal))
        def kill(self): actions.append(('kill',))

    def start(command,**kwargs):
        assert kwargs['creationflags']==512
        assert command[-1]==str(tmp_path/'launch.py')
        return Child()

    monkeypatch.setattr(run.subprocess,'Popen',start)
    monkeypatch.setattr(run.subprocess,'run',lambda command,**kwargs:actions.append(('command',command)))
    with pytest.raises(KeyboardInterrupt): run.main()
    assert actions[0]==('signal',123)
    assert (('command',['taskkill','/PID','4321','/T','/F']) in actions)==stuck
