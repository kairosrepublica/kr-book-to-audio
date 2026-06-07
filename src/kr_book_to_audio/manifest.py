from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
from .models import JobPaths
from .utils import atomic_write_json

SCHEMA_VERSION = 1


def new_manifest(*, source: Path, source_sha256: str, title: str, options: dict) -> dict:
    return {
        'schema_version': SCHEMA_VERSION,
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'updated_utc': datetime.now(timezone.utc).isoformat(),
        'source': {'name': source.name, 'sha256': source_sha256},
        'title': title,
        'options': options,
        'text': {},
        'parts': [],
        'audio': {'signature': None, 'completed': {}},
    }


def load_manifest(job: JobPaths) -> dict:
    if not job.manifest.exists():
        raise FileNotFoundError(f'Job manifest not found: {job.manifest}')
    payload = json.loads(job.manifest.read_text(encoding='utf-8'))
    if payload.get('schema_version') != SCHEMA_VERSION:
        raise RuntimeError('Unsupported job manifest schema version')
    return payload


def save_manifest(job: JobPaths, manifest: dict) -> None:
    manifest['updated_utc'] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(job.manifest, manifest)
