"""Synthetic macOS beta tests. No real launchctl or Ollama installation is used."""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import configuration
import desktop_settings
import platform_paths
from checks.cli_history import CliHistoryCheck
from checks.context import AccountContext, ScanContext
from checks.desktop_database import DesktopDatabaseCheck
from checks.logs import LogsCheck


@pytest.fixture
def mac(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: home))
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    store = {}
    calls = []

    def fake_getenv(name, timeout=3):
        return (name in store, store.get(name), None)

    def fake_launchctl(args):
        calls.append(list(args))
        if args[0] == 'setenv':
            store[args[1]] = args[2]
        elif args[0] == 'unsetenv':
            store.pop(args[1], None)
        return subprocess.CompletedProcess(args, 0, '', '')

    monkeypatch.setattr(platform_paths, 'launchctl_getenv', fake_getenv)
    monkeypatch.setattr(configuration, '_launchctl', fake_launchctl)
    return SimpleNamespace(home=home, store=store, calls=calls)


def context_for(home, platform='darwin'):
    return ScanContext(
        accounts=[AccountContext('mac_user', home, None, platform=platform)],
        environment_sources={},
        model_directories=[],
        log_directories=[],
        redirected_logs=[],
        model_source_paths=[]
    )


def test_platform_paths_macos(mac):
    assert platform_paths.desktop_database_dir(home=mac.home, platform='darwin') == mac.home / 'Library' / 'Application Support' / 'Ollama'
    assert platform_paths.log_directories(home=mac.home, platform='darwin') == [mac.home / '.ollama' / 'logs']
    assert platform_paths.config_backup_path(home=mac.home, platform='darwin') == mac.home / 'Library' / 'Application Support' / 'OllamaPrivacyController' / 'configuration-backup.json'


def test_macos_checkers_use_macos_paths(mac):
    db_dir = mac.home / 'Library' / 'Application Support' / 'Ollama'
    db_dir.mkdir(parents=True)
    db = db_dir / 'db.sqlite'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE chats (id INTEGER PRIMARY KEY, title TEXT)')
        conn.execute('CREATE TABLE messages (id INTEGER PRIMARY KEY, content TEXT)')
        conn.execute("INSERT INTO chats (title) VALUES ('fixture')")
        conn.execute("INSERT INTO messages (content) VALUES ('fixture')")
    log_dir = mac.home / '.ollama' / 'logs'
    log_dir.mkdir(parents=True)
    (log_dir / 'server.log').write_text('time=2026-01-01T00:00:00Z level=INFO msg="fixture"\n')
    (mac.home / '.ollama').mkdir(exist_ok=True)
    (mac.home / '.ollama' / 'history').write_text('fixture\n')
    context = context_for(mac.home)

    db_result = DesktopDatabaseCheck().inspect(context)
    log_result = LogsCheck().inspect(context)
    history_result = CliHistoryCheck().inspect(context)

    assert str(db) in [item['path'] for item in db_result.locations]
    assert str(log_dir / 'server.log') in [item['path'] for item in log_result.locations]
    assert str(mac.home / '.ollama' / 'history') in [item['path'] for item in history_result.locations]


def test_desktop_settings_macos_paths(mac, monkeypatch):
    db_dir = mac.home / 'Library' / 'Application Support' / 'Ollama'
    db_dir.mkdir(parents=True)
    db = db_dir / 'db.sqlite'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE users (name TEXT, plan TEXT)')
        conn.execute('CREATE TABLE settings (id INTEGER, auto_update_enabled INTEGER, expose INTEGER, models TEXT, context_length INTEGER)')
        conn.execute("INSERT INTO users VALUES ('Fixture User', 'free')")
        conn.execute("INSERT INTO settings VALUES (1, 0, 0, '/fixture/models', 0)")
    (mac.home / '.ollama').mkdir(exist_ok=True)
    (mac.home / '.ollama' / 'server.json').write_text('{"disable_ollama_cloud": true}')
    log_dir = mac.home / '.ollama' / 'logs'
    log_dir.mkdir(exist_ok=True)
    (log_dir / 'server.log').write_text('time=fixture msg="Ollama cloud disabled: true"\n')
    monkeypatch.setattr(desktop_settings, 'detect_version', lambda: {'version': None, 'source': None, 'status': 'unknown'})

    result = desktop_settings.inspect()

    assert result['platform'] == 'darwin'
    assert result['updater']['status'] == 'not_assessed'
    assert result['updater']['platform'] == 'darwin'
    sign_in = next(row for row in result['settings'] if row['label'] == 'Sign in')
    cloud = next(row for row in result['settings'] if row['label'] == 'Cloud')
    assert sign_in['status'] == 'read' and 'Fixture User' in sign_in['value']
    assert cloud['status'] == 'read' and 'Disabled' in cloud['value']
    assert 'untested beta' in result['note']


def test_context_macos_launchctl_sources(mac, monkeypatch):
    mac.store['OLLAMA_NO_CLOUD'] = 'true'
    monkeypatch.setattr(sys, 'platform', 'darwin')
    context = ScanContext.current()
    assert context.accounts[0].platform == 'darwin'
    assert context.environment_sources['user']['values']['OLLAMA_NO_CLOUD'] == 'true'
    assert context.environment_sources['machine']['status'] == 'unsupported'


def test_configuration_macos_apply_and_restore(mac):
    state = configuration.inspect()
    assert state['supported'] is True
    assert state['beta'] is True
    assert state['machine_supported'] is False

    plan = configuration.plan({'changes': {'OLLAMA_NO_CLOUD': 'true', 'OLLAMA_HOST': '127.0.0.1:11434'}}, 'mac-session')
    result = configuration.apply({'plan_token': plan['plan_token'], 'confirmed': True}, 'mac-session')

    assert mac.store['OLLAMA_NO_CLOUD'] == 'true'
    assert mac.store['OLLAMA_HOST'] == '127.0.0.1:11434'
    assert result['persistence'] == 'launchd_login_agents_beta'
    agent_dir = mac.home / 'Library' / 'LaunchAgents'
    assert (agent_dir / 'com.ollamaPrivacyController.env.ollama_no_cloud.plist').is_file()
    assert (agent_dir / 'com.ollamaPrivacyController.env.ollama_host.plist').is_file()
    backup = mac.home / 'Library' / 'Application Support' / 'OllamaPrivacyController' / 'configuration-backup.json'
    assert backup.is_file()

    restore_plan = configuration.plan({'mode': 'restore'}, 'mac-session')
    restore = configuration.apply({'plan_token': restore_plan['plan_token'], 'confirmed': True}, 'mac-session')
    assert restore['persistence'] == 'removed'
    assert 'OLLAMA_NO_CLOUD' not in mac.store
    assert 'OLLAMA_HOST' not in mac.store
    assert not list(agent_dir.glob('com.ollamaPrivacyController.env.*.plist'))
    assert not backup.exists()


def test_configuration_macos_rejects_existing_agent(mac):
    agent_dir = mac.home / 'Library' / 'LaunchAgents'
    agent_dir.mkdir(parents=True)
    (agent_dir / 'com.ollamaPrivacyController.env.ollama_debug.plist').write_text('fixture')
    with pytest.raises(configuration.ConfigError, match='launch agents'):
        configuration.plan({'changes': {'OLLAMA_DEBUG': '0'}}, 'mac-session')


def test_configuration_macos_restore_refuses_tampered_agent(mac):
    plan = configuration.plan({'changes': {'OLLAMA_NO_CLOUD': 'true'}}, 'mac-session')
    configuration.apply({'plan_token': plan['plan_token'], 'confirmed': True}, 'mac-session')
    agent = mac.home / 'Library' / 'LaunchAgents' / 'com.ollamaPrivacyController.env.ollama_no_cloud.plist'
    agent.write_text('tampered')

    restore_plan = configuration.plan({'mode': 'restore'}, 'mac-session')
    with pytest.raises(configuration.ConfigError, match='changed since apply'):
        configuration.apply({'plan_token': restore_plan['plan_token'], 'confirmed': True}, 'mac-session')

    assert mac.store['OLLAMA_NO_CLOUD'] == 'true'
    assert agent.read_text() == 'tampered'
