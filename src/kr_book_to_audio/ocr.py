from __future__ import annotations
from dataclasses import dataclass, asdict
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable
from datetime import datetime, timezone
import threading
import json
import os
import shutil
import tempfile
import time
from .subprocess_utils import run_hidden_cli
from .extractors import _decode_stdout, _pdf_sample_pages, diagnose
from .providers import OCR_PROVIDER_SPECS, ProviderUnavailable, get_ocr_provider
from .power import keep_computer_awake
from .utils import atomic_write_json, atomic_write_text, sanitize_filename

OCRProgressCallback = Callable[[dict[str, object]], None]


class OCRCancelled(RuntimeError):
    pass


class OCRControl:
    '''Thread-safe cooperative OCR control. Pause and cancel apply between durable page checkpoints.'''
    def __init__(self) -> None:
        self._paused = threading.Event()
        self._cancelled = threading.Event()

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def cancel(self) -> None:
        self._cancelled.set()
        self._paused.clear()

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def wait_until_runnable(
        self,
        *,
        progress: OCRProgressCallback | None,
        started: float,
        completed_pages: int,
        total_pages: int,
        last_completed_page: int | None,
    ) -> None:
        if self.cancelled:
            raise OCRCancelled('OCR cancelled by the user. Completed page checkpoints were preserved.')
        emitted_pause = False
        while self.paused:
            if self.cancelled:
                raise OCRCancelled('OCR cancelled by the user. Completed page checkpoints were preserved.')
            if not emitted_pause:
                _emit(progress, event='ocr', state='ocr-paused', completed_pages=completed_pages, total_pages=total_pages, **_runtime_metrics(started, completed_pages, total_pages, last_completed_page))
                emitted_pause = True
            time.sleep(0.2)
        if emitted_pause:
            _emit(progress, event='ocr', state='ocr-resumed', completed_pages=completed_pages, total_pages=total_pages, **_runtime_metrics(started, completed_pages, total_pages, last_completed_page))



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
            if provider_id.startswith('tesseract-local') and available:
                details['languages'] = sorted(getattr(provider, 'installed_languages')())
        except Exception as exc:
            available, reason, details = False, f'{type(exc).__name__}: {exc}', {}
        snapshot[provider_id] = {'available': bool(available), 'reason': reason, 'details': details, 'spec': spec.to_dict()}
    snapshot['gpu'] = {
        'available': bool(os.environ.get('CUDA_VISIBLE_DEVICES')) or bool(shutil.which('nvidia-smi')),
        'reason': 'GPU discovery is advisory only. v2.5.0 OCR defaults to broad-compatibility CPU execution.',
        'spec': {'provider_id': 'gpu', 'kind': 'capability'},
    }
    return snapshot


def _pdftotext_command() -> str | None:
    found = shutil.which('pdftotext')
    if found:
        return found
    try:
        from .local_ocr import local_ocr_foundation
        candidate = local_ocr_foundation().pdftotext
        return str(candidate) if candidate.is_file() else None
    except Exception:
        return None


def _sample_pdf_text(source: Path, pages: list[int]) -> str:
    command = _pdftotext_command()
    if not command:
        return ''
    out = []
    for page in pages:
        result = run_hidden_cli([command, '-f', str(page), '-l', str(page), '-layout', str(source), '-'], capture_output=True, check=False)
        if result.returncode == 0:
            out.append(_decode_stdout(result.stdout))
    return '\n'.join(out)


def _tesseract_supports(language: str, capability: dict[str, Any]) -> bool:
    if not capability.get('available'):
        return False
    languages = set(capability.get('details', {}).get('languages', []))
    if not languages:
        return True
    required = {'eng'} if language == 'english' else ({'chi_sim', 'eng'} if language in {'chinese', 'mixed', 'uncertain'} else {'eng'})
    return required.issubset(languages)


def _recommend_provider(language: str, capabilities: dict[str, dict[str, Any]]) -> str | None:
    for provider_id in ('paddleocr-ppocrv5-mobile', 'paddleocr-ppocrv5'):
        if capabilities.get(provider_id, {}).get('available'):
            return provider_id
    for provider_id in ('tesseract-local-best', 'tesseract-local'):
        if _tesseract_supports(language, capabilities.get(provider_id, {})):
            return provider_id
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
        reason += ' Local OCR foundation is missing or incomplete. Use Install / repair local OCR foundation.'
    return OCRAnalysis('required', fmt, language, provider, reason, pages, capabilities, score)


def preview_sample_ocr(
    source: Path,
    analysis: OCRAnalysis,
    *,
    provider_id: str | None = None,
    progress: OCRProgressCallback | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    provider_id = provider_id or analysis.recommended_provider
    if not provider_id or provider_id == 'native-text':
        raise ProviderUnavailable('No OCR provider is required or available for sample preview.')
    provider = get_ocr_provider(provider_id)
    started = time.monotonic()
    if output_dir is None:
        with tempfile.TemporaryDirectory(prefix='kr-b2a-ocr-preview-') as tmp:
            text = provider.recognize_pdf_to_text(Path(source), language=analysis.language, output_dir=Path(tmp), pages=analysis.sample_pages, progress=progress)
        return {'provider_id': provider_id, 'language': analysis.language, 'sample_pages': analysis.sample_pages, 'quality_score': quality_score(text), 'preview_text': text[:12000], 'elapsed_seconds': round(time.monotonic() - started, 3)}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    text = provider.recognize_pdf_to_text(Path(source), language=analysis.language, output_dir=output_dir, pages=analysis.sample_pages, progress=progress)
    sample_text = output_dir / 'ocr_preview_sample.txt'
    summary = output_dir / 'ocr_preview_summary.json'
    elapsed = round(time.monotonic() - started, 3)
    atomic_write_text(sample_text, text.strip() + '\n')
    payload = {
        'provider_id': provider_id,
        'language': analysis.language,
        'sample_pages': analysis.sample_pages,
        'quality_score': quality_score(text),
        'preview_text': text[:12000],
        'elapsed_seconds': elapsed,
        'average_seconds_per_page': round(elapsed / max(1, len(analysis.sample_pages)), 3),
        'output_dir': str(output_dir),
        'sample_text': str(sample_text),
    }
    atomic_write_json(summary, payload)
    return payload


def _source_sha256(source: Path) -> str:
    digest = sha256()
    with Path(source).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _source_token(source: Path, source_sha256: str | None = None) -> str:
    source = Path(source)
    fingerprint = source_sha256 or _source_sha256(source)
    digest = sha256((str(source.resolve()) + '\0' + fingerprint).encode('utf-8', 'replace')).hexdigest()[:12]
    return sanitize_filename(source.stem, 'book') + '-' + digest


def _runtime_metrics(started: float, completed_pages: int, total_pages: int, last_completed_page: int | None = None) -> dict[str, object]:
    elapsed = round(time.monotonic() - started, 3)
    average = round(elapsed / completed_pages, 3) if completed_pages else 0.0
    remaining = round(max(total_pages - completed_pages, 0) * average, 3) if completed_pages else None
    return {
        'elapsed_seconds': elapsed,
        'last_completed_page': last_completed_page,
        'average_seconds_per_page': average,
        'estimated_remaining_seconds': remaining,
    }


def _read_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _emit(progress: OCRProgressCallback | None, **payload: object) -> None:
    if progress:
        progress(payload)


def run_recommended_ocr(
    source: Path,
    analysis: OCRAnalysis,
    *,
    output_dir: Path,
    provider_id: str | None = None,
    keep_awake: bool = True,
    progress: OCRProgressCallback | None = None,
    export_dir: Path | None = None,
    control: OCRControl | None = None,
) -> Path:
    provider_id = provider_id or analysis.recommended_provider
    if not provider_id or provider_id == 'native-text':
        raise ProviderUnavailable('No local OCR provider is available or OCR is not required.')
    provider = get_ocr_provider(provider_id)
    source = Path(source)
    output_dir = Path(output_dir)
    export_dir = Path(export_dir) if export_dir is not None else None
    control = control or OCRControl()
    source_sha256 = _source_sha256(source)
    execution_dir = output_dir / _source_token(source, source_sha256)
    pages_dir = execution_dir / 'pages'
    attempts_dir = execution_dir / 'attempts'
    failed_dir = execution_dir / 'failed-pages'
    for folder in (pages_dir, attempts_dir, failed_dir):
        folder.mkdir(parents=True, exist_ok=True)
    state_path = execution_dir / '_ocr_execution.json'
    try:
        diagnosis = diagnose(source)
    except Exception:
        diagnosis = {}
    total_pages = int(diagnosis.get('pages') or max(analysis.sample_pages or [0]))
    if total_pages <= 0:
        raise RuntimeError('OCR cannot start because the PDF page count could not be determined.')
    if not bool(getattr(provider, 'page_checkpoint_capable', False)):
        raise ProviderUnavailable(f'OCR Provider does not support durable page checkpoints: {provider_id}')
    prior = _read_state(state_path)
    completed = {int(page) for page in prior.get('completed_pages', []) if str(page).isdigit() and (pages_dir / f'page-{int(page):04d}.txt').is_file()}
    failed = {int(page) for page in prior.get('failed_pages', []) if str(page).isdigit()}
    started = time.monotonic()
    cooldown_seconds = max(0.0, float(os.environ.get('KR_B2A_OCR_PAGE_COOLDOWN_SECONDS', '2')))
    batch_cooldown_seconds = max(0.0, float(os.environ.get('KR_B2A_OCR_BATCH_COOLDOWN_SECONDS', '30')))
    batch_size = max(1, int(os.environ.get('KR_B2A_OCR_BATCH_SIZE', '20')))
    base_state: dict[str, Any] = {
        'status': 'running', 'source': str(source.resolve()), 'source_sha256': source_sha256,
        'provider_id': provider_id, 'language': analysis.language, 'page_checkpoint_capable': True,
        'total_pages': total_pages, 'completed_pages': sorted(completed), 'failed_pages': sorted(failed),
        'offline_mode_enforced': True,
    }
    atomic_write_json(state_path, base_state)
    atomic_write_json(output_dir / '_ocr_execution.json', base_state)
    _emit(progress, event='ocr', state='ocr-started', provider_id=provider_id, completed_pages=len(completed), total_pages=total_pages, **_runtime_metrics(started, len(completed), total_pages, max(completed) if completed else None))
    with keep_computer_awake(keep_awake):
        for page in range(1, total_pages + 1):
            control.wait_until_runnable(progress=progress, started=started, completed_pages=len(completed), total_pages=total_pages, last_completed_page=max(completed) if completed else None)
            page_path = pages_dir / f'page-{page:04d}.txt'
            if page in completed and page_path.is_file():
                _emit(progress, event='ocr', state='ocr-page-reused', provider_id=provider_id, page=page, completed_pages=len(completed), total_pages=total_pages, **_runtime_metrics(started, len(completed), total_pages, page))
                continue
            _emit(progress, event='ocr', state='ocr-page-started', phase='starting offline OCR page', provider_id=provider_id, page=page, completed_pages=len(completed), total_pages=total_pages, **_runtime_metrics(started, len(completed), total_pages, max(completed) if completed else None))
            page_attempt_dir = attempts_dir / f'page-{page:04d}'
            page_attempt_dir.mkdir(parents=True, exist_ok=True)
            try:
                text = provider.recognize_pdf_to_text(source, language=analysis.language, output_dir=page_attempt_dir, pages=[page], progress=progress)
                if control.cancelled:
                    raise OCRCancelled('OCR cancelled by the user. Completed page checkpoints were preserved.')
                atomic_write_text(page_path, text.strip() + '\n')
                completed.add(page)
                failed.discard(page)
                metrics = _runtime_metrics(started, len(completed), total_pages, page)
                base_state.update({'status': 'running', 'completed_pages': sorted(completed), 'failed_pages': sorted(failed), **metrics})
                atomic_write_json(state_path, base_state)
                atomic_write_json(output_dir / '_ocr_execution.json', base_state)
                _emit(progress, event='ocr', state='ocr-page-completed', phase='saved page checkpoint', provider_id=provider_id, page=page, completed_pages=len(completed), total_pages=total_pages, **metrics)
            except OCRCancelled:
                raise
            except Exception as exc:
                failed.add(page)
                failure = {'page': page, 'error': f'{type(exc).__name__}: {exc}', 'failed_at': datetime.now(timezone.utc).isoformat()}
                atomic_write_json(failed_dir / f'page-{page:04d}.json', failure)
                metrics = _runtime_metrics(started, len(completed), total_pages, max(completed) if completed else None)
                base_state.update({'status': 'running-with-page-failures', 'completed_pages': sorted(completed), 'failed_pages': sorted(failed), **metrics})
                atomic_write_json(state_path, base_state)
                atomic_write_json(output_dir / '_ocr_execution.json', base_state)
                _emit(progress, event='ocr', state='ocr-page-failed-continued', phase='page failed; continuing', provider_id=provider_id, page=page, completed_pages=len(completed), total_pages=total_pages, failed_pages=len(failed), error=failure['error'], **metrics)
            if cooldown_seconds:
                time.sleep(cooldown_seconds)
            if page % batch_size == 0 and batch_cooldown_seconds:
                _emit(progress, event='ocr', state='ocr-batch-cooldown', phase='laptop cooldown', provider_id=provider_id, page=page, completed_pages=len(completed), total_pages=total_pages, cooldown_seconds=batch_cooldown_seconds, **_runtime_metrics(started, len(completed), total_pages, page))
                time.sleep(batch_cooldown_seconds)
    stem = sanitize_filename(source.stem, 'book')
    working_target = output_dir / f'{stem}_ocr.txt'
    chunks = []
    for page in range(1, total_pages + 1):
        page_path = pages_dir / f'page-{page:04d}.txt'
        chunks.append(page_path.read_text(encoding='utf-8', errors='replace').strip() if page_path.is_file() else f'[OCR FAILED PAGE {page}]')
    combined = '\n\n'.join(chunks).strip() + '\n'
    atomic_write_text(working_target, combined)
    metrics = _runtime_metrics(started, len(completed), total_pages, max(completed) if completed else None)
    target = working_target
    final_status = 'completed-with-page-failures' if failed else 'completed'
    if export_dir is not None:
        export_dir.mkdir(parents=True, exist_ok=True)
        raw_target = export_dir / f'{stem}_ocr_raw.txt'
        review_target = export_dir / f'{stem}_ocr_review.txt'
        summary_target = export_dir / f'{stem}_ocr_summary.json'
        atomic_write_text(raw_target, combined)
        atomic_write_text(review_target, combined)
        atomic_write_json(summary_target, {'status': final_status, 'source': str(source.resolve()), 'provider_id': provider_id, 'language': analysis.language, 'total_pages': total_pages, 'completed_pages': sorted(completed), 'failed_pages': sorted(failed), 'working_output': str(working_target), 'review_output': str(review_target), 'raw_output': str(raw_target), **metrics})
        target = review_target
    base_state.update({'status': final_status, 'completed_pages': sorted(completed), 'failed_pages': sorted(failed), 'output': str(target), 'working_output': str(working_target), **metrics})
    atomic_write_json(state_path, base_state)
    atomic_write_json(output_dir / '_ocr_execution.json', base_state)
    _emit(progress, event='ocr', state='ocr-completed-with-page-failures' if failed else 'ocr-completed', phase='full OCR pass completed', provider_id=provider_id, completed_pages=len(completed), total_pages=total_pages, failed_pages=len(failed), output=str(target), working_output=str(working_target), **metrics)
    return target


def retry_failed_ocr_pages(source: Path, analysis: OCRAnalysis, *, output_dir: Path, provider_id: str | None = None, keep_awake: bool = True, progress: OCRProgressCallback | None = None, export_dir: Path | None = None, control: OCRControl | None = None) -> Path:
    return run_recommended_ocr(source, analysis, output_dir=output_dir, provider_id=provider_id, keep_awake=keep_awake, progress=progress, export_dir=export_dir, control=control)
