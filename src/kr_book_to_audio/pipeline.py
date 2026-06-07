from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json
import shutil
from .config import DEFAULT_CHUNK_CJK, default_export_root, local_work_root
from .extractors import book_title, diagnose, extract
from .manifest import load_manifest, new_manifest, save_manifest
from .models import JobPaths
from .text_processing import apply_dictionary, chunk_text, clean_text, load_dictionary, strip_repeated_junk, text_units
from .utils import atomic_write_json, atomic_write_text, clear_files, sanitize_filename, sha256_file, sha256_text


def _log(job: JobPaths, line: str) -> None:
    job.run_log.parent.mkdir(parents=True, exist_ok=True)
    with job.run_log.open('a', encoding='utf-8') as handle:
        handle.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")


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
    _log(job, f'job-created title={title}')
    return job


def _convert_opencc(text: str, config: str) -> str:
    try:
        from opencc import OpenCC
    except ImportError as exc:
        raise RuntimeError('OpenCC is required for Traditional-to-Simplified conversion: pip install opencc') from exc
    return OpenCC(config).convert(text)


def prepare_job(
    source: Path,
    *,
    work_root: Path | None = None,
    export_root: Path | None = None,
    title: str | None = None,
    strip_dates: bool = False,
    convert_config: str | None = None,
    dictionary_path: Path | None = None,
    chunk_chars: int = DEFAULT_CHUNK_CJK,
) -> JobPaths:
    source = Path(source).resolve()
    diagnosis = diagnose(source)
    if not diagnosis.get('extractable'):
        reason = diagnosis.get('reason') or 'Input is not extractable. OCR is required first.'
        raise RuntimeError(reason)
    options = {'strip_dates': strip_dates, 'convert_config': convert_config, 'chunk_chars': chunk_chars}
    job = create_job(source, work_root=work_root, export_root=export_root, title=title, options=options)
    raw = extract(source)
    atomic_write_text(job.extracted, raw)
    cleaned, stats = clean_text(raw, strip_dates=strip_dates)
    if convert_config:
        cleaned = _convert_opencc(cleaned, convert_config)
    atomic_write_text(job.cleaned, cleaned)
    atomic_write_text(job.proofread, cleaned)
    manifest = load_manifest(job)
    manifest['diagnosis'] = diagnosis
    manifest['text']['clean_stats'] = stats
    manifest['text']['proofread_sha256'] = sha256_text(cleaned)
    save_manifest(job, manifest)
    rebuild_parts(job, dictionary_path=dictionary_path, chunk_chars=chunk_chars)
    _log(job, f'prepared cjk_chars={stats["cjk_chars"]}')
    return job


def strip_junk_and_rebuild(job: JobPaths, *, min_repeats: int = 3, dictionary_path: Path | None = None) -> dict:
    manifest = load_manifest(job)
    baseline = job.proofread.read_text(encoding='utf-8')
    cleaned, report = strip_repeated_junk(baseline, min_repeats=min_repeats)
    backup = job.work / 'proofread_prejunk.txt'
    if not backup.exists():
        shutil.copyfile(job.proofread, backup)
    atomic_write_text(job.proofread, cleaned)
    rebuild_parts(job, dictionary_path=dictionary_path, chunk_chars=int(manifest['options']['chunk_chars']))
    atomic_write_json(job.work / 'junk_report.json', report)
    _log(job, f'junk-stripped removed={len(report["removed"])}')
    return report


def rebuild_parts(job: JobPaths, *, dictionary_path: Path | None = None, chunk_chars: int | None = None) -> dict:
    job.ensure()
    manifest = load_manifest(job)
    proofread = job.proofread.read_text(encoding='utf-8')
    entries = load_dictionary(dictionary_path)
    rendered, preview = apply_dictionary(proofread, entries)
    atomic_write_text(job.tts_text, rendered)
    atomic_write_json(job.pronunciation_preview, {'entries': preview})
    chunk_chars = int(chunk_chars or manifest['options'].get('chunk_chars', DEFAULT_CHUNK_CJK))
    parts = chunk_text(rendered, max_cjk=chunk_chars)
    new_records = [{'index': index, 'file': f'part-{index:04d}.txt', 'sha256': sha256_text(text)} for index, text in enumerate(parts, 1)]
    old_records = manifest.get('parts', [])
    old_signature = [(x.get('index'), x.get('sha256')) for x in old_records]
    new_signature = [(x.get('index'), x.get('sha256')) for x in new_records]
    clear_files(job.parts_text, 'part-*.txt')
    for record, text in zip(new_records, parts):
        atomic_write_text(job.parts_text / record['file'], text)
    if old_signature != new_signature:
        clear_files(job.parts_audio, 'part-*.mp3')
        clear_files(job.parts_audio, 'part-*.mp3.partial')
        manifest['audio'] = {'signature': None, 'completed': {}}
    manifest['parts'] = new_records
    manifest['options']['chunk_chars'] = chunk_chars
    manifest['text']['proofread_sha256'] = sha256_text(proofread)
    manifest['text']['tts_text_sha256'] = sha256_text(rendered)
    manifest['text']['dictionary_sha256'] = sha256_text(json.dumps(entries, ensure_ascii=False, sort_keys=True))
    save_manifest(job, manifest)
    _log(job, f'rebuilt-parts count={len(parts)}')
    return {'parts': len(parts), 'pronunciation_preview': preview}


def job_status(job: JobPaths) -> dict:
    manifest = load_manifest(job)
    completed = manifest.get('audio', {}).get('completed', {})
    return {
        'job_root': str(job.root),
        'title': manifest['title'],
        'parts': len(manifest.get('parts', [])),
        'completed_audio_parts': len(completed),
        'proofread_path': str(job.proofread),
        'export_dir': str(job.export),
        'estimated_hours': round(text_units(job.tts_text.read_text(encoding='utf-8')) / 4.6 / 3600, 2) if job.tts_text.exists() else 0.0,
    }
