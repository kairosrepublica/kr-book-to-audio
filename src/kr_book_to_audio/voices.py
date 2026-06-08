from __future__ import annotations
from pathlib import Path
import json
from .config import config_path
from .providers import get_tts_provider

FALLBACK_VOICES = [
    {'short_name': 'zh-CN-YunyangNeural', 'locale': 'zh-CN', 'gender': 'Male', 'friendly_name': 'zh-CN-YunyangNeural'},
    {'short_name': 'zh-CN-XiaoxiaoNeural', 'locale': 'zh-CN', 'gender': 'Female', 'friendly_name': 'zh-CN-XiaoxiaoNeural'},
    {'short_name': 'zh-CN-YunxiNeural', 'locale': 'zh-CN', 'gender': 'Male', 'friendly_name': 'zh-CN-YunxiNeural'},
    {'short_name': 'en-US-AriaNeural', 'locale': 'en-US', 'gender': 'Female', 'friendly_name': 'en-US-AriaNeural'},
    {'short_name': 'en-US-GuyNeural', 'locale': 'en-US', 'gender': 'Male', 'friendly_name': 'en-US-GuyNeural'},
    {'short_name': 'en-GB-SoniaNeural', 'locale': 'en-GB', 'gender': 'Female', 'friendly_name': 'en-GB-SoniaNeural'},
]


def voice_cache_path() -> Path:
    return config_path().with_name('.kr_book_to_audio_voices.json')


def save_voice_cache(provider_id: str, voices: list[dict[str, str]]) -> None:
    payload = {'provider_id': provider_id, 'voices': voices}
    voice_cache_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load_voice_cache(provider_id: str = 'edge-tts') -> list[dict[str, str]]:
    path = voice_cache_path()
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
            if payload.get('provider_id') == provider_id and isinstance(payload.get('voices'), list):
                voices = [item for item in payload['voices'] if isinstance(item, dict) and item.get('short_name')]
                if voices:
                    return voices
        except (OSError, ValueError, TypeError):
            pass
    return list(FALLBACK_VOICES)


def refresh_voice_cache(provider_id: str = 'edge-tts') -> list[dict[str, str]]:
    voices = get_tts_provider(provider_id).list_voices()
    if voices:
        save_voice_cache(provider_id, voices)
    return voices or load_voice_cache(provider_id)


def filter_voices(voices: list[dict[str, str]], profile: str, *, show_all: bool = False) -> list[dict[str, str]]:
    if show_all or profile in {'general-prose', 'auto'}:
        return voices
    allowed: tuple[str, ...]
    if profile == 'chinese':
        allowed = ('zh-',)
    elif profile == 'english':
        allowed = ('en-',)
    elif profile == 'mixed':
        allowed = ('zh-', 'en-')
    else:
        allowed = ()
    selected = [voice for voice in voices if str(voice.get('locale', '')).lower().startswith(allowed)]
    return selected or voices
