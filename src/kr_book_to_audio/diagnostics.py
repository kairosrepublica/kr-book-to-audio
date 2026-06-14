from __future__ import annotations
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import json
import os
import re

from .manifest import load_manifest
from .models import JobPaths
from .utils import sanitize_filename


def diagnostics_root() -> Path:
    override = os.environ.get('KR_B2A_DIAGNOSTICS_ROOT')
    if override:
        return Path(override)
    return Path.home() / 'Desktop' / 'KR_Book_To_Audio_Diagnostics'


def _app_version() -> str:
    try:
        return version('kr-book-to-audio')
    except PackageNotFoundError:
        return 'source-mode'


def _sanitized_summary(job: JobPaths, manifest: dict) -> dict:
    audio = manifest.get('audio', {})
    execution = manifest.get('execution', {})
    controls = dict(audio.get('controls') or {})
    return {
        'application': 'KR Book To Audio',
        'version': _app_version(),
        'exported_utc': datetime.now().astimezone().isoformat(),
        'job_id': manifest.get('job_id'),
        'title': manifest.get('title'),
        'parts_total': len(manifest.get('parts', [])),
        'parts_completed': len(audio.get('completed', {})),
        'failed_parts': sorted(audio.get('failures', {})),
        'current_part': execution.get('current_part'),
        'current_part_state': execution.get('current_part_state'),
        'execution_status': execution.get('status'),
        'provider_id': controls.get('provider_id') or audio.get('provider_id'),
        'voice': controls.get('voice'),
        'rate': controls.get('rate'),
        'pitch': controls.get('pitch'),
        'volume': controls.get('volume'),
        'last_runtime_telemetry': audio.get('last_runtime_telemetry'),
        'note': 'Sanitized diagnostics exclude book text, MP3 files, credentials and unnecessary absolute paths.',
    }


def _sanitize_log_text(job: JobPaths, text: str) -> str:
    # Replace the most specific paths first. On Windows, the job and export
    # roots commonly live below the user home path. Replacing <USER_HOME>
    # first would shadow the more useful <JOB_ROOT> and <EXPORT_ROOT> tokens.
    replacements: list[tuple[str, str]] = []
    for raw_path, label in (
        (job.export, '<EXPORT_ROOT>'),
        (job.root, '<JOB_ROOT>'),
        (Path.home(), '<USER_HOME>'),
    ):
        raw = str(raw_path)
        if not raw:
            continue
        for variant in {raw, raw.replace('\\', '/'), raw.replace('/', '\\')}:
            if variant:
                replacements.append((variant, label))

    sanitized = text
    for raw, label in sorted(set(replacements), key=lambda item: len(item[0]), reverse=True):
        sanitized = re.sub(re.escape(raw), label, sanitized, flags=re.IGNORECASE)
    return sanitized


def export_diagnostic_zip(job: JobPaths, *, root: Path | None = None) -> Path:
    job = JobPaths.from_root(job.root, export_root=job.export)
    manifest = load_manifest(job)
    destination_root = Path(root or diagnostics_root())
    destination_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    title = sanitize_filename(str(manifest.get('title') or 'job'))
    zip_path = destination_root / f'{stamp}_{title}_diagnostics.zip'
    summary = _sanitized_summary(job, manifest)
    summary_json = json.dumps(summary, ensure_ascii=False, indent=2) + '\n'
    with ZipFile(zip_path, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('diagnostics_summary.json', summary_json)
        if job.run_log.exists():
            archive.writestr('run.log', _sanitize_log_text(job, job.run_log.read_text(encoding='utf-8', errors='replace')))
    return zip_path



def export_prejob_ocr_diagnostic_zip(work_root: Path) -> Path:
    """Export OCR pre-job evidence without requiring a prepared text job."""
    import json
    import shutil
    import tempfile
    import zipfile
    from datetime import datetime, timezone

    work_root = Path(work_root)
    ocr_root = work_root / '_ocr_work'
    target_root = diagnostics_root()
    target_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    zip_path = target_root / f'KR_Book_To_Audio_OCR_PREJOB_DIAGNOSTICS_PRIVATE_{stamp}.zip'
    allowed_names = {'attempt-receipt.json', 'request.json', 'stdout.log', 'stderr.log', 'paddleocr-worker.stderr.log', 'fallback-receipt.json'}
    with tempfile.TemporaryDirectory(prefix='kr-b2a-ocr-prejob-diagnostics-') as tmp:
        stage = Path(tmp)
        manifest = {'mode': 'ocr-prejob-diagnostics', 'generated_at': datetime.now(timezone.utc).isoformat(), 'book_body_included': False, 'mp3_included': False, 'generic_run_log_included': False, 'files': []}
        if ocr_root.is_dir():
            candidates = sorted((item for item in ocr_root.rglob('*') if item.is_file()), key=lambda item: item.stat().st_mtime, reverse=True)
            selected = []
            for source in candidates:
                name = source.name.lower()
                if name in allowed_names or name.endswith('.attempt-receipt.json') or name.endswith('.fallback-receipt.json'):
                    selected.append(source)
                if len(selected) >= 60:
                    break
            for index, source in enumerate(selected, start=1):
                relative = Path('collected') / f'{index:03d}_{source.name}'
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                manifest['files'].append({'path': relative.as_posix(), 'source_name': source.name})
        (stage / 'MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(stage.rglob('*')):
                if item.is_file():
                    archive.write(item, item.relative_to(stage).as_posix())
    return zip_path
