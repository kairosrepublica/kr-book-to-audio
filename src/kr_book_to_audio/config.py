from __future__ import annotations
from pathlib import Path
import json
import os

APP_NAME = 'KRBookToAudio'
DEFAULT_TTS_ENGINE = 'edge-tts'
DEFAULT_VOICE = 'zh-CN-YunyangNeural'
DEFAULT_RATE = '+0%'
DEFAULT_PITCH = '+0Hz'
DEFAULT_VOLUME = '+0%'
DEFAULT_PROCESSING_PROFILE = 'auto'
DEFAULT_CHUNK_CJK = 9000
DEFAULT_KEEP_AWAKE = True


def app_root() -> Path:
    override = os.environ.get('KR_B2A_APP_ROOT')
    if override:
        return Path(override)
    base = os.environ.get('LOCALAPPDATA')
    if base:
        return Path(base) / APP_NAME
    return Path.home() / f'.{APP_NAME.lower()}'


def local_work_root() -> Path:
    return app_root() / 'jobs'


def execution_history_path() -> Path:
    return app_root() / 'execution_history.json'


def default_export_root() -> Path:
    return Path.home() / 'Documents' / 'KR Book To Audio Exports'


def config_path() -> Path:
    return Path.home() / '.kr_book_to_audio.json'


def _migrate_config(payload: dict) -> dict:
    migrated = dict(payload)
    migrated.pop('strip_dates', None)
    migrated.pop('strip_datetime_tags', None)
    migrated.pop('t2s', None)
    migrated.setdefault('tts_engine', DEFAULT_TTS_ENGINE)
    migrated.setdefault('processing_profile', DEFAULT_PROCESSING_PROFILE)
    migrated.setdefault('prepare_layout_mode', 'auto')
    migrated.setdefault('pitch', DEFAULT_PITCH)
    migrated.setdefault('volume', DEFAULT_VOLUME)
    migrated.setdefault('show_all_voices', False)
    migrated.setdefault('keep_awake', DEFAULT_KEEP_AWAKE)
    return migrated


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        return _migrate_config({})
    try:
        return _migrate_config(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, json.JSONDecodeError, TypeError):
        return _migrate_config({})


def save_config(data: dict) -> None:
    path = config_path()
    path.write_text(json.dumps(_migrate_config(data), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
