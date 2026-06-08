from __future__ import annotations
from datetime import datetime
from pathlib import Path
import shutil
from .config import DEFAULT_CHUNK_CJK, default_export_root, local_work_root
from .extractors import book_title, diagnose, extract
from .manifest import load_manifest, new_manifest, save_manifest
from .models import JobPaths
from .state import approve_proofread_state, dictionary_digest, load_required_dictionary, reset_audio_state, reset_preview_gate
from .text_processing import analyze_cleanup, apply_cleanup, apply_dictionary, chunk_text, clean_text, text_units
from .utils import append_job_log, atomic_write_json, atomic_write_text, clear_files, job_operation_lock, sanitize_filename, sha256_file, sha256_text


def create_job(source: Path, *, work_root: Path | None = None, export_root: Path | None = None, title: str | None = None, options: dict | None = None) -> JobPaths:
    source = Path(source).resolve()
    work_root = Path(work_root or local_work_root())
    export_root = Path(export_root or default_export_root())
    title = sanitize_filename(title or book_title(source))
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    job = JobPaths.from_root(work_root / f'{stamp}_{title}', export_root / f'{stamp}_{title}')
    job.ensure()
    manifest = new_manifest(source=source, source_sha256=sha256_file(source), title=title, options=options or {})
    manifest['source']['path_runtime_only'] = str(source)
    manifest['paths'] = {'export_runtime_only': str(job.export)}
    save_manifest(job, manifest)
    append_job_log(job, 'job-created', title=title)
    return job


def prepare_job(
    source: Path,
    *,
    work_root: Path | None = None,
    export_root: Path | None = None,
    title: str | None = None,
    processing_profile: str = 'auto',
    dictionary_path: Path | None = None,
    chunk_chars: int = DEFAULT_CHUNK_CJK,
) -> JobPaths:
    source = Path(source).resolve()
    diagnosis = diagnose(source)
    if not diagnosis.get('extractable'):
        reason = diagnosis.get('reason') or 'Input is not extractable. OCR is required first.'
        raise RuntimeError(reason)
    options = {'processing_profile': processing_profile, 'chunk_chars': chunk_chars}
    job = create_job(source, work_root=work_root, export_root=export_root, title=title, options=options)
    raw = extract(source)
    atomic_write_text(job.extracted, raw)
    cleaned, stats = clean_text(raw, processing_profile=processing_profile)
    atomic_write_text(job.cleaned, cleaned)
    atomic_write_text(job.proofread, cleaned)
    manifest = load_manifest(job)
    manifest['diagnosis'] = diagnosis
    manifest['text']['clean_stats'] = stats
    manifest['text']['processing_profile'] = stats.get('language_mode')
    manifest['cleanup']['analysis'] = analyze_cleanup(cleaned)
    save_manifest(job, manifest)
    rebuild_parts(job, dictionary_path=dictionary_path, chunk_chars=chunk_chars)
    append_job_log(job, 'prepared', cjk_chars=stats['cjk_chars'], language_mode=stats['language_mode'])
    return job


def _rebuild_parts_unlocked(job: JobPaths, *, dictionary_path: Path | None = None, chunk_chars: int | None = None) -> dict:
    job.ensure()
    manifest = load_manifest(job)
    proofread = job.proofread.read_text(encoding='utf-8')
    entries = load_required_dictionary(dictionary_path)
    rendered, preview = apply_dictionary(proofread, entries)
    atomic_write_text(job.tts_text, rendered)
    atomic_write_json(job.pronunciation_preview, {'entries': preview})
    chunk_chars = int(chunk_chars or manifest['options'].get('chunk_chars', DEFAULT_CHUNK_CJK))
    parts = chunk_text(rendered, max_cjk=chunk_chars)
    if not parts:
        raise RuntimeError('No listenable prose remained after cleanup. Review the source and cleaning mode.')
    new_records = [{'index': index, 'file': f'part-{index:04d}.txt', 'sha256': sha256_text(text)} for index, text in enumerate(parts, 1)]
    old_records = manifest.get('parts', [])
    old_signature = [(item.get('index'), item.get('sha256')) for item in old_records]
    new_signature = [(item.get('index'), item.get('sha256')) for item in new_records]
    new_proofread_sha = sha256_text(proofread)
    new_rendered_sha = sha256_text(rendered)
    new_dictionary_sha = dictionary_digest(entries)
    text_changed = (
        old_signature != new_signature
        or manifest['text'].get('proofread_sha256') != new_proofread_sha
        or manifest['text'].get('tts_text_sha256') != new_rendered_sha
        or manifest['text'].get('dictionary_sha256') != new_dictionary_sha
    )
    clear_files(job.parts_text, 'part-*.txt')
    for record, text in zip(new_records, parts):
        atomic_write_text(job.parts_text / record['file'], text)
    if text_changed:
        reset_audio_state(job, manifest, reason='text-or-dictionary-rebuilt')
    if manifest['gates']['proofread'].get('approved_sha256') != new_proofread_sha:
        manifest['gates']['proofread'] = {'approved_sha256': None, 'approved_utc': None}
    if text_changed:
        reset_preview_gate(manifest)
    manifest['parts'] = new_records
    manifest['options']['chunk_chars'] = chunk_chars
    manifest['text']['proofread_sha256'] = new_proofread_sha
    manifest['text']['tts_text_sha256'] = new_rendered_sha
    manifest['text']['dictionary_sha256'] = new_dictionary_sha
    manifest['text']['dictionary_path_runtime_only'] = str(Path(dictionary_path).resolve()) if dictionary_path else None
    save_manifest(job, manifest)
    append_job_log(job, 'parts-rebuilt', count=len(parts), dictionary_entries=len(entries), text_changed=text_changed)
    return {'parts': len(parts), 'pronunciation_preview': preview, 'text_changed': text_changed}


def rebuild_parts(job: JobPaths, *, dictionary_path: Path | None = None, chunk_chars: int | None = None) -> dict:
    with job_operation_lock(job, 'rebuild-parts'):
        return _rebuild_parts_unlocked(job, dictionary_path=dictionary_path, chunk_chars=chunk_chars)


def approve_proofread_and_rebuild(job: JobPaths, *, dictionary_path: Path | None = None, chunk_chars: int | None = None) -> dict:
    with job_operation_lock(job, 'approve-proofread-and-rebuild'):
        report = _rebuild_parts_unlocked(job, dictionary_path=dictionary_path, chunk_chars=chunk_chars)
        manifest = load_manifest(job)
        approval = approve_proofread_state(job, manifest)
        save_manifest(job, manifest)
        return {'approval': approval, **report}


def apply_cleanup_and_rebuild(job: JobPaths, *, kind: str, dictionary_path: Path | None = None) -> dict:
    with job_operation_lock(job, f'cleanup-{kind}'):
        manifest = load_manifest(job)
        baseline = job.proofread.read_text(encoding='utf-8')
        cleaned, report = apply_cleanup(baseline, kind)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = job.work / f'proofread_precleanup_{stamp}.txt'
        shutil.copyfile(job.proofread, backup)
        atomic_write_text(job.proofread, cleaned)
        _rebuild_parts_unlocked(job, dictionary_path=dictionary_path, chunk_chars=int(manifest['options']['chunk_chars']))
        manifest = load_manifest(job)
        manifest['cleanup']['analysis'] = analyze_cleanup(cleaned)
        manifest['cleanup'].setdefault('history', []).append({'kind': kind, 'backup': str(backup), 'report': report})
        save_manifest(job, manifest)
        append_job_log(job, 'cleanup-applied', kind=kind, backup=str(backup), report=report)
        return {'kind': kind, 'backup': str(backup), 'report': report, 'analysis': manifest['cleanup']['analysis']}


def strip_junk_and_rebuild(job: JobPaths, *, min_repeats: int = 3, dictionary_path: Path | None = None) -> dict:
    return apply_cleanup_and_rebuild(job, kind='repeated-headers-and-junk', dictionary_path=dictionary_path)


def strip_datetime_and_rebuild(job: JobPaths, *, dictionary_path: Path | None = None) -> dict:
    return apply_cleanup_and_rebuild(job, kind='metadata-date-time-tags', dictionary_path=dictionary_path)

def job_status(job: JobPaths) -> dict:
    manifest = load_manifest(job)
    completed = manifest.get('audio', {}).get('completed', {})
    failures = manifest.get('audio', {}).get('failures', {})
    actual_proofread_sha = sha256_text(job.proofread.read_text(encoding='utf-8')) if job.proofread.exists() else None
    proofread_approved = manifest['gates']['proofread'].get('approved_sha256') == actual_proofread_sha and actual_proofread_sha is not None
    preview = manifest['gates']['preview']
    first_sha = manifest.get('parts', [{}])[0].get('sha256') if manifest.get('parts') else None
    preview_approved = bool(
        preview.get('approved_audio_signature')
        and preview.get('approved_audio_signature') == manifest.get('audio', {}).get('signature')
        and preview.get('approved_part_sha256') == first_sha
    )
    return {
        'job_root': str(job.root),
        'title': manifest['title'],
        'parts': len(manifest.get('parts', [])),
        'completed_audio_parts': len(completed),
        'failed_audio_parts': sorted(int(index) for index in failures),
        'proofread_approved': proofread_approved,
        'preview_approved': preview_approved,
        'proofread_path': str(job.proofread),
        'export_dir': str(job.export),
        'export': manifest.get('export', {'status': 'not-finalized'}),
        'estimated_hours': round(text_units(job.tts_text.read_text(encoding='utf-8')) / 4.6 / 3600, 2) if job.tts_text.exists() else 0.0,
        'cleanup_analysis': manifest.get('cleanup', {}).get('analysis', {}),
        'processing_profile': manifest.get('text', {}).get('processing_profile', manifest.get('options', {}).get('processing_profile', 'auto')),
        'execution': manifest.get('execution', {}),
        'resumable': bool(len(completed) < len(manifest.get('parts', [])) or failures or manifest.get('execution', {}).get('resume_required')),
    }
