from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
import os
import shutil

from .manifest import load_manifest, save_manifest
from .models import JobPaths
from .utils import append_job_log, atomic_write_json, sha256_file

Validator = Callable[[Path], dict]
ProgressCallback = Callable[[dict], None]
EXPORT_SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def export_parts_dir(job: JobPaths) -> Path:
    return job.export / 'parts'


def export_manifest_path(job: JobPaths) -> Path:
    return job.export / 'export_manifest.json'


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


def _internal_verified_records(job: JobPaths, manifest: dict, validator: Validator) -> list[dict]:
    signature = manifest.get('audio', {}).get('signature')
    if not signature:
        raise RuntimeError('No approved audio configuration exists for export.')
    completed = manifest.get('audio', {}).get('completed', {})
    verified: list[dict] = []
    for item in _expected_records(manifest):
        index = int(item['index'])
        key = str(index)
        source = job.parts_audio / f'part-{index:04d}.mp3'
        saved = completed.get(key)
        if not saved:
            raise RuntimeError(f'Audio completion record is missing: {source.name}')
        if saved.get('text_sha256') != item.get('sha256'):
            raise RuntimeError(f'Audio text checkpoint is stale: {source.name}')
        if saved.get('signature') != signature:
            raise RuntimeError(f'Audio signature checkpoint is stale: {source.name}')
        metadata = validator(source)
        if metadata.get('sha256') != saved.get('sha256'):
            raise RuntimeError(f'Internal audio changed after validation: {source.name}')
        verified.append({
            'index': index,
            'file': source.name,
            'source_runtime_only': str(source),
            'text_sha256': item['sha256'],
            'signature': signature,
            **metadata,
        })
    return verified


def _atomic_copy(source: Path, destination: Path, validator: Validator) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.stem + '.partial' + destination.suffix)
    partial.unlink(missing_ok=True)
    try:
        with source.open('rb') as src, partial.open('wb') as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        metadata = validator(partial)
        if metadata.get('sha256') != sha256_file(source):
            raise RuntimeError(f'Atomic export copy hash mismatch: {destination.name}')
        os.replace(partial, destination)
        return metadata
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _merged_record(job: JobPaths, manifest: dict, validator: Validator, *, require_merged: bool) -> dict | None:
    merge = manifest.get('merge', {})
    raw = merge.get('output_runtime_only')
    if not raw:
        if require_merged:
            raise RuntimeError('Merged MP3 is required but has not been created.')
        return None
    path = Path(raw)
    if not path.exists():
        if require_merged:
            raise RuntimeError(f'Merged MP3 is missing: {path.name}')
        return None
    metadata = validator(path)
    saved_sha = merge.get('sha256')
    if saved_sha and saved_sha != metadata.get('sha256'):
        raise RuntimeError(f'Merged MP3 changed after validation: {path.name}')
    return {'file': path.name, 'path_runtime_only': str(path), **metadata}


def _verify_export_impl(
    job: JobPaths,
    *,
    validator: Validator | None = None,
    require_merged: bool = False,
    write_manifest: bool = True,
    progress: ProgressCallback | None = None,
) -> dict:
    """Verify the externally deliverable export tree and optionally persist evidence."""
    validator = _validator(validator)
    manifest = load_manifest(job)
    internal = _internal_verified_records(job, manifest, validator)
    expected_names = [item['file'] for item in internal]
    parts_dir = export_parts_dir(job)
    actual_names = sorted(path.name for path in parts_dir.glob('part-*.mp3')) if parts_dir.exists() else []
    if actual_names != expected_names:
        raise RuntimeError(f'Exported Part set mismatch: expected={expected_names!r} actual={actual_names!r}')
    exported: list[dict] = []
    _emit(progress, state='verification-started', total=len(internal))
    append_job_log(job, 'export-verification-started', expected_parts=len(internal))
    for position, item in enumerate(internal, 1):
        path = parts_dir / item['file']
        metadata = validator(path)
        if metadata.get('sha256') != item.get('sha256'):
            raise RuntimeError(f'Exported MP3 SHA-256 mismatch: {path.name}')
        exported.append({'index': item['index'], 'file': item['file'], **metadata})
        _emit(progress, state='verification-part', index=position, total=len(internal), file=item['file'])
    merged = _merged_record(job, manifest, validator, require_merged=require_merged)
    report = {
        'schema_version': EXPORT_SCHEMA_VERSION,
        'status': 'verified',
        'verified_utc': _utc_now(),
        'job_id': manifest.get('job_id'),
        'title': manifest.get('title'),
        'expected_parts': len(internal),
        'exported_parts': len(exported),
        'parts': exported,
        'merged': merged,
    }
    if write_manifest:
        atomic_write_json(export_manifest_path(job), report)
        manifest['export'] = {
            'status': 'verified',
            'verified_utc': report['verified_utc'],
            'manifest_runtime_only': str(export_manifest_path(job)),
            'parts_dir_runtime_only': str(parts_dir),
            'expected_parts': len(internal),
            'exported_parts': len(exported),
            'merged_present': bool(merged),
        }
        save_manifest(job, manifest)
    append_job_log(job, 'export-verification-pass', exported_parts=len(exported), merged_present=bool(merged))
    _emit(progress, state='verification-pass', total=len(exported), merged_present=bool(merged))
    return report


def verify_export(
    job: JobPaths,
    *,
    validator: Validator | None = None,
    require_merged: bool = False,
    write_manifest: bool = True,
    progress: ProgressCallback | None = None,
) -> dict:
    try:
        return _verify_export_impl(
            job,
            validator=validator,
            require_merged=require_merged,
            write_manifest=write_manifest,
            progress=progress,
        )
    except Exception as exc:
        message = f'{type(exc).__name__}: {exc}'
        append_job_log(job, 'export-verification-failed', error=message)
        _emit(progress, state='verification-failed', error=message)
        raise


def _finalize_export_impl(
    job: JobPaths,
    *,
    validator: Validator | None = None,
    progress: ProgressCallback | None = None,
) -> dict:
    """Materialize a verified public export tree from authoritative internal checkpoints."""
    validator = _validator(validator)
    manifest = load_manifest(job)
    internal = _internal_verified_records(job, manifest, validator)
    parts_dir = export_parts_dir(job)
    parts_dir.mkdir(parents=True, exist_ok=True)
    expected_names = {item['file'] for item in internal}
    append_job_log(job, 'export-finalization-started', expected_parts=len(internal), destination=str(parts_dir))
    _emit(progress, state='finalization-started', total=len(internal), destination=str(parts_dir))
    for position, item in enumerate(internal, 1):
        destination = parts_dir / item['file']
        source = Path(item['source_runtime_only'])
        if destination.exists():
            try:
                metadata = validator(destination)
                if metadata.get('sha256') == item.get('sha256'):
                    _emit(progress, state='copy-reused', index=position, total=len(internal), file=item['file'])
                    continue
            except Exception:
                pass
            destination.unlink(missing_ok=True)
        _emit(progress, state='copying-part', index=position, total=len(internal), file=item['file'])
        append_job_log(job, 'export-copying-part', index=position, total=len(internal), file=item['file'])
        copied = _atomic_copy(source, destination, validator)
        if copied.get('sha256') != item.get('sha256'):
            raise RuntimeError(f'Exported MP3 SHA-256 mismatch after atomic copy: {item["file"]}')
    for path in parts_dir.glob('part-*.mp3'):
        if path.name not in expected_names:
            path.unlink(missing_ok=True)
    report = verify_export(job, validator=validator, write_manifest=True, progress=progress)
    append_job_log(job, 'export-finalization-completed', exported_parts=report['exported_parts'])
    _emit(progress, state='finalization-completed', total=report['exported_parts'])
    return report


def finalize_export(
    job: JobPaths,
    *,
    validator: Validator | None = None,
    progress: ProgressCallback | None = None,
) -> dict:
    try:
        return _finalize_export_impl(job, validator=validator, progress=progress)
    except Exception as exc:
        message = f'{type(exc).__name__}: {exc}'
        append_job_log(job, 'export-finalization-failed', error=message)
        _emit(progress, state='finalization-failed', error=message)
        raise


def export_is_verified(job: JobPaths) -> bool:
    try:
        manifest = load_manifest(job)
    except Exception:
        return False
    record = manifest.get('export', {})
    return bool(
        record.get('status') == 'verified'
        and export_manifest_path(job).exists()
        and export_parts_dir(job).exists()
    )
