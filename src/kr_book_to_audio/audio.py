from __future__ import annotations
from pathlib import Path
from typing import Callable
import asyncio
import os
import subprocess
import tempfile
import time
from .manifest import load_manifest, save_manifest
from .models import JobPaths
from .state import approve_preview_state, assert_preview_approved, assert_proofread_approved, reset_audio_state
from .utils import append_job_log, job_operation_lock, require_command, sha256_file, sha256_text

ProgressCallback = Callable[[dict], None]


def audio_signature(*, voice: str, rate: str, pitch: str = '+0Hz', volume: str = '+0%') -> str:
    return sha256_text('|'.join([voice, rate, pitch, volume]))


def expected_audio_paths(job: JobPaths, manifest: dict) -> list[Path]:
    return [job.parts_audio / f"part-{int(item['index']):04d}.mp3" for item in manifest['parts']]


def validate_mp3(path: Path, *, ffprobe: str = 'ffprobe') -> dict:
    if not path.exists() or path.stat().st_size <= 1024:
        raise RuntimeError(f'MP3 missing or too small: {path.name}')
    require_command(ffprobe, 'install FFmpeg')
    result = subprocess.run(
        [ffprobe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f'ffprobe rejected {path.name}: {result.stderr.strip()}')
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f'ffprobe duration missing for {path.name}') from exc
    if duration <= 0:
        raise RuntimeError(f'Invalid MP3 duration for {path.name}')
    return {'bytes': path.stat().st_size, 'duration_seconds': duration, 'sha256': sha256_file(path)}


def audition_sample(*, voice: str, rate: str = '+0%', pitch: str = '+0Hz', volume: str = '+0%', output_dir: Path | None = None, validator: Callable[[Path], dict] = validate_mp3) -> Path:
    output_dir = Path(output_dir or tempfile.gettempdir())
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_voice = ''.join(char for char in voice if char.isalnum() or char in '-_')
    final = output_dir / f'audition-{safe_voice}.mp3'
    partial = output_dir / f'audition-{safe_voice}.partial.mp3'
    partial.unlink(missing_ok=True)
    sample = '这是语音试听。价值投资的核心，是以合理的价格买入优秀的公司，并长期持有。'
    asyncio.run(_edge_save(sample, partial, voice=voice, rate=rate, pitch=pitch, volume=volume))
    validator(partial)
    os.replace(partial, final)
    return final


async def _edge_save(text: str, out_path: Path, *, voice: str, rate: str, pitch: str, volume: str) -> None:
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume).save(str(out_path))


def _emit(progress: ProgressCallback | None, **payload: object) -> None:
    if progress:
        progress(payload)


def _invalidate_for_signature(job: JobPaths, manifest: dict, signature: str) -> None:
    if manifest.get('audio', {}).get('signature') == signature:
        return
    reset_audio_state(job, manifest, reason='voice-or-speaking-controls-changed', signature=signature)


def _synthesize_parts_unlocked(
    job: JobPaths,
    *,
    voice: str,
    rate: str = '+0%',
    pitch: str = '+0Hz',
    volume: str = '+0%',
    start: int = 1,
    end: int | None = None,
    indexes: set[int] | None = None,
    retries: int = 3,
    gap_seconds: float = 2.0,
    require_preview_approval: bool = True,
    save_func: Callable[..., object] | None = None,
    validator: Callable[[Path], dict] = validate_mp3,
    progress: ProgressCallback | None = None,
) -> dict:
    manifest = load_manifest(job)
    assert_proofread_approved(job, manifest)
    signature = audio_signature(voice=voice, rate=rate, pitch=pitch, volume=volume)
    if require_preview_approval:
        assert_preview_approved(manifest, signature=signature)
    _invalidate_for_signature(job, manifest, signature)
    completed = manifest['audio']['completed']
    failures = manifest['audio']['failures']
    parts = manifest['parts']
    end = end or int(parts[-1]['index'])
    save_func = save_func or _edge_save
    selected = [item for item in parts if start <= int(item['index']) <= end and (indexes is None or int(item['index']) in indexes)]
    if not selected:
        raise RuntimeError('No matching text parts were selected for synthesis.')
    append_job_log(job, 'synthesis-started', selected=[int(item['index']) for item in selected], signature=signature)
    for item in selected:
        _emit(progress, index=int(item['index']), state='queued')
    run_failures: list[dict] = []
    for item in selected:
        index = int(item['index'])
        text_path = job.parts_text / item['file']
        audio_path = job.parts_audio / f'part-{index:04d}.mp3'
        partial = audio_path.with_name(audio_path.stem + '.partial.mp3')
        if audio_path.exists():
            try:
                metadata = validator(audio_path)
                saved = completed.get(str(index), {})
                if saved.get('text_sha256') == item['sha256'] and saved.get('signature') == signature and saved.get('sha256') == metadata.get('sha256'):
                    completed[str(index)] = {'text_sha256': item['sha256'], 'signature': signature, **metadata}
                    failures.pop(str(index), None)
                    save_manifest(job, manifest)
                    _emit(progress, index=index, state='done', reused=True)
                    append_job_log(job, 'part-reused', index=index)
                    continue
            except RuntimeError:
                pass
            audio_path.unlink(missing_ok=True)
        completed.pop(str(index), None)
        save_manifest(job, manifest)
        ok = False
        last_error = None
        for attempt in range(1, retries + 2):
            partial.unlink(missing_ok=True)
            state = 'running' if attempt == 1 else 'retrying'
            _emit(progress, index=index, state=state, attempt=attempt)
            append_job_log(job, f'part-{state}', index=index, attempt=attempt)
            try:
                maybe = save_func(text_path.read_text(encoding='utf-8'), partial, voice=voice, rate=rate, pitch=pitch, volume=volume)
                if asyncio.iscoroutine(maybe):
                    asyncio.run(maybe)
                metadata = validator(partial)
                os.replace(partial, audio_path)
                completed[str(index)] = {'text_sha256': item['sha256'], 'signature': signature, **metadata}
                failures.pop(str(index), None)
                save_manifest(job, manifest)
                ok = True
                _emit(progress, index=index, state='done', reused=False)
                append_job_log(job, 'part-completed', index=index, duration_seconds=metadata.get('duration_seconds'))
                break
            except Exception as exc:
                last_error = f'{type(exc).__name__}: {exc}'
                partial.unlink(missing_ok=True)
                append_job_log(job, 'part-attempt-failed', index=index, attempt=attempt, error=last_error)
                if attempt <= retries:
                    time.sleep(min(45.0, 5.0 * (3 ** (attempt - 1))))
        if not ok:
            failures[str(index)] = {'error': last_error, 'text_sha256': item['sha256'], 'signature': signature}
            run_failures.append({'index': index, 'error': last_error})
            save_manifest(job, manifest)
            _emit(progress, index=index, state='failed', error=last_error)
            append_job_log(job, 'part-failed', index=index, error=last_error)
        if gap_seconds:
            time.sleep(gap_seconds)
    save_manifest(job, manifest)
    append_job_log(job, 'synthesis-finished', failures=len(run_failures), completed=len(completed))
    return {'failures': run_failures, 'completed': sorted(int(index) for index in completed)}


def synthesize_parts(job: JobPaths, **kwargs: object) -> dict:
    with job_operation_lock(job, 'synthesize-parts'):
        return _synthesize_parts_unlocked(job, **kwargs)


def retry_failed_parts(job: JobPaths, **kwargs: object) -> dict:
    with job_operation_lock(job, 'retry-failed-parts'):
        manifest = load_manifest(job)
        indexes = {int(index) for index in manifest['audio'].get('failures', {})}
        if not indexes:
            raise RuntimeError('No failed audio parts are recorded for retry.')
        return _synthesize_parts_unlocked(job, indexes=indexes, **kwargs)


def approve_preview(job: JobPaths, *, voice: str, rate: str = '+0%', pitch: str = '+0Hz', volume: str = '+0%', validator: Callable[[Path], dict] = validate_mp3) -> dict:
    with job_operation_lock(job, 'approve-preview'):
        manifest = load_manifest(job)
        assert_proofread_approved(job, manifest)
        signature = audio_signature(voice=voice, rate=rate, pitch=pitch, volume=volume)
        if manifest['audio'].get('signature') != signature:
            raise RuntimeError('Part 1 must be generated with the currently selected voice and speaking rate before approval.')
        first = manifest['parts'][0]
        saved = manifest['audio']['completed'].get('1')
        if not saved or saved.get('text_sha256') != first['sha256'] or saved.get('signature') != signature:
            raise RuntimeError('Part 1 has not been generated for the current text and voice settings.')
        metadata = validator(job.parts_audio / 'part-0001.mp3')
        if metadata.get('sha256') != saved.get('sha256'):
            raise RuntimeError('Part 1 audio changed after synthesis. Generate the preview again.')
        approval = approve_preview_state(job, manifest, signature=signature)
        save_manifest(job, manifest)
        return approval


def merge_parts(job: JobPaths, *, output_name: str | None = None, validator: Callable[[Path], dict] = validate_mp3) -> Path:
    with job_operation_lock(job, 'merge-parts'):
        manifest = load_manifest(job)
        assert_proofread_approved(job, manifest)
        signature = manifest['audio'].get('signature')
        if not signature:
            raise RuntimeError('No approved audio configuration exists.')
        assert_preview_approved(manifest, signature=signature)
        expected = expected_audio_paths(job, manifest)
        if not expected:
            raise RuntimeError('No manifest-declared audio parts exist.')
        append_job_log(job, 'merge-started', parts=len(expected), signature=signature)
        for item, path in zip(manifest['parts'], expected):
            index = str(int(item['index']))
            saved = manifest['audio']['completed'].get(index)
            if not saved or saved.get('text_sha256') != item['sha256'] or saved.get('signature') != signature:
                raise RuntimeError(f'Audio completion record is missing or stale: {path.name}')
            metadata = validator(path)
            if metadata.get('sha256') != saved.get('sha256'):
                raise RuntimeError(f'Audio file changed after validation: {path.name}')
        ffmpeg = require_command('ffmpeg', 'install FFmpeg')
        concat_list = job.work / 'concat.txt'
        concat_list.write_text(''.join(f"file '{path.resolve().as_posix()}'\n" for path in expected), encoding='utf-8', newline='\n')
        output = job.export / (output_name or f"{manifest['title']}.mp3")
        output.parent.mkdir(parents=True, exist_ok=True)
        partial = output.with_name(output.stem + '.partial' + output.suffix)
        partial.unlink(missing_ok=True)
        try:
            subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(concat_list), '-c', 'copy', str(partial)], check=True)
            merged_metadata = validate_mp3(partial)
            os.replace(partial, output)
        except Exception as exc:
            partial.unlink(missing_ok=True)
            append_job_log(job, 'merge-failed', error=f'{type(exc).__name__}: {exc}')
            raise
        manifest['merge'] = {'output_runtime_only': str(output), 'signature': signature, **merged_metadata}
        save_manifest(job, manifest)
        append_job_log(job, 'merge-completed', output=str(output), duration_seconds=merged_metadata.get('duration_seconds'))
        return output
