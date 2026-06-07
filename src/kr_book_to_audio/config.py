from __future__ import annotations
from pathlib import Path
import json
import os

APP_NAME = "KRBookToAudio"
DEFAULT_VOICE = "zh-CN-YunyangNeural"
DEFAULT_RATE = "+0%"
DEFAULT_CHUNK_CJK = 9000


def local_work_root() -> Path:
    """Return a local processing root. Cloud-synced roots are discouraged for work files."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / APP_NAME / "jobs"
    return Path.home() / f".{APP_NAME.lower()}" / "jobs"


def default_export_root() -> Path:
    return Path.home() / "Documents" / "KR Book To Audio Exports"


def config_path() -> Path:
    return Path.home() / ".kr_book_to_audio.json"


def _migrate_config(payload: dict) -> dict:
    """Remove retired UI options while preserving the date-cleanup preference."""
    migrated = dict(payload)
    if "strip_datetime_tags" not in migrated and "strip_dates" in migrated:
        migrated["strip_datetime_tags"] = bool(migrated.get("strip_dates"))
    migrated.pop("strip_dates", None)
    migrated.pop("t2s", None)
    return migrated


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    try:
        return _migrate_config(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def save_config(data: dict) -> None:
    path = config_path()
    path.write_text(json.dumps(_migrate_config(data), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
