from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
import shutil

from .manifest import load_manifest, save_manifest
from .models import JobPaths
from .utils import append_job_log, atomic_write_json, atomic_write_text, sanitize_filename, sha256_file, sha256_text
from .durable_io import copy_verified, cleanup_stale_partials, replace_with_retry, unique_partial_path

Validator = Callable[[Path], dict]
ProgressCallback = Callable[[dict], None]
EXPORT_SCHEMA_VERSION = 3


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def export_parts_dir(job: JobPaths) -> Path:
    """Return the flat human-facing export root.

    Historical releases exposed a nested ``parts`` directory. v2.4.0 keeps all
    user-facing MP3 files directly in the book export root.
    """
    return job.export


def legacy_export_parts_dir(job: JobPaths) -> Path:
    return job.export / 'parts'


def export_manifest_path(job: JobPaths) -> Path:
    """Keep machine-facing export receipts internal, outside the human deliverable."""
    return job.work / 'export_manifest.json'


def legacy_export_manifest_path(job: JobPaths) -> Path:
    return job.export / 'export_manifest.json'


def cleaned_text_export_path(job: JobPaths, manifest: dict | None = None) -> Path:
    manifest = manifest or load_manifest(job)
    title = sanitize_filename(str(manifest.get('title') or 'cleaned-text'))
    return job.export / f'{title}.txt'


def _validator(validator: Validator | None) -> Validator:
    if validator is not None:
        return validator
    from .audio import validate_mp3
    return validate_mp3


def _emit(progress: ProgressCallback | None, **payload: object) -> None:
    if progress:
        progress({'event': 'export', **payload})


def _expected_records(manifest: dict) -> list[dict]:
    records = sorted(manifest.get('parts', []), key=lambda item: int(item['index']))
    if not records:
        raise RuntimeError('No manifest-declared audio parts exist for export.')
    expected = list(range(1, len(records) + 1))
    actual = [int(item['index']) for item in records]
    if actual != expected:
        raise RuntimeError(f'Manifest Part indexes are not continuous: expected={expected!r} actual={actual!r}')
    return records


def _receipt_metadata(path: Path, receipt: dict) -> dict | None:
    if not path.exists() or path.stat().st_size <= 1024:
        return None
    expected_sha = str(receipt.get('sha256') or '')
    if not expected_sha or sha256_file(path) != expected_sha:
        return None
    duration = receipt.get('duration_seconds')
    if not isinstance(duration, (int, float)) or float(duration) <= 0:
        return None
    return {
        'bytes': int(path.stat().st_size),
        'duration_seconds': float(duration),
        'sha256': expected_sha,
        'verification_receipt': 'reused',
    }


def _internal_verified_records(job: JobPaths, manifest: dict, validator: Validator) -> tuple[list[dict], int]:
    signature = manifest.get('audio', {}).get('signature')
    if not signature:
        raise RuntimeError('No approved audio configuration exists for export.')
    completed = manifest.get('audio', {}).get('completed', {})
    verified: list[dict] = []
    reused_receipts = 0
    for item in _expected_records(manifest):
        index = int(item['index'])
        source = job.parts_audio / f'part-{index:04d}.mp3'
        saved = completed.get(str(index))
        if not saved:
            raise RuntimeError(f'Audio completion record is missing: {source.name}')
        if saved.get('text_sha256') != item.get('sha256'):
            raise RuntimeError(f'Audio text checkpoint is stale: {source.name}')
        if saved.get('signature') != signature:
            raise RuntimeError(f'Audio signature checkpoint is stale: {source.name}')
        metadata = _receipt_metadata(source, saved)
        if metadata is None:
            metadata = validator(source)
            if metadata.get('sha256') != saved.get('sha256'):
                raise RuntimeError(f'Internal audio changed after validation: {source.name}')
        else:
            reused_receipts += 1
        verified.append({
            'index': index,
            'file': source.name,
            'source_runtime_only': str(source),
            'text_sha256': item['sha256'],
            'signature': signature,
            **metadata,
        })
    return verified, reused_receipts


def _atomic_copy(source: Path, destination: Path, validator: Validator) -> dict:
    """Compatibility helper: durable copy plus explicit validation for negative fixtures."""
    source = Path(source); destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    cleanup_stale_partials(destination)
    partial = unique_partial_path(destination, before_suffix=True)
    try:
        with source.open('rb') as src, partial.open('wb') as dst:
            import os
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush(); os.fsync(dst.fileno())
        metadata = validator(partial)
        if metadata.get('sha256') != sha256_file(source):
            raise RuntimeError(f'Atomic export copy hash mismatch: {destination.name}')
        replace_with_retry(partial, destination)
        return metadata
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _copy_with_receipt(source: Path, destination: Path, receipt: dict) -> dict:
    destination = Path(destination)
    expected = str(receipt['sha256'])
    if destination.exists():
        if not destination.is_file():
            raise RuntimeError(f'Export conflict: expected a file but found another object: {destination.name}')
        existing_sha = sha256_file(destination)
        if existing_sha != expected:
            raise RuntimeError(f'Export conflict: existing file differs and will not be overwritten: {destination.name}')
        return {
            'bytes': int(destination.stat().st_size),
            'duration_seconds': float(receipt['duration_seconds']),
            'sha256': expected,
            'verification_receipt': 'reused-existing-export',
        }
    copied_sha = copy_verified(source, destination, expected_sha256=expected)
    if copied_sha != expected:
        raise RuntimeError(f'Exported MP3 SHA-256 mismatch after durable copy: {destination.name}')
    return {
        'bytes': int(destination.stat().st_size),
        'duration_seconds': float(receipt['duration_seconds']),
        'sha256': copied_sha,
        'verification_receipt': 'reused-after-copy',
    }


def _write_cleaned_text(job: JobPaths, manifest: dict) -> Path:
    if not job.proofread.exists():
        raise RuntimeError('Reviewed cleaned text is missing. Approve reviewed text and rebuild first.')
    destination = cleaned_text_export_path(job, manifest)
    text = job.proofread.read_text(encoding='utf-8')
    if destination.exists() and destination.is_file():
        existing = destination.read_text(encoding='utf-8')
        if sha256_text(existing) != sha256_text(text):
            raise RuntimeError(f'Export conflict: existing cleaned TXT differs and will not be overwritten: {destination.name}')
        return destination
    if destination.exists():
        raise RuntimeError(f'Export conflict: expected a TXT file but found another object: {destination.name}')
    atomic_write_text(destination, text)
    return destination


def _migrate_legacy_export(job: JobPaths, internal: list[dict]) -> None:
    legacy_parts = legacy_export_parts_dir(job)
    if legacy_parts.exists():
        if not legacy_parts.is_dir():
            raise RuntimeError('Legacy export conflict: parts exists but is not a directory.')
        expected_by_name = {item['file']: item for item in internal}
        for candidate in legacy_parts.iterdir():
            if candidate.is_dir():
                raise RuntimeError(f'Legacy export contains an unexpected subdirectory: {candidate.name}')
            if candidate.name not in expected_by_name:
                raise RuntimeError(f'Legacy export contains an unexpected file: parts/{candidate.name}')
            destination = job.export / candidate.name
            expected = str(expected_by_name[candidate.name]['sha256'])
            if sha256_file(candidate) != expected:
                raise RuntimeError(f'Legacy exported MP3 changed after validation: {candidate.name}')
            if destination.exists():
                if not destination.is_file() or sha256_file(destination) != expected:
                    raise RuntimeError(f'Export conflict: cannot flatten legacy file safely: {candidate.name}')
                candidate.unlink()
            else:
                candidate.replace(destination)
        if any(legacy_parts.iterdir()):
            raise RuntimeError('Legacy parts directory could not be emptied safely.')
        legacy_parts.rmdir()
    legacy_manifest = legacy_export_manifest_path(job)
    if legacy_manifest.exists():
        if not legacy_manifest.is_file():
            raise RuntimeError('Legacy export conflict: export_manifest.json is not a regular file.')
        legacy_manifest.unlink()


def _assert_flat_user_export(job: JobPaths, expected_names: set[str]) -> None:
    if not job.export.exists():
        raise RuntimeError('Final Export folder does not exist.')
    actual_files: set[str] = set()
    for item in job.export.iterdir():
        if item.is_dir():
            raise RuntimeError(f'Final Export folder must remain flat. Unexpected directory: {item.name}')
        actual_files.add(item.name)
    if actual_files != expected_names:
        raise RuntimeError(f'Exported Part set mismatch / Final Export set mismatch: expected={sorted(expected_names)!r} actual={sorted(actual_files)!r}')


def _merged_record(job: JobPaths, manifest: dict, validator: Validator, *, require_merged: bool) -> tuple[dict | None, int]:
    merge = manifest.get('merge', {})
    raw = merge.get('output_runtime_only')
    if not raw:
        if require_merged:
            raise RuntimeError('Merged MP3 is required but has not been created.')
        return None, 0
    path = Path(raw)
    if not path.exists():
        if require_merged:
            raise RuntimeError(f'Merged MP3 is missing: {path.name}')
        return None, 0
    metadata = _receipt_metadata(path, merge)
    reused = 1 if metadata is not None else 0
    if metadata is None:
        metadata = validator(path)
    saved_sha = merge.get('sha256')
    if saved_sha and saved_sha != metadata.get('sha256'):
        raise RuntimeError(f'Merged MP3 changed after validation: {path.name}')
    return {'file': path.name, 'path_runtime_only': str(path), **metadata}, reused


def _verify_export_impl(
    job: JobPaths,
    *,
    validator: Validator | None = None,
    require_merged: bool = False,
    write_manifest: bool = True,
    progress: ProgressCallback | None = None,
) -> dict:
    validator = _validator(validator)
    manifest = load_manifest(job)
    internal, internal_receipts = _internal_verified_records(job, manifest, validator)
    expected_audio_names = [item['file'] for item in internal]
    text_path = cleaned_text_export_path(job, manifest)
    merged, merged_receipts = _merged_record(job, manifest, validator, require_merged=require_merged)
    expected_flat_names = set(expected_audio_names + [text_path.name])
    if merged:
        expected_flat_names.add(str(merged['file']))
    _assert_flat_user_export(job, expected_flat_names)
    exported: list[dict] = []
    exported_receipts = 0
    _emit(progress, state='verification-started', total=len(internal))
    append_job_log(job, 'export-verification-started', expected_parts=len(internal), flat_export=True)
    for position, item in enumerate(internal, 1):
        path = job.export / item['file']
        metadata = _receipt_metadata(path, item)
        if metadata is None:
            metadata = validator(path)
        else:
            exported_receipts += 1
        if metadata.get('sha256') != item.get('sha256'):
            raise RuntimeError(f'Exported MP3 SHA-256 mismatch: {path.name}')
        exported.append({'index': item['index'], 'file': item['file'], **metadata})
        _emit(progress, state='verification-part', index=position, total=len(internal), file=item['file'])
    if sha256_text(text_path.read_text(encoding='utf-8')) != sha256_text(job.proofread.read_text(encoding='utf-8')):
        raise RuntimeError(f'Exported cleaned TXT differs from approved reviewed text: {text_path.name}')
    report = {
        'schema_version': EXPORT_SCHEMA_VERSION,
        'status': 'verified',
        'verified_utc': _utc_now(),
        'job_id': manifest.get('job_id'),
        'title': manifest.get('title'),
        'expected_parts': len(internal),
        'exported_parts': len(exported),
        'flat_export': True,
        'cleaned_text': {'file': text_path.name, 'sha256': sha256_text(text_path.read_text(encoding='utf-8'))},
        'receipt_reuse': {
            'internal_parts': internal_receipts,
            'exported_parts': exported_receipts,
            'merged': merged_receipts,
        },
        'parts': exported,
        'merged': merged,
    }
    if write_manifest:
        atomic_write_json(export_manifest_path(job), report)
        manifest['export'] = {
            'status': 'verified',
            'verified_utc': report['verified_utc'],
            'manifest_runtime_only': str(export_manifest_path(job)),
            'parts_dir_runtime_only': str(job.export),
            'expected_parts': len(internal),
            'exported_parts': len(exported),
            'cleaned_text_runtime_only': str(text_path),
            'flat_export': True,
            'merged_present': bool(merged),
            'receipt_reuse': report['receipt_reuse'],
        }
        save_manifest(job, manifest)
    append_job_log(job, 'export-verification-pass', exported_parts=len(exported), cleaned_text=text_path.name, flat_export=True, merged_present=bool(merged), receipt_reuse=report['receipt_reuse'])
    _emit(progress, state='verification-pass', total=len(exported), flat_export=True, merged_present=bool(merged), receipt_reuse=report['receipt_reuse'])
    return report


def verify_export(job: JobPaths, *, validator: Validator | None = None, require_merged: bool = False, write_manifest: bool = True, progress: ProgressCallback | None = None) -> dict:
    try:
        return _verify_export_impl(job, validator=validator, require_merged=require_merged, write_manifest=write_manifest, progress=progress)
    except Exception as exc:
        message = f'{type(exc).__name__}: {exc}'
        append_job_log(job, 'export-verification-failed', error=message)
        _emit(progress, state='verification-failed', error=message)
        raise


def _finalize_export_impl(job: JobPaths, *, validator: Validator | None = None, progress: ProgressCallback | None = None) -> dict:
    validator = _validator(validator)
    manifest = load_manifest(job)
    internal, reused_receipts = _internal_verified_records(job, manifest, validator)
    job.export.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_export(job, internal)
    _emit(progress, state='finalization-started', total=len(internal), receipt_reuse=reused_receipts, flat_export=True)
    append_job_log(job, 'export-finalization-started', expected_parts=len(internal), internal_receipts_reused=reused_receipts, flat_export=True)
    for position, item in enumerate(internal, 1):
        source = Path(item['source_runtime_only'])
        destination = job.export / item['file']
        if destination.exists() and destination.is_file() and sha256_file(destination) == item['sha256']:
            _emit(progress, state='copy-reused', index=position, total=len(internal), file=item['file'])
            continue
        _emit(progress, state='copying-part', index=position, total=len(internal), file=item['file'])
        _copy_with_receipt(source, destination, item)
    text_path = _write_cleaned_text(job, manifest)
    _emit(progress, state='writing-cleaned-text', file=text_path.name)
    report = _verify_export_impl(job, validator=validator, write_manifest=True, progress=progress)
    append_job_log(job, 'export-finalization-completed', exported_parts=report['exported_parts'], cleaned_text=text_path.name, flat_export=True)
    _emit(progress, state='finalization-completed', total=report['exported_parts'], cleaned_text=text_path.name, flat_export=True)
    return report


def finalize_export(job: JobPaths, *, validator: Validator | None = None, progress: ProgressCallback | None = None) -> dict:
    try:
        return _finalize_export_impl(job, validator=validator, progress=progress)
    except Exception as exc:
        export_manifest_path(job).unlink(missing_ok=True)
        message = f'{type(exc).__name__}: {exc}'
        append_job_log(job, 'export-finalization-failed', error=message)
        _emit(progress, state='finalization-failed', error=message)
        raise


def export_is_verified(job: JobPaths, *, validator: Validator | None = None) -> bool:
    try:
        return verify_export(job, validator=validator, write_manifest=False).get('status') == 'verified'
    except Exception:
        return False
