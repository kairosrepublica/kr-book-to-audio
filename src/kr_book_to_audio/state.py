from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
from .manifest import ensure_manifest_defaults
from .models import JobPaths
from .text_processing import load_dictionary
from .utils import append_job_log, clear_files, sha256_text


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dictionary_digest(entries: list[dict]) -> str:
    return sha256_text(json.dumps(entries, ensure_ascii=False, sort_keys=True))


def load_required_dictionary(path: Path | None) -> list[dict]:
    if path is None:
        return []
    candidate = Path(path)
    if not candidate.exists():
        raise RuntimeError(f'Pronunciation dictionary not found: {candidate}')
    return load_dictionary(candidate)


def stored_dictionary_path(manifest: dict) -> Path | None:
    value = manifest.get('text', {}).get('dictionary_path_runtime_only')
    return Path(value) if value else None


def current_dictionary_entries(manifest: dict) -> list[dict]:
    return load_required_dictionary(stored_dictionary_path(manifest))


def reset_preview_gate(manifest: dict) -> None:
    preview = ensure_manifest_defaults(manifest)['gates']['preview']
    preview.update({'approved_audio_signature': None, 'approved_part_sha256': None, 'approved_utc': None})


def reset_audio_state(job: JobPaths, manifest: dict, *, reason: str, signature: str | None = None) -> None:
    clear_files(job.parts_audio, 'part-*.mp3')
    clear_files(job.parts_audio, 'part-*.partial.mp3')
    clear_files(job.parts_audio, 'part-*.meta.json')
    manifest['audio'] = {'signature': signature, 'completed': {}, 'failures': {}}
    reset_preview_gate(manifest)
    append_job_log(job, 'audio-invalidated', reason=reason, signature=signature)


def assert_text_state_fresh(job: JobPaths, manifest: dict) -> None:
    ensure_manifest_defaults(manifest)
    if not job.proofread.exists() or not job.tts_text.exists():
        raise RuntimeError('Text preparation is incomplete. Approve proofreading and rebuild parts first.')
    proofread_sha = sha256_text(job.proofread.read_text(encoding='utf-8'))
    if manifest['text'].get('proofread_sha256') != proofread_sha:
        raise RuntimeError('proofread.txt changed after the last rebuild. Approve proofreading and rebuild parts again.')
    entries = current_dictionary_entries(manifest)
    if manifest['text'].get('dictionary_sha256') != dictionary_digest(entries):
        raise RuntimeError('Pronunciation dictionary changed after the last rebuild. Approve proofreading and rebuild parts again.')
    rendered_sha = sha256_text(job.tts_text.read_text(encoding='utf-8'))
    if manifest['text'].get('tts_text_sha256') != rendered_sha:
        raise RuntimeError('tts_text.txt no longer matches the manifest. Approve proofreading and rebuild parts again.')
    records = manifest.get('parts', [])
    if not records:
        raise RuntimeError('No text parts exist. Approve proofreading and rebuild parts first.')
    for record in records:
        path = job.parts_text / record['file']
        if not path.exists() or sha256_text(path.read_text(encoding='utf-8')) != record.get('sha256'):
            raise RuntimeError(f'Text part is missing or stale: {record["file"]}')


def assert_proofread_approved(job: JobPaths, manifest: dict) -> None:
    assert_text_state_fresh(job, manifest)
    actual = sha256_text(job.proofread.read_text(encoding='utf-8'))
    if manifest['gates']['proofread'].get('approved_sha256') != actual:
        raise RuntimeError('Proofreading has not been approved for the current text. Run Approve proofread & rebuild first.')


def approve_proofread_state(job: JobPaths, manifest: dict) -> dict:
    actual = sha256_text(job.proofread.read_text(encoding='utf-8'))
    manifest['gates']['proofread'] = {'approved_sha256': actual, 'approved_utc': _utc_now()}
    append_job_log(job, 'proofread-approved', proofread_sha256=actual)
    return manifest['gates']['proofread']


def assert_preview_approved(manifest: dict, *, signature: str) -> None:
    ensure_manifest_defaults(manifest)
    if not manifest.get('parts'):
        raise RuntimeError('No text parts exist.')
    preview = manifest['gates']['preview']
    first_sha = manifest['parts'][0]['sha256']
    if preview.get('approved_audio_signature') != signature or preview.get('approved_part_sha256') != first_sha:
        raise RuntimeError('Part 1 preview has not been approved for the current text, voice and speaking rate.')


def approve_preview_state(job: JobPaths, manifest: dict, *, signature: str) -> dict:
    first_sha = manifest['parts'][0]['sha256']
    manifest['gates']['preview'] = {
        'approved_audio_signature': signature,
        'approved_part_sha256': first_sha,
        'approved_utc': _utc_now(),
    }
    append_job_log(job, 'preview-approved', signature=signature, part_sha256=first_sha)
    return manifest['gates']['preview']
