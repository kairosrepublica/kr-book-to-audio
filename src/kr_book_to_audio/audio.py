from __future__ import annotations
from pathlib import Path
from typing import Callable
import asyncio
import inspect
import os
import tempfile
import time
from .manifest import load_manifest, save_manifest
from .execution import begin_execution, checkpoint_execution, finish_execution
from .power import keep_computer_awake
from .providers import get_tts_provider
from .models import JobPaths
from .state import approve_preview_state, assert_preview_approved, assert_proofread_approved, reset_audio_state
from .subprocess_utils import run_hidden_cli
from .utils import append_job_log, atomic_write_json, clear_files, job_operation_lock, require_command, sha256_file, sha256_text
from .durable_io import cleanup_stale_partials, replace_with_retry, unique_partial_path

ProgressCallback = Callable[[dict], None]


def speech_controls(*, voice: str, rate: str = '+0%', pitch: str = '+0Hz', volume: str = '+0%', provider_id: str = 'edge-tts') -> dict[str, str]:
    return {
        'provider_id': str(provider_id),
        'voice': str(voice),
        'rate': str(rate),
        'pitch': str(pitch),
        'volume': str(volume),
    }


def audio_signature(*, voice: str, rate: str = '+0%', pitch: str = '+0Hz', volume: str = '+0%', provider_id: str = 'edge-tts') -> str:
    return sha256_text('|'.join([provider_id, voice, rate, pitch, volume]))


def controls_match_signature(controls: dict | None, signature: str | None) -> bool:
    if not isinstance(controls, dict) or not signature:
        return False
    required = ('provider_id', 'voice', 'rate', 'pitch', 'volume')
    if any(not isinstance(controls.get(key), str) for key in required):
        return False
    return audio_signature(**{key: controls[key] for key in required}) == signature


def recover_speech_controls(manifest: dict, *, preferred: dict | None = None, candidate_voices: list[str] | tuple[str, ...] = ()) -> dict[str, str] | None:
    """Return task-bound speech controls or safely recover a legacy default tuple."""
    audio = manifest.get('audio', {})
    signature = audio.get('signature')
    stored = audio.get('controls')
    if controls_match_signature(stored, signature):
        return speech_controls(**stored)
    candidates: list[dict[str, str]] = []
    if isinstance(preferred, dict):
        try:
            candidates.append(speech_controls(**preferred))
        except TypeError:
            pass
    provider_id = str(audio.get('provider_id') or 'edge-tts')
    for voice in candidate_voices:
        candidates.append(speech_controls(provider_id=provider_id, voice=str(voice)))
    seen: set[tuple[str, str, str, str, str]] = set()
    for candidate in candidates:
        key = tuple(candidate[name] for name in ('provider_id', 'voice', 'rate', 'pitch', 'volume'))
        if key in seen:
            continue
        seen.add(key)
        if controls_match_signature(candidate, signature):
            return candidate
    return None


def expected_audio_paths(job: JobPaths, manifest: dict) -> list[Path]:
    return [job.parts_audio / f"part-{int(item['index']):04d}.mp3" for item in manifest['parts']]


def audio_metadata_path(audio_path: Path) -> Path:
    return audio_path.with_name(audio_path.stem + '.meta.json')


def _write_audio_sidecar(audio_path: Path, *, text_sha256: str, signature: str, metadata: dict, controls: dict | None = None) -> None:
    payload = {'text_sha256': text_sha256, 'signature': signature, **metadata}
    if controls_match_signature(controls, signature):
        payload['controls'] = dict(controls)
    atomic_write_json(audio_metadata_path(audio_path), payload)


def reconcile_audio_state(job: JobPaths, *, validator: Callable[[Path], dict] = None) -> dict:
    """Conservatively reconcile durable MP3 state after an abnormal exit."""
    validator = validator or validate_mp3
    manifest = load_manifest(job)
    signature = manifest.get('audio', {}).get('signature')
    controls = manifest.get('audio', {}).get('controls')
    completed = manifest.setdefault('audio', {}).setdefault('completed', {})
    failures = manifest['audio'].setdefault('failures', {})
    removed_partial = []
    for path in job.parts_audio.glob('part-*.partial.mp3'):
        removed_partial.append(path.name); path.unlink(missing_ok=True)
    expected = {int(item['index']): item for item in manifest.get('parts', [])}
    reused = []
    removed_invalid = []
    for index, item in expected.items():
        audio_path = job.parts_audio / f'part-{index:04d}.mp3'
        sidecar = audio_metadata_path(audio_path)
        saved = completed.get(str(index))
        if saved:
            try:
                metadata = validator(audio_path)
                if saved.get('text_sha256') != item.get('sha256') or saved.get('signature') != signature or saved.get('sha256') != metadata.get('sha256'):
                    raise RuntimeError('stale completion record')
                _write_audio_sidecar(audio_path, text_sha256=item['sha256'], signature=signature, metadata=metadata, controls=controls)
                reused.append(index)
                continue
            except Exception:
                completed.pop(str(index), None)
                failures.pop(str(index), None)
                audio_path.unlink(missing_ok=True); sidecar.unlink(missing_ok=True)
                removed_invalid.append(index)
                continue
        if audio_path.exists() and sidecar.exists() and signature:
            try:
                import json
                side = json.loads(sidecar.read_text(encoding='utf-8'))
                metadata = validator(audio_path)
                if side.get('text_sha256') != item.get('sha256') or side.get('signature') != signature or side.get('sha256') != metadata.get('sha256'):
                    raise RuntimeError('untrusted orphan MP3')
                completed[str(index)] = {'text_sha256': item['sha256'], 'signature': signature, **metadata}
                failures.pop(str(index), None)
                reused.append(index)
                continue
            except Exception:
                pass
        if audio_path.exists():
            audio_path.unlink(missing_ok=True)
            audio_metadata_path(audio_path).unlink(missing_ok=True)
            sidecar.unlink(missing_ok=True)
            removed_invalid.append(index)
    valid_indexes = sorted(int(value) for value in completed)
    total = len(expected)
    next_part = next((index for index in range(1, total + 1) if index not in set(valid_indexes)), None)
    execution = manifest.setdefault('execution', {})
    if next_part is None and total:
        execution.update({'status': 'idle', 'resume_required': False, 'current_part': None, 'current_part_state': None})
    elif execution.get('status') == 'running':
        execution.update({'status': 'interrupted', 'resume_required': True})
    save_manifest(job, manifest)
    append_job_log(job, 'audio-reconciled', reused=reused, removed_invalid=removed_invalid, removed_partial=removed_partial, next_part=next_part)
    return {'reused': reused, 'removed_invalid': removed_invalid, 'removed_partial': removed_partial, 'next_part': next_part, 'completed': valid_indexes, 'total': total}


def validate_mp3(path: Path, *, ffprobe: str = 'ffprobe') -> dict:
    if not path.exists() or path.stat().st_size <= 1024:
        raise RuntimeError(f'MP3 missing or too small: {path.name}')
    require_command(ffprobe, 'install FFmpeg')
    result = run_hidden_cli(
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


def audition_sample(*, voice: str, rate: str = '+0%', pitch: str = '+0Hz', volume: str = '+0%', provider_id: str = 'edge-tts', output_dir: Path | None = None, validator: Callable[[Path], dict] = validate_mp3) -> Path:
    output_dir = Path(output_dir or tempfile.gettempdir())
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_voice = ''.join(char for char in voice if char.isalnum() or char in '-_')
    final = output_dir / f'audition-{safe_voice}.mp3'
    partial = unique_partial_path(final, before_suffix=True)
    cleanup_stale_partials(final)
    sample = '这是语音试听。价值投资的核心，是以合理的价格买入优秀的公司，并长期持有。'
    get_tts_provider(provider_id).synthesize(sample, partial, voice=voice, rate=rate, pitch=pitch, volume=volume)
    validator(partial)
    replace_with_retry(partial, final)
    return final


def _emit(progress: ProgressCallback | None, **payload: object) -> None:
    if progress:
        progress(payload)


def _accepts_keyword(fn: Callable[..., object], name: str) -> bool:
    try:
        parameters = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(parameter.kind == inspect.Parameter.VAR_KEYWORD or parameter.name == name for parameter in parameters)


def _invoke_save_func(
    save_func: Callable[..., object],
    text: str,
    partial: Path,
    *,
    voice: str,
    rate: str,
    pitch: str,
    volume: str,
    provider_progress: Callable[[dict[str, object]], None] | None = None,
) -> None:
    kwargs: dict[str, object] = {'voice': voice, 'rate': rate, 'pitch': pitch, 'volume': volume}
    if provider_progress is not None and _accepts_keyword(save_func, 'progress'):
        kwargs['progress'] = provider_progress
    maybe = save_func(text, partial, **kwargs)
    if asyncio.iscoroutine(maybe):
        asyncio.run(maybe)


def _provider_switch_recommendation(provider_id: str, error: str) -> str | None:
    if provider_id != 'edge-tts':
        return None
    return (
        'Edge Online TTS failed. Recommended action: switch TTS engine to Kokoro Local TTS, '
        'generate Preview Part 1 again, listen, approve Part 1, then resume from the first incomplete Part. '
        f'Original error: {error}'
    )


def _provider_progress_bridge(
    job: JobPaths,
    manifest: dict,
    progress: ProgressCallback | None,
    *,
    index: int,
    attempt: int,
    provider_id: str,
) -> Callable[[dict[str, object]], None]:
    last_logged_monotonic = 0.0
    last_stage = ''

    def callback(payload: dict[str, object]) -> None:
        nonlocal last_logged_monotonic, last_stage
        now = time.monotonic()
        telemetry = {
            'provider_id': str(payload.get('provider_id') or provider_id),
            'stage': str(payload.get('stage') or 'provider-running'),
            'attempt': int(attempt),
            'index': int(index),
            'elapsed_seconds': float(payload.get('elapsed_seconds') or 0.0),
            'bytes_received': int(payload.get('bytes_received') or 0),
            'last_audio_seconds_ago': float(payload.get('last_audio_seconds_ago') or 0.0),
        }
        manifest.setdefault('audio', {})['last_runtime_telemetry'] = dict(telemetry)
        stage_changed = telemetry['stage'] != last_stage
        if stage_changed or now - last_logged_monotonic >= 15.0:
            append_job_log(job, 'provider-runtime', **telemetry)
            save_manifest(job, manifest)
            last_logged_monotonic = now
            last_stage = telemetry['stage']
        _emit(progress, state='provider-status', estimated_percent=0, **telemetry)

    return callback


def _invalidate_for_signature(job: JobPaths, manifest: dict, controls: dict[str, str]) -> None:
    signature = audio_signature(**controls)
    if manifest.get('audio', {}).get('signature') == signature:
        return
    reset_audio_state(job, manifest, reason='voice-or-speaking-controls-changed', signature=signature, controls=controls)


def _synthesize_parts_unlocked(
    job: JobPaths,
    *,
    voice: str,
    rate: str = '+0%',
    pitch: str = '+0Hz',
    volume: str = '+0%',
    provider_id: str = 'edge-tts',
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
    controls = speech_controls(voice=voice, rate=rate, pitch=pitch, volume=volume, provider_id=provider_id)
    signature = audio_signature(**controls)
    if require_preview_approval:
        assert_preview_approved(manifest, signature=signature)
    _invalidate_for_signature(job, manifest, controls)
    manifest['audio']['provider_id'] = provider_id
    manifest['audio']['controls'] = controls
    completed = manifest['audio']['completed']
    failures = manifest['audio']['failures']
    parts = manifest['parts']
    end = end or int(parts[-1]['index'])
    save_func = save_func or get_tts_provider(provider_id).synthesize
    selected = [item for item in parts if start <= int(item['index']) <= end and (indexes is None or int(item['index']) in indexes)]
    if not selected:
        raise RuntimeError('No matching text parts were selected for synthesis.')
    begin_execution(job, manifest, 'synthesize-parts', current_part=int(selected[0]['index']))
    append_job_log(job, 'synthesis-started', selected=[int(item['index']) for item in selected], signature=signature)
    for item in selected:
        _emit(progress, index=int(item['index']), state='queued', estimated_percent=0, text_chars=len((job.parts_text / item['file']).read_text(encoding='utf-8')))
    run_failures: list[dict] = []
    for item in selected:
        index = int(item['index'])
        text_path = job.parts_text / item['file']
        audio_path = job.parts_audio / f'part-{index:04d}.mp3'
        cleanup_stale_partials(audio_path)
        partial = unique_partial_path(audio_path, before_suffix=True)
        checkpoint_execution(job, manifest, last_step='part-started', current_part=index, current_part_state='running')
        text = text_path.read_text(encoding='utf-8')
        text_chars = len(text)
        part_started_monotonic = time.monotonic()
        if audio_path.exists():
            try:
                metadata = validator(audio_path)
                saved = completed.get(str(index), {})
                if saved.get('text_sha256') == item['sha256'] and saved.get('signature') == signature and saved.get('sha256') == metadata.get('sha256'):
                    completed[str(index)] = {'text_sha256': item['sha256'], 'signature': signature, **metadata}
                    failures.pop(str(index), None)
                    save_manifest(job, manifest)
                    checkpoint_execution(job, manifest, last_step='part-reused', current_part=index, current_part_state='done', last_completed_part=index)
                    _emit(progress, index=index, state='done', reused=True, estimated_percent=100, text_chars=text_chars, elapsed_seconds=0)
                    append_job_log(job, 'part-reused', index=index)
                    continue
            except RuntimeError:
                pass
            audio_path.unlink(missing_ok=True)
            audio_metadata_path(audio_path).unlink(missing_ok=True)
        completed.pop(str(index), None)
        save_manifest(job, manifest)
        ok = False
        last_error = None
        for attempt in range(1, retries + 2):
            partial.unlink(missing_ok=True)
            state = 'running' if attempt == 1 else 'retrying'
            _emit(progress, index=index, state=state, attempt=attempt, estimated_percent=5, text_chars=text_chars)
            append_job_log(job, f'part-{state}', index=index, attempt=attempt)
            try:
                provider_progress = _provider_progress_bridge(
                    job, manifest, progress, index=index, attempt=attempt, provider_id=provider_id,
                )
                _invoke_save_func(
                    save_func, text, partial, voice=voice, rate=rate, pitch=pitch, volume=volume,
                    provider_progress=provider_progress,
                )
                _emit(progress, index=index, state='validating', estimated_percent=95, text_chars=text_chars)
                metadata = validator(partial)
                replace_with_retry(partial, audio_path)
                _write_audio_sidecar(audio_path, text_sha256=item['sha256'], signature=signature, metadata=metadata, controls=controls)
                completed[str(index)] = {'text_sha256': item['sha256'], 'signature': signature, **metadata}
                failures.pop(str(index), None)
                save_manifest(job, manifest)
                ok = True
                checkpoint_execution(job, manifest, last_step='part-completed', current_part=index, current_part_state='done', last_completed_part=index)
                _emit(progress, index=index, state='done', reused=False, estimated_percent=100, text_chars=text_chars, elapsed_seconds=time.monotonic() - part_started_monotonic)
                append_job_log(job, 'part-completed', index=index, duration_seconds=metadata.get('duration_seconds'))
                break
            except Exception as exc:
                last_error = f'{type(exc).__name__}: {exc}'
                partial.unlink(missing_ok=True)
                recommendation = _provider_switch_recommendation(provider_id, last_error)
                append_job_log(job, 'part-attempt-failed', index=index, attempt=attempt, provider_id=provider_id, error=last_error, switch_recommendation=recommendation)
                if attempt <= retries:
                    retry_delay = min(45.0, 5.0 * (3 ** (attempt - 1)))
                    _emit(progress, index=index, state='retry-wait', attempt=attempt + 1, retry_delay_seconds=retry_delay, error=last_error, switch_recommendation=recommendation, text_chars=text_chars)
                    time.sleep(retry_delay)
        if not ok:
            recommendation = _provider_switch_recommendation(provider_id, str(last_error))
            failures[str(index)] = {'error': last_error, 'text_sha256': item['sha256'], 'signature': signature, 'provider_id': provider_id, 'switch_recommendation': recommendation}
            run_failures.append({'index': index, 'error': last_error, 'provider_id': provider_id, 'switch_recommendation': recommendation})
            checkpoint_execution(job, manifest, last_step='part-failed', current_part=index, current_part_state='failed')
            _emit(progress, index=index, state='failed', error=last_error, switch_recommendation=recommendation, estimated_percent=0, text_chars=text_chars)
            append_job_log(job, 'part-failed', index=index, provider_id=provider_id, error=last_error, switch_recommendation=recommendation)
        if gap_seconds:
            time.sleep(gap_seconds)
    finish_execution(job, manifest, status='completed-with-failures' if run_failures else 'idle', last_step='synthesis-finished')
    append_job_log(job, 'synthesis-finished', failures=len(run_failures), completed=len(completed))
    export_report = None
    all_indexes = {int(item['index']) for item in parts}
    if require_preview_approval and not run_failures and set(int(index) for index in completed) == all_indexes:
        from .export import finalize_export
        export_report = finalize_export(job, validator=validator, progress=progress)
    return {'failures': run_failures, 'completed': sorted(int(index) for index in completed), 'export': export_report}


def synthesize_parts(job: JobPaths, *, keep_awake: bool = True, **kwargs: object) -> dict:
    with job_operation_lock(job, 'synthesize-parts'):
        with keep_computer_awake(keep_awake):
            try:
                return _synthesize_parts_unlocked(job, **kwargs)
            except Exception:
                manifest = load_manifest(job)
                if manifest.get('execution', {}).get('status') == 'running':
                    finish_execution(job, manifest, status='failed', last_step='synthesis-aborted')
                raise


def retry_failed_parts(job: JobPaths, *, keep_awake: bool = True, **kwargs: object) -> dict:
    with job_operation_lock(job, 'retry-failed-parts'):
        with keep_computer_awake(keep_awake):
            manifest = load_manifest(job)
            indexes = {int(index) for index in manifest['audio'].get('failures', {})}
            if not indexes:
                raise RuntimeError('No failed audio parts are recorded for retry.')
            try:
                return _synthesize_parts_unlocked(job, indexes=indexes, **kwargs)
            except Exception:
                manifest = load_manifest(job)
                if manifest.get('execution', {}).get('status') == 'running':
                    finish_execution(job, manifest, status='failed', last_step='retry-aborted')
                raise


def approve_preview(job: JobPaths, *, voice: str, rate: str = '+0%', pitch: str = '+0Hz', volume: str = '+0%', provider_id: str = 'edge-tts', validator: Callable[[Path], dict] = validate_mp3) -> dict:
    with job_operation_lock(job, 'approve-preview'):
        manifest = load_manifest(job)
        assert_proofread_approved(job, manifest)
        controls = speech_controls(voice=voice, rate=rate, pitch=pitch, volume=volume, provider_id=provider_id)
        signature = audio_signature(**controls)
        if manifest['audio'].get('signature') != signature:
            raise RuntimeError('Part 1 must be generated with the currently selected voice and speaking rate before approval.')
        first = manifest['parts'][0]
        saved = manifest['audio']['completed'].get('1')
        if not saved or saved.get('text_sha256') != first['sha256'] or saved.get('signature') != signature:
            raise RuntimeError('Part 1 has not been generated for the current text and voice settings.')
        metadata = validator(job.parts_audio / 'part-0001.mp3')
        if metadata.get('sha256') != saved.get('sha256'):
            raise RuntimeError('Part 1 audio changed after synthesis. Generate the preview again.')
        manifest['audio']['provider_id'] = provider_id
        manifest['audio']['controls'] = controls
        approval = approve_preview_state(job, manifest, signature=signature)
        save_manifest(job, manifest)
        return approval



def generate_resume_voice_check(
    job: JobPaths,
    *,
    voice: str,
    rate: str = '+0%',
    pitch: str = '+0Hz',
    volume: str = '+0%',
    provider_id: str = 'edge-tts',
    save_func: Callable[..., object] | None = None,
    validator: Callable[[Path], dict] = validate_mp3,
) -> dict:
    """Create a candidate Part-1 preview without mutating preserved completed audio."""
    with job_operation_lock(job, 'resume-voice-check'):
        manifest = load_manifest(job)
        assert_proofread_approved(job, manifest)
        first = manifest.get('parts', [None])[0]
        if not first:
            raise RuntimeError('No Part 1 text exists for resume voice verification.')
        existing = job.parts_audio / 'part-0001.mp3'
        saved = manifest.get('audio', {}).get('completed', {}).get('1')
        if not saved or not existing.exists():
            raise RuntimeError('The preserved Part 1 MP3 is missing. Start a new preview before resuming.')
        existing_metadata = validator(existing)
        if saved.get('sha256') != existing_metadata.get('sha256') or saved.get('text_sha256') != first.get('sha256'):
            raise RuntimeError('The preserved Part 1 MP3 does not match its checkpoint. Start a new preview before resuming.')
        controls = speech_controls(voice=voice, rate=rate, pitch=pitch, volume=volume, provider_id=provider_id)
        signature = audio_signature(**controls)
        folder = job.work / 'resume_voice_check'
        folder.mkdir(parents=True, exist_ok=True)
        candidate = folder / 'candidate-part-0001.mp3'
        cleanup_stale_partials(candidate)
        partial = unique_partial_path(candidate, before_suffix=True)
        save_func = save_func or get_tts_provider(provider_id).synthesize
        _invoke_save_func(
            save_func, (job.parts_text / first['file']).read_text(encoding='utf-8'), partial,
            voice=voice, rate=rate, pitch=pitch, volume=volume,
        )
        candidate_metadata = validator(partial)
        replace_with_retry(partial, candidate)
        append_job_log(job, 'resume-voice-check-generated', signature=signature, preserved_part_one=str(existing), candidate_part_one=str(candidate))
        return {
            'existing_part_one': str(existing),
            'candidate_part_one': str(candidate),
            'candidate_metadata': candidate_metadata,
            'controls': controls,
            'signature': signature,
        }


def approve_legacy_resume_controls(
    job: JobPaths,
    *,
    voice: str,
    rate: str = '+0%',
    pitch: str = '+0Hz',
    volume: str = '+0%',
    provider_id: str = 'edge-tts',
    validator: Callable[[Path], dict] = validate_mp3,
) -> dict:
    """Bind preserved legacy MP3 files to an Owner-approved control tuple after audible comparison."""
    with job_operation_lock(job, 'approve-legacy-resume-controls'):
        manifest = load_manifest(job)
        assert_proofread_approved(job, manifest)
        controls = speech_controls(voice=voice, rate=rate, pitch=pitch, volume=volume, provider_id=provider_id)
        signature = audio_signature(**controls)
        completed = manifest.get('audio', {}).get('completed', {})
        records = {str(int(item['index'])): item for item in manifest.get('parts', [])}
        if not completed:
            raise RuntimeError('No preserved MP3 files exist for legacy resume approval.')
        rebound: list[int] = []
        for key in sorted(completed, key=lambda value: int(value)):
            item = records.get(str(int(key)))
            if not item:
                raise RuntimeError(f'Preserved Part {key} is not declared by the current manifest.')
            audio_path = job.parts_audio / f'part-{int(key):04d}.mp3'
            metadata = validator(audio_path)
            saved = completed[key]
            if saved.get('text_sha256') != item.get('sha256') or saved.get('sha256') != metadata.get('sha256'):
                raise RuntimeError(f'Preserved Part {key} failed checkpoint verification.')
            completed[key] = {'text_sha256': item['sha256'], 'signature': signature, **metadata, 'legacy_owner_voice_check': True}
            _write_audio_sidecar(audio_path, text_sha256=item['sha256'], signature=signature, metadata=metadata, controls=controls)
            rebound.append(int(key))
        manifest['audio']['provider_id'] = provider_id
        manifest['audio']['signature'] = signature
        manifest['audio']['controls'] = controls
        approval = approve_preview_state(job, manifest, signature=signature)
        manifest.setdefault('resume', {}).setdefault('legacy_owner_voice_checks', []).append({
            'signature': signature,
            'controls': controls,
            'rebound_parts': rebound,
            'approved_utc': approval.get('approved_utc'),
        })
        save_manifest(job, manifest)
        append_job_log(job, 'legacy-resume-controls-approved', signature=signature, rebound_parts=rebound)
        return {'approval': approval, 'controls': controls, 'signature': signature, 'rebound_parts': rebound}

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
        cleanup_stale_partials(output)
        partial = unique_partial_path(output, before_suffix=True)
        try:
            run_hidden_cli([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(concat_list), '-c', 'copy', str(partial)], check=True)
            merged_metadata = validate_mp3(partial)
            replace_with_retry(partial, output)
        except Exception as exc:
            partial.unlink(missing_ok=True)
            append_job_log(job, 'merge-failed', error=f'{type(exc).__name__}: {exc}')
            raise
        manifest['merge'] = {'output_runtime_only': str(output), 'signature': signature, **merged_metadata}
        save_manifest(job, manifest)
        from .export import finalize_export, verify_export
        finalize_export(job, validator=validator)
        verify_export(job, validator=validator, require_merged=True)
        append_job_log(job, 'merge-completed', output=str(output), duration_seconds=merged_metadata.get('duration_seconds'))
        return output
