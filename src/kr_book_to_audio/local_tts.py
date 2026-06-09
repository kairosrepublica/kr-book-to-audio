from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import os
import re


KOKORO_REQUIRED_REPO_CACHE_DIRS: tuple[str, ...] = (
    'models--hexgrad--Kokoro-82M',
    'models--hexgrad--Kokoro-82M-v1.1-zh',
)

KOKORO_VOICES: tuple[dict[str, str], ...] = (
    {'short_name': 'zf_001', 'locale': 'zh-CN', 'gender': 'Female', 'friendly_name': 'Kokoro Mandarin Female 001'},
    {'short_name': 'zm_009', 'locale': 'zh-CN', 'gender': 'Male', 'friendly_name': 'Kokoro Mandarin Male 009'},
    {'short_name': 'af_heart', 'locale': 'en-US', 'gender': 'Female', 'friendly_name': 'Kokoro American English Heart'},
    {'short_name': 'am_adam', 'locale': 'en-US', 'gender': 'Male', 'friendly_name': 'Kokoro American English Adam'},
    {'short_name': 'bf_emma', 'locale': 'en-GB', 'gender': 'Female', 'friendly_name': 'Kokoro British English Emma'},
    {'short_name': 'bm_george', 'locale': 'en-GB', 'gender': 'Male', 'friendly_name': 'Kokoro British English George'},
)


def local_tts_root() -> Path:
    override = os.environ.get('KR_B2A_LOCAL_TTS_ROOT')
    if override:
        return Path(override)
    if os.name == 'nt':
        return Path(r'C:\dev\KR_TTS_Local')
    return Path.home() / '.kr_tts_local'


def governed_resource_archive_root() -> Path:
    override = os.environ.get('KR_B2A_TTS_RESOURCE_ARCHIVE_ROOT')
    if override:
        return Path(override)
    if os.name == 'nt':
        return Path.home() / 'OneDrive' / 'Documents' / 'KRG' / 'KRG Code' / '_Resource' / 'KR_TTS_Offline_Resources'
    return Path.home() / '.kr_tts_offline_resources'


@dataclass(frozen=True)
class KokoroFoundation:
    root: Path
    resource_archive_root: Path
    python: Path
    worker: Path
    hf_home: Path
    reports: Path
    samples: Path
    logs: Path

    def required_model_cache_paths(self) -> tuple[Path, ...]:
        hub = self.hf_home / 'hub'
        return tuple(hub / name for name in KOKORO_REQUIRED_REPO_CACHE_DIRS)

    def ready(self) -> tuple[bool, list[str]]:
        required = (self.python, self.worker, *self.required_model_cache_paths())
        missing = [str(path) for path in required if not path.exists()]
        return not missing, missing

    def assert_ready(self) -> None:
        ok, missing = self.ready()
        if not ok:
            raise RuntimeError(
                'Kokoro Local foundation is not installed. Run tools/setup_local_tts_foundation.py first. '
                f'Missing: {missing}'
            )

    def worker_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env['HF_HOME'] = str(self.hf_home)
        env['HUGGINGFACE_HUB_CACHE'] = str(self.hf_home / 'hub')
        env['HF_HUB_OFFLINE'] = '1'
        env['TRANSFORMERS_OFFLINE'] = '1'
        env['HF_DATASETS_OFFLINE'] = '1'
        env['HF_HUB_DISABLE_SYMLINKS'] = '1'
        env['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
        env['KR_B2A_LOCAL_TTS_ROOT'] = str(self.root)
        return env


def kokoro_foundation(root: Path | None = None, resource_archive_root: Path | None = None) -> KokoroFoundation:
    root = Path(root or local_tts_root())
    resource_archive_root = Path(resource_archive_root or governed_resource_archive_root())
    if os.name == 'nt':
        python = root / 'envs' / 'kokoro' / 'Scripts' / 'python.exe'
    else:
        python = root / 'envs' / 'kokoro' / 'bin' / 'python'
    return KokoroFoundation(
        root=root,
        resource_archive_root=resource_archive_root,
        python=python,
        worker=root / 'workers' / 'kokoro_worker' / 'kokoro_worker.py',
        hf_home=root / 'hf_cache',
        reports=root / 'reports',
        samples=root / 'samples',
        logs=root / 'logs',
    )


def kokoro_speed_from_rate(rate: str) -> float:
    match = re.fullmatch(r'([+-]?)(\d+(?:\.\d+)?)%', str(rate).strip())
    if not match:
        raise RuntimeError(f'Unsupported Rate format for Kokoro Local: {rate!r}. Use values such as +0%, -10% or +15%.')
    sign = -1.0 if match.group(1) == '-' else 1.0
    percent = sign * float(match.group(2))
    speed = 1.0 + percent / 100.0
    if not 0.5 <= speed <= 2.0:
        raise RuntimeError('Kokoro Local Rate must remain between -50% and +100%.')
    return speed
