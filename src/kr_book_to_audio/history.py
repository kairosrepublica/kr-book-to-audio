from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
from .config import execution_history_path, local_work_root
from .models import JobPaths
from .utils import atomic_write_json

HISTORY_SCHEMA_VERSION = 1
MAX_RECENT_JOBS = 20


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_history() -> dict[str, Any]:
    return {'schema_version': HISTORY_SCHEMA_VERSION, 'updated_utc': _utc_now(), 'jobs': []}


def _entry_manifest_path(entry: dict[str, Any]) -> Path | None:
    raw = str(entry.get('job_root') or '').strip()
    if not raw:
        return None
    return Path(raw) / '_work' / 'job_manifest.json'


def _entry_is_valid(entry: dict[str, Any]) -> bool:
    manifest = _entry_manifest_path(entry)
    return bool(manifest and manifest.is_file())


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


def format_last_active(value: str | None) -> str:
    parsed = _parse_utc(value)
    if not parsed:
        return 'Unknown'
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().strftime('%Y-%m-%d %H:%M')


def display_status(entry: dict[str, Any]) -> str:
    if entry.get('interrupted'):
        return 'Interrupted · resume'
    if int(entry.get('failed_parts') or 0):
        return 'Failed · retry'
    total = int(entry.get('total_parts') or 0)
    completed = int(entry.get('completed_parts') or 0)
    if total and completed >= total:
        return 'Completed'
    if total:
        return 'Ready to resume'
    return 'Needs preparation'


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        'job_id': str(entry.get('job_id') or ''),
        'title': str(entry.get('title') or 'Untitled'),
        'job_root': str(entry.get('job_root') or ''),
        'export_root': str(entry.get('export_root') or ''),
        'source_sha256': str(entry.get('source_sha256') or ''),
        'created_utc': str(entry.get('created_utc') or ''),
        'updated_utc': str(entry.get('updated_utc') or _utc_now()),
        'last_operation': entry.get('last_operation'),
        'last_step': entry.get('last_step'),
        'current_part': entry.get('current_part'),
        'total_parts': int(entry.get('total_parts') or 0),
        'completed_parts': int(entry.get('completed_parts') or 0),
        'failed_parts': int(entry.get('failed_parts') or 0),
        'status': str(entry.get('status') or 'idle'),
        'interrupted': bool(entry.get('interrupted', False)),
        'resumable': bool(entry.get('resumable', False)),
        'hidden': bool(entry.get('hidden', False)),
    }


def read_history(path: Path | None = None) -> dict[str, Any]:
    path = Path(path or execution_history_path())
    if not path.exists():
        return _empty_history()
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('history payload must be an object')
        jobs = payload.get('jobs', [])
        if not isinstance(jobs, list):
            raise ValueError('history jobs must be a list')
        return {
            'schema_version': HISTORY_SCHEMA_VERSION,
            'updated_utc': str(payload.get('updated_utc') or _utc_now()),
            'jobs': [_normalize_entry(item) for item in jobs if isinstance(item, dict)],
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return _empty_history()


def write_history(payload: dict[str, Any], path: Path | None = None) -> None:
    path = Path(path or execution_history_path())
    jobs = [_normalize_entry(item) for item in payload.get('jobs', []) if isinstance(item, dict)]
    jobs.sort(key=lambda item: item.get('updated_utc') or '', reverse=True)
    atomic_write_json(path, {'schema_version': HISTORY_SCHEMA_VERSION, 'updated_utc': _utc_now(), 'jobs': jobs[:MAX_RECENT_JOBS]})


def history_entry_from_manifest(job: JobPaths, manifest: dict[str, Any]) -> dict[str, Any]:
    audio = manifest.get('audio', {})
    execution = manifest.get('execution', {})
    parts = manifest.get('parts', [])
    status = str(execution.get('status') or 'idle')
    interrupted = status == 'interrupted' or bool(execution.get('resume_required', False))
    completed = len(audio.get('completed', {}))
    total = len(parts)
    return _normalize_entry({
        'job_id': manifest.get('job_id'),
        'title': manifest.get('title'),
        'job_root': str(job.root),
        'export_root': str(job.export),
        'source_sha256': str(manifest.get('source', {}).get('sha256') or ''),
        'created_utc': manifest.get('created_utc'),
        'updated_utc': manifest.get('updated_utc') or _utc_now(),
        'last_operation': execution.get('last_operation'),
        'last_step': execution.get('last_step'),
        'current_part': execution.get('current_part'),
        'total_parts': total,
        'completed_parts': completed,
        'failed_parts': len(audio.get('failures', {})),
        'status': status,
        'interrupted': interrupted,
        'resumable': bool(total and completed < total) or interrupted or bool(audio.get('failures')),
    })


def sync_job_history(job: JobPaths, manifest: dict[str, Any], path: Path | None = None) -> None:
    path = Path(path or execution_history_path())
    payload = read_history(path)
    entry = history_entry_from_manifest(job, manifest)
    existing = {item.get('job_id'): item for item in payload['jobs']}
    previous = existing.get(entry['job_id'])
    if previous and previous.get('hidden'):
        entry['hidden'] = True
    existing[entry['job_id']] = entry
    payload['jobs'] = list(existing.values())
    write_history(payload, path)


def prune_invalid_history(path: Path | None = None) -> dict[str, Any]:
    path = Path(path or execution_history_path())
    payload = read_history(path)
    jobs = payload.get('jobs', [])
    valid = [item for item in jobs if _entry_is_valid(item)]
    removed = len(jobs) - len(valid)
    if removed:
        payload['jobs'] = valid
        write_history(payload, path)
    return {'removed': removed, 'remaining': len(valid)}


def list_recent_jobs(path: Path | None = None, *, include_hidden: bool = False) -> list[dict[str, Any]]:
    path = Path(path or execution_history_path())
    payload = read_history(path)
    valid = [item for item in payload.get('jobs', []) if _entry_is_valid(item)]
    if len(valid) != len(payload.get('jobs', [])):
        payload['jobs'] = valid
        write_history(payload, path)
    jobs = valid
    if not include_hidden:
        jobs = [item for item in jobs if not item.get('hidden')]
    return sorted(jobs, key=lambda item: item.get('updated_utc') or '', reverse=True)


def list_resumable_jobs(path: Path | None = None, *, include_older_attempts: bool = False) -> list[dict[str, Any]]:
    candidates = [
        item for item in list_recent_jobs(path)
        if item.get('resumable') or item.get('interrupted') or int(item.get('failed_parts') or 0)
    ]
    if include_older_attempts:
        return candidates
    newest: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for item in candidates:
        source_sha256 = str(item.get('source_sha256') or '').strip()
        key = f'sha256:{source_sha256}' if source_sha256 else f'job:{item.get("job_id")}'
        if key in seen_sources:
            continue
        seen_sources.add(key)
        newest.append(item)
    return newest


def remove_from_history(job_id: str, path: Path | None = None) -> None:
    path = Path(path or execution_history_path())
    payload = read_history(path)
    for item in payload['jobs']:
        if item.get('job_id') == job_id:
            item['hidden'] = True
    write_history(payload, path)


def rebuild_history(work_root: Path | None = None, path: Path | None = None) -> dict[str, Any]:
    work_root = Path(work_root or local_work_root())
    path = Path(path or execution_history_path())
    existing = {item.get('job_id'): item for item in read_history(path).get('jobs', []) if _entry_is_valid(item)}
    rebuilt: list[dict[str, Any]] = []
    if work_root.exists():
        for manifest_path in work_root.glob('*/_work/job_manifest.json'):
            try:
                payload = json.loads(manifest_path.read_text(encoding='utf-8'))
                job = JobPaths.from_root(manifest_path.parent.parent)
                entry = history_entry_from_manifest(job, payload)
                previous = existing.get(entry['job_id'])
                if previous and previous.get('hidden'):
                    entry['hidden'] = True
                rebuilt.append(entry)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
    merged = dict(existing)
    for entry in rebuilt:
        merged[entry['job_id']] = entry
    result = {'schema_version': HISTORY_SCHEMA_VERSION, 'jobs': list(merged.values())}
    write_history(result, path)
    return read_history(path)
