"""First-run prompts, persistence and preservation using synthetic credentials."""
from types import SimpleNamespace

from dotenv import dotenv_values
import pytest
import setup_config

TOKEN='123456:FAKE_ONLY_FOR_LOCAL_TESTS_12345'
KEYS=('BOT_TOKEN','ADMIN_PHONE')


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(setup_config,'ROOT',tmp_path)
    for key in KEYS: monkeypatch.delenv(key,raising=False)
    (tmp_path/'.env.example').write_text('BOT_TOKEN=\nADMIN_PHONE=\nWEBAPP_PORT=8080\n')
    monkeypatch.setattr(setup_config.sys,'stdin',SimpleNamespace(isatty=lambda:True))
    return tmp_path


def test_first_run_prompts_and_next_run_uses_saved_values(setup,monkeypatch,capsys):
    answers=iter([TOKEN])
    monkeypatch.setattr(setup_config.getpass,'getpass',lambda prompt:next(answers))
    monkeypatch.setattr('builtins.input',lambda prompt:'+998 (90) 123-45-67')
    setup_config.prepare_config()
    values=dotenv_values(setup/'.env')
    assert values['BOT_TOKEN']==TOKEN and 'NGROK_AUTHTOKEN' not in values
    assert values['ADMIN_PHONE']=='+998901234567'
    output=capsys.readouterr().out
    assert TOKEN not in output
    original=(setup/'.env').read_bytes()
    for key in KEYS: monkeypatch.delenv(key,raising=False)
    def unexpected(prompt): pytest.fail('Saved settings must not prompt again')
    monkeypatch.setattr(setup_config.getpass,'getpass',unexpected)
    monkeypatch.setattr('builtins.input',unexpected)
    setup_config.prepare_config()
    assert (setup/'.env').read_bytes()==original


def test_missing_keys_added_without_overwriting_existing_settings(setup,monkeypatch):
    (setup/'.env').write_text('# existing settings\nADMIN_PHONE=+998901234567\nWEBAPP_PORT=8081\nDB_PATH=data/original.sqlite3\n')
    answers=iter([TOKEN])
    monkeypatch.setattr(setup_config.getpass,'getpass',lambda prompt:next(answers))
    setup_config.prepare_config()
    values=dotenv_values(setup/'.env')
    assert values['WEBAPP_PORT']=='8081' and values['DB_PATH']=='data/original.sqlite3'
    assert values['BOT_TOKEN']==TOKEN and 'NGROK_AUTHTOKEN' not in values
    assert (setup/'.env').read_text().startswith('# existing settings')


def test_noninteractive_missing_config_is_actionable(setup,monkeypatch):
    monkeypatch.setattr(setup_config.sys,'stdin',SimpleNamespace(isatty=lambda:False))
    with pytest.raises(RuntimeError,match='BOT_TOKEN'):
        setup_config.prepare_config()


def test_invalid_inputs_are_retried_before_saving(setup,monkeypatch,capsys):
    secrets=iter(['invalid',TOKEN])
    phones=iter(['abc','123','+998901234567'])
    monkeypatch.setattr(setup_config.getpass,'getpass',lambda prompt:next(secrets))
    monkeypatch.setattr('builtins.input',lambda prompt:next(phones))
    setup_config.prepare_config()
    values=dotenv_values(setup/'.env')
    assert values['BOT_TOKEN']==TOKEN and 'NGROK_AUTHTOKEN' not in values
    assert values['ADMIN_PHONE']=='+998901234567'
    assert 'contains spaces' not in capsys.readouterr().out


def test_external_environment_can_supply_settings_without_persisting_secrets(setup,monkeypatch):
    for key,value in zip(KEYS,(TOKEN,'+998901234567')):
        monkeypatch.setenv(key,value)
    monkeypatch.setattr(setup_config.sys,'stdin',SimpleNamespace(isatty=lambda:False))
    setup_config.prepare_config()
    assert TOKEN not in (setup/'.env').read_text()


def test_blank_input_stops_cleanly(setup,monkeypatch):
    monkeypatch.setattr(setup_config.getpass,'getpass',lambda prompt:'')
    with pytest.raises(RuntimeError,match='BOT_TOKEN kiritilmadi'):
        setup_config.prepare_config()
