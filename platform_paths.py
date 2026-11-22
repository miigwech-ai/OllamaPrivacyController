"""Shared platform path and launchd helpers."""
import os
import subprocess
import sys
from pathlib import Path

LAUNCHCTL = '/bin/launchctl'


def platform_id(platform=None):
    return platform or sys.platform


def is_windows(platform=None):
    return platform_id(platform).startswith('win')


def is_macos(platform=None):
    return platform_id(platform) == 'darwin'


def is_linux(platform=None):
    return platform_id(platform).startswith('linux')


def _home(home=None):
    return Path(home) if home is not None else Path.home()


def desktop_database_dir(home=None, platform=None, local_app_data=None):
    platform = platform_id(platform)
    if is_windows(platform):
        base = local_app_data if local_app_data is not None else os.environ.get('LOCALAPPDATA')
        return Path(base) / 'Ollama' if base else None
    if is_macos(platform):
        return _home(home) / 'Library' / 'Application Support' / 'Ollama'
    return None


def log_directories(home=None, platform=None, local_app_data=None):
    platform = platform_id(platform)
    if is_windows(platform):
        base = local_app_data if local_app_data is not None else os.environ.get('LOCALAPPDATA')
        return [Path(base) / 'Ollama'] if base else []
    if is_macos(platform):
        return [_home(home) / '.ollama' / 'logs']
    return []


def config_backup_path(home=None, platform=None):
    platform = platform_id(platform)
    if is_windows(platform):
        base = os.environ.get('LOCALAPPDATA')
        if not base:
            return None
        return Path(base) / 'OllamaPrivacyController' / 'configuration-backup.json'
    if is_macos(platform):
        return _home(home) / 'Library' / 'Application Support' / 'OllamaPrivacyController' / 'configuration-backup.json'
    return _home(home) / '.local' / 'state' / 'OllamaPrivacyController' / 'configuration-backup.json'


def launchctl_getenv(name, timeout=3):
    try:
        proc = subprocess.run([LAUNCHCTL, 'getenv', name], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return False, None, 'launchctl is unavailable.'
    if proc.returncode == 0:
        return True, proc.stdout.rstrip('\r\n'), None
    detail = (proc.stderr or proc.stdout or '').lower()
    if 'could not find' in detail or 'not found' in detail or 'no such' in detail:
        return False, None, None
    return False, None, 'launchctl getenv failed.'
