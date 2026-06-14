from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import json
import os
import re
import sys

OCR_RUNTIME_ENV = 'KR_B2A_OCR_RUNTIME_ROOT'
OCR_ARCHIVE_ENV = 'KR_B2A_OCR_RESOURCE_ROOT'
OCR_PROFILE_ENV = 'KR_B2A_OCR_PROFILE'
OCR_RUNTIME_DEFAULT = Path('C:/dev/KR_OCR_Local')
OCR_ARCHIVE_RELATIVE = Path('OneDrive') / 'Documents' / 'KRG' / 'KRG Code' / '_Resource' / 'KR_OCR_Offline_Resources'
OCR_FOUNDATION_MARKER = 'manifests/RESOURCE_MANIFEST.json'
OCR_ACTIVE_DEPLOYMENT_POINTER = Path('active') / 'ACTIVE_DEPLOYMENT.json'
OCR_ACTIVE_BUNDLE_POINTER = Path('active') / 'ACTIVE_BUNDLE.json'
PADDLE_PROFILES = ('server', 'mobile')
TESSERACT_PROFILES = ('fast', 'best')
_SAFE_BUNDLE = re.compile(r'^[A-Za-z0-9._-]+$')


def _root_from_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else Path(default)


def ocr_runtime_root() -> Path:
    return _root_from_env(OCR_RUNTIME_ENV, OCR_RUNTIME_DEFAULT)


def ocr_resource_root() -> Path:
    value = os.environ.get(OCR_ARCHIVE_ENV)
    return Path(value).expanduser() if value else Path.home() / OCR_ARCHIVE_RELATIVE


def _exe(name: str) -> str:
    return name + '.exe' if os.name == 'nt' else name


def _read_active_pointer(pointer: Path, key: str, parent: Path) -> Path | None:
    if not pointer.is_file():
        return None
    try:
        payload = json.loads(pointer.read_text(encoding='utf-8'))
        bundle_id = str(payload[key])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
    if not _SAFE_BUNDLE.fullmatch(bundle_id):
        return None
    target = parent / bundle_id
    return target if target.is_dir() else None


@dataclass(frozen=True)
class LocalOCRFoundation:
    root: Path
    resource_root: Path

    @property
    def active_deployment_pointer(self) -> Path:
        return self.root / OCR_ACTIVE_DEPLOYMENT_POINTER

    @property
    def active_bundle_pointer(self) -> Path:
        return self.resource_root / OCR_ACTIVE_BUNDLE_POINTER

    @property
    def runtime_root(self) -> Path:
        active = _read_active_pointer(self.active_deployment_pointer, 'active_bundle', self.root / 'deployments')
        return active or self.root

    @property
    def archive_root(self) -> Path:
        active = _read_active_pointer(self.active_deployment_pointer, 'active_archive_bundle', self.resource_root / 'bundles')
        if active is None:
            active = _read_active_pointer(self.active_bundle_pointer, 'active_bundle', self.resource_root / 'bundles')
        return active or self.resource_root

    @property
    def manifest(self) -> Path:
        return self.archive_root / OCR_FOUNDATION_MARKER

    @property
    def paddle_python(self) -> Path:
        return self.runtime_root / 'envs' / 'paddleocr' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')

    @property
    def paddle_worker(self) -> Path:
        return self.runtime_root / 'workers' / 'paddleocr_worker.py'

    @property
    def poppler_bin(self) -> Path:
        return self.runtime_root / 'tools' / 'poppler' / 'bin'

    @property
    def pdftoppm(self) -> Path:
        return self.poppler_bin / _exe('pdftoppm')

    @property
    def pdftotext(self) -> Path:
        return self.poppler_bin / _exe('pdftotext')

    @property
    def pdfinfo(self) -> Path:
        return self.poppler_bin / _exe('pdfinfo')

    @property
    def pdffonts(self) -> Path:
        return self.poppler_bin / _exe('pdffonts')

    @property
    def tesseract(self) -> Path:
        return self.runtime_root / 'tools' / 'tesseract' / _exe('tesseract')

    def tessdata(self, profile: str = 'fast') -> Path:
        normalized = profile if profile in TESSERACT_PROFILES else 'fast'
        return self.runtime_root / 'tessdata' / normalized

    def paddle_model(self, name: str) -> Path:
        return self.runtime_root / 'models' / 'paddleocr' / name

    def paddle_model_paths(self, profile: str = 'server') -> tuple[Path, Path]:
        normalized = profile if profile in PADDLE_PROFILES else 'server'
        return (
            self.paddle_model(f'PP-OCRv5_{normalized}_det'),
            self.paddle_model(f'PP-OCRv5_{normalized}_rec'),
        )

    def ready_report(self) -> dict[str, object]:
        server_det, server_rec = self.paddle_model_paths('server')
        mobile_det, mobile_rec = self.paddle_model_paths('mobile')
        required_tess = ('eng.traineddata', 'chi_sim.traineddata', 'chi_tra.traineddata', 'osd.traineddata')
        fast = self.tessdata('fast')
        best = self.tessdata('best')
        return {
            'manifest': self.manifest.is_file(),
            'paddle_python': self.paddle_python.is_file(),
            'paddle_worker': self.paddle_worker.is_file(),
            'poppler': all(path.is_file() for path in (self.pdftoppm, self.pdftotext, self.pdfinfo, self.pdffonts)),
            'tesseract': self.tesseract.is_file(),
            'paddle_server_models': all(path.is_dir() and any(path.iterdir()) for path in (server_det, server_rec)),
            'paddle_mobile_models': all(path.is_dir() and any(path.iterdir()) for path in (mobile_det, mobile_rec)),
            'tessdata_fast': all((fast / item).is_file() for item in required_tess),
            'tessdata_best': all((best / item).is_file() for item in required_tess),
        }

    def assert_paddle_ready(self, profile: str = 'server') -> None:
        det, rec = self.paddle_model_paths(profile)
        missing = [str(path) for path in (self.paddle_python, self.paddle_worker, self.pdftoppm, det, rec) if not path.exists()]
        if missing:
            raise RuntimeError('PaddleOCR local foundation is incomplete. Run Install / repair local OCR foundation. Missing: ' + ', '.join(missing))

    def assert_tesseract_ready(self, profile: str = 'fast') -> None:
        tessdata = self.tessdata(profile)
        required = [self.tesseract, self.pdftoppm, tessdata / 'eng.traineddata', tessdata / 'chi_sim.traineddata', tessdata / 'chi_tra.traineddata', tessdata / 'osd.traineddata']
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise RuntimeError('Tesseract local foundation is incomplete. Run Install / repair local OCR foundation. Missing: ' + ', '.join(missing))

    def paddle_ready(self, profile: str = 'server') -> bool:
        try:
            self.assert_paddle_ready(profile)
            return True
        except RuntimeError:
            return False

    def tesseract_ready(self, profile: str = 'fast') -> bool:
        try:
            self.assert_tesseract_ready(profile)
            return True
        except RuntimeError:
            return False

    def offline_env(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        env = os.environ.copy()
        env.update({
            'HF_HUB_OFFLINE': '1',
            'TRANSFORMERS_OFFLINE': '1',
            'HF_DATASETS_OFFLINE': '1',
            'PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK': 'True',
            'FLAGS_use_mkldnn': '0',
            'PYTHONUTF8': '1',
            'PYTHONIOENCODING': 'utf-8',
        })
        if extra:
            env.update({str(key): str(value) for key, value in extra.items()})
        for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
            env.pop(key, None)
        env['NO_PROXY'] = '*'
        env['no_proxy'] = '*'
        env['KR_B2A_OCR_OFFLINE_ONLY'] = '1'
        return env

    def tesseract_env(self, profile: str = 'fast') -> dict[str, str]:
        env = self.offline_env({'TESSDATA_PREFIX': str(self.tessdata(profile))})
        current = env.get('PATH', '')
        env['PATH'] = str(self.poppler_bin) + os.pathsep + str(self.tesseract.parent) + (os.pathsep + current if current else '')
        return env

    def foundation_status_text(self) -> str:
        report = self.ready_report()
        ready = [key for key, value in report.items() if value]
        missing = [key for key, value in report.items() if not value]
        return f'OCR foundation ready: {", ".join(ready) or "none"}; missing: {", ".join(missing) or "none"}'


def local_ocr_foundation() -> LocalOCRFoundation:
    return LocalOCRFoundation(ocr_runtime_root(), ocr_resource_root())


def install_or_repair_command() -> list[str]:
    if bool(getattr(sys, 'frozen', False)):
        return [str(Path(sys.executable)), '--install-or-repair-ocr-foundation']
    return [str(Path(sys.executable)), '-m', 'kr_book_to_audio.local_ocr_setup', '--activate']


def install_or_repair_foundation() -> dict[str, object]:
    from .subprocess_utils import run_hidden_cli
    command = install_or_repair_command()
    result = run_hidden_cli(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or '').strip()
        raise RuntimeError(f'Local OCR foundation setup failed: {detail or "unknown error"}')
    foundation = local_ocr_foundation()
    report = foundation.ready_report()
    if not all(report.values()):
        raise RuntimeError(f'Local OCR foundation setup completed but remains incomplete: {report}')
    return {
        'runtime_root': str(foundation.runtime_root),
        'resource_root': str(foundation.archive_root),
        'ready': report,
        'stdout': (result.stdout or '').strip(),
    }


def foundation_report_json() -> str:
    foundation = local_ocr_foundation()
    payload = {
        'runtime_root': str(foundation.runtime_root),
        'resource_root': str(foundation.archive_root),
        'ready': foundation.ready_report(),
    }
    return json.dumps(payload, indent=2, sort_keys=True)
