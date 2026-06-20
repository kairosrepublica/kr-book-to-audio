from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import tempfile
from .models import JobPaths
from .job_state import initialize as initialize_job_state, load as load_job_state, save as save_job_state, state_exists

SCHEMA_VERSION = 4


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_manifest_defaults(payload: dict) -> dict:
    """Upgrade additive fields while retiring obsolete text-conversion flags."""
    if payload.get('schema_version') in {1, 2, 3}:
        old_schema = payload.get('schema_version')
        payload['schema_version'] = SCHEMA_VERSION
        payload.setdefault('migration', {}).setdefault('upgraded_from_schema', old_schema)
    payload.setdefault('schema_version', SCHEMA_VERSION)
    if not payload.get('job_id'):
        import uuid
        payload['job_id'] = uuid.uuid4().hex
    payload.setdefault('paths', {})
    text = payload.setdefault('text', {})
    payload.setdefault('parts', [])
    options = payload.setdefault('options', {})
    ignored: list[str] = []
    for key in ('strip_dates', 'strip_datetime_tags', 'convert_config', 't2s'):
        if key in options:
            options.pop(key, None)
            ignored.append(key)
    if ignored:
        migration = payload.setdefault('migration', {})
        existing = set(migration.get('ignored_legacy_options', []))
        migration['ignored_legacy_options'] = sorted(existing | set(ignored))
    options.setdefault('processing_profile', 'auto')
    options.setdefault('chunk_chars', 9000)
    options.setdefault('layout_mode', 'auto')
    audio = payload.setdefault('audio', {})
    audio.setdefault('provider_id', 'edge-tts')
    audio.setdefault('signature', None)
    audio.setdefault('controls', None)
    audio.setdefault('completed', {})
    audio.setdefault('failures', {})
    gates = payload.setdefault('gates', {})
    proofread = gates.setdefault('proofread', {})
    proofread.setdefault('approved_sha256', None)
    proofread.setdefault('approved_utc', None)
    preview = gates.setdefault('preview', {})
    preview.setdefault('approved_audio_signature', None)
    preview.setdefault('approved_part_sha256', None)
    preview.setdefault('approved_utc', None)
    payload.setdefault('merge', {})
    payload.setdefault('export', {'status': 'not-finalized'})
    payload.setdefault('cleanup', {'analysis': {}, 'history': []})
    payload.setdefault('ocr', {'analysis': {}, 'history': []})
    execution = payload.setdefault('execution', {})
    execution.setdefault('status', 'idle')
    execution.setdefault('last_operation', None)
    execution.setdefault('last_step', None)
    execution.setdefault('current_part', None)
    execution.setdefault('current_part_state', None)
    execution.setdefault('last_completed_part', None)
    execution.setdefault('pid', None)
    execution.setdefault('operation_started_utc', None)
    execution.setdefault('heartbeat_utc', None)
    execution.setdefault('interrupted_detected_utc', None)
    execution.setdefault('resume_required', False)
    text.setdefault('processing_profile', options.get('processing_profile', 'auto'))
    return payload


def new_manifest(*, source: Path, source_sha256: str, title: str, options: dict) -> dict:
    import uuid
    return ensure_manifest_defaults({
        'schema_version': SCHEMA_VERSION,
        'job_id': uuid.uuid4().hex,
        'created_utc': _utc_now(),
        'updated_utc': _utc_now(),
        'source': {'name': source.name, 'sha256': source_sha256},
        'title': title,
        'options': options,
    })


def _read_legacy_snapshot(job: JobPaths) -> dict:
    if not job.manifest.exists():
        raise FileNotFoundError(f'Job manifest not found: {job.manifest}')
    payload = json.loads(job.manifest.read_text(encoding='utf-8'))
    if payload.get('schema_version') not in {None, 1, 2, 3, SCHEMA_VERSION}:
        raise RuntimeError('Unsupported job manifest schema version')
    return ensure_manifest_defaults(payload)


def load_manifest(job: JobPaths) -> dict:
    if state_exists(job):
        payload = load_job_state(job)
        return ensure_manifest_defaults(payload)
    payload = _read_legacy_snapshot(job)
    initialized = initialize_job_state(job, payload, preserve_legacy=True)
    return ensure_manifest_defaults(initialized)


def _history_sync_allowed(job: JobPaths) -> bool:
    override = os.environ.get('KR_B2A_HISTORY_SYNC')
    if override == '0':
        return False
    if override == '1':
        return True
    try:
        Path(job.root).resolve().relative_to(Path(tempfile.gettempdir()).resolve())
        return False
    except ValueError:
        return True


def save_manifest(job: JobPaths, manifest: dict) -> None:
    manifest = ensure_manifest_defaults(manifest)
    manifest['updated_utc'] = _utc_now()
    if not state_exists(job):
        initialize_job_state(job, manifest, preserve_legacy=True)
        # load the authoritative revision created by initialization.
        manifest['_state_revision'] = load_job_state(job).get('_state_revision', 0)
    save_job_state(job, manifest)
    if not _history_sync_allowed(job):
        return
    try:
        from .history import sync_job_history
        sync_job_history(job, manifest)
    except Exception:
        # The application-level history is a rebuildable index, never the job authority.
        pass
