from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import os
import shutil
import subprocess
import tempfile
from .extractors import _decode_stdout, _pdf_sample_pages, diagnose
from .providers import OCR_PROVIDER_SPECS, ProviderUnavailable, get_ocr_provider
from .power import keep_computer_awake
from .utils import atomic_write_json


@dataclass(frozen=True)
class OCRAnalysis:
    status: str
    source_format: str
    language: str
    recommended_provider: str | None
    reason: str
    sample_pages: list[int]
    capabilities: dict[str, dict[str, Any]]
    embedded_text_score: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_language(text: str) -> str:
    compact = ''.join(char for char in text if not char.isspace())
    if not compact:
        return 'uncertain'
    cjk = sum(1 for char in compact if '\u3400' <= char <= '\u9fff')
    latin = sum(1 for char in compact if char.isascii() and char.isalpha())
    if cjk >= 20 and latin >= 20 and min(cjk, latin) / max(cjk, latin) >= 0.12:
        return 'mixed'
    if cjk >= max(10, latin * 2):
        return 'chinese'
    if latin >= max(10, cjk * 2):
        return 'english'
    return 'other'


def quality_score(text: str) -> int:
    compact = [char for char in text if not char.isspace()]
    if not compact:
        return 0
    readable = sum(1 for char in compact if char.isalnum() or '\u3400' <= char <= '\u9fff' or char in '，。、！？；：,.!?;:()[]（）【】')
    length_factor = min(1.0, len(compact) / 800)
    return round(100 * (readable / len(compact)) * (0.5 + 0.5 * length_factor))


def discover_ocr_capabilities() -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for provider_id, spec in OCR_PROVIDER_SPECS.items():
        if provider_id == 'native-text':
            snapshot[provider_id] = {'available': True, 'reason': 'Native text path is built in.', 'spec': spec.to_dict()}
            continue
        try:
            provider = get_ocr_provider(provider_id)
            available, reason = provider.available()
            details: dict[str, Any] = {}
            if provider_id in {'tesseract-local', 'ocrmypdf-tesseract'} and shutil.which('tesseract'):
                language_result = subprocess.run(['tesseract', '--list-langs'], capture_output=True, check=False)
                languages = [line.strip() for line in _decode_stdout(language_result.stdout).splitlines()[1:] if line.strip()]
                details['languages'] = sorted(languages)
        except Exception as exc:
            available, reason, details = False, f'{type(exc).__name__}: {exc}', {}
        snapshot[provider_id] = {'available': bool(available), 'reason': reason, 'details': details, 'spec': spec.to_dict()}
    snapshot['gpu'] = {
        'available': bool(os.environ.get('CUDA_VISIBLE_DEVICES')) or bool(shutil.which('nvidia-smi')),
        'reason': 'GPU discovery is advisory only.',
        'spec': {'provider_id': 'gpu', 'kind': 'capability'},
    }
    return snapshot


def _sample_pdf_text(source: Path, pages: list[int]) -> str:
    if not shutil.which('pdftotext'):
        return ''
    out = []
    for page in pages:
        result = subprocess.run(['pdftotext', '-f', str(page), '-l', str(page), '-layout', str(source), '-'], capture_output=True, check=False)
        if result.returncode == 0:
            out.append(_decode_stdout(result.stdout))
    return '\n'.join(out)


def _tesseract_supports(language: str, capability: dict[str, Any]) -> bool:
    if not capability.get('available'):
        return False
    languages = set(capability.get('details', {}).get('languages', []))
    if not languages:
        return True  # discovery may be mocked or list-langs may be unavailable
    required = {'eng'} if language == 'english' else ({'chi_sim', 'eng'} if language in {'chinese', 'mixed'} else {'eng'})
    return required.issubset(languages)


def _recommend_provider(language: str, capabilities: dict[str, dict[str, Any]]) -> str | None:
    if capabilities.get('paddleocr-ppocrv5', {}).get('available'):
        return 'paddleocr-ppocrv5'
    if _tesseract_supports(language, capabilities.get('tesseract-local', {})):
        return 'tesseract-local'
    if _tesseract_supports(language, capabilities.get('ocrmypdf-tesseract', {})):
        return 'ocrmypdf-tesseract'
    return None


def analyze_source(source: Path) -> OCRAnalysis:
    source = Path(source)
    diagnosis = diagnose(source)
    fmt = str(diagnosis.get('format', source.suffix.lower().lstrip('.')))
    capabilities = discover_ocr_capabilities()
    if fmt != 'pdf':
        return OCRAnalysis('not-applicable', fmt, 'native-text', 'native-text', 'This source already contains native text.', [], capabilities, 100)
    pages = list(diagnosis.get('sample_pages') or _pdf_sample_pages(diagnosis.get('pages')))
    sample = _sample_pdf_text(source, pages)
    language = detect_language(sample)
    score = quality_score(sample)
    if diagnosis.get('extractable'):
        return OCRAnalysis('not-needed', fmt, language, 'native-text', 'A usable embedded text layer was detected. OCR would add cost and can introduce recognition errors.', pages, capabilities, score)
    provider = _recommend_provider(language, capabilities)
    reason = str(diagnosis.get('reason') or 'The PDF text layer is not usable.')
    if provider:
        reason += f' Recommended local provider: {OCR_PROVIDER_SPECS[provider].label}.'
    else:
        reason += ' No supported local OCR provider is currently available. Install PaddleOCR or Tesseract plus Poppler.'
    return OCRAnalysis('required', fmt, language, provider, reason, pages, capabilities, score)


def preview_sample_ocr(source: Path, analysis: OCRAnalysis, *, provider_id: str | None = None) -> dict[str, Any]:
    provider_id = provider_id or analysis.recommended_provider
    if not provider_id or provider_id == 'native-text':
        raise ProviderUnavailable('No OCR provider is required or available for sample preview.')
    provider = get_ocr_provider(provider_id)
    with tempfile.TemporaryDirectory(prefix='kr-b2a-ocr-preview-') as tmp:
        text = provider.recognize_pdf_to_text(Path(source), language=analysis.language, output_dir=Path(tmp), pages=analysis.sample_pages)
    return {'provider_id': provider_id, 'language': analysis.language, 'sample_pages': analysis.sample_pages, 'quality_score': quality_score(text), 'preview_text': text[:4000]}


def run_recommended_ocr(source: Path, analysis: OCRAnalysis, *, output_dir: Path, provider_id: str | None = None, keep_awake: bool = True) -> Path:
    provider_id = provider_id or analysis.recommended_provider
    if not provider_id or provider_id == 'native-text':
        raise ProviderUnavailable('No local OCR provider is available or OCR is not required.')
    provider = get_ocr_provider(provider_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / '_ocr_execution.json'
    provider_capability = bool(getattr(provider, 'page_checkpoint_capable', False))
    atomic_write_json(state_path, {'status': 'running', 'source': str(Path(source)), 'provider_id': provider_id, 'language': analysis.language, 'page_checkpoint_capable': provider_capability})
    try:
        with keep_computer_awake(keep_awake):
            if provider_id == 'ocrmypdf-tesseract':
                target = output_dir / f'{Path(source).stem}_searchable.pdf'
                provider.create_searchable_pdf(Path(source), target, language=analysis.language)  # type: ignore[attr-defined]
            else:
                target = output_dir / f'{Path(source).stem}_ocr.txt'
                with tempfile.TemporaryDirectory(prefix='kr-b2a-ocr-full-') as tmp:
                    text = provider.recognize_pdf_to_text(Path(source), language=analysis.language, output_dir=Path(tmp))
                target.write_text(text, encoding='utf-8', newline='\n')
        atomic_write_json(state_path, {'status': 'completed', 'source': str(Path(source)), 'provider_id': provider_id, 'language': analysis.language, 'page_checkpoint_capable': provider_capability, 'output': str(target)})
        return target
    except Exception as exc:
        atomic_write_json(state_path, {'status': 'interrupted-or-failed', 'source': str(Path(source)), 'provider_id': provider_id, 'language': analysis.language, 'page_checkpoint_capable': provider_capability, 'error': f'{type(exc).__name__}: {exc}'})
        raise
