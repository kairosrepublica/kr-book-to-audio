from __future__ import annotations
from pathlib import Path
import json
import os

APP_NAME = "KRBookToAudio"
DEFAULT_VOICE = "zh-CN-YunyangNeural"
DEFAULT_RATE = "+0%"
DEFAULT_CHUNK_CJK = 9000


def local_work_root() -> Path:
    """Return a non-cloud-synced default working root on Windows and other systems."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / APP_NAME / "jobs"
    return Path.home() / f".{APP_NAME.lower()}" / "jobs"


def default_export_root() -> Path:
    return Path.home() / "Documents" / "KR Book To Audio Exports"


def config_path() -> Path:
    return Path.home() / ".kr_book_to_audio.json"


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(data: dict) -> None:
    path = config_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
