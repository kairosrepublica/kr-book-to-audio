from __future__ import annotations
from pathlib import Path
from typing import Callable
import asyncio
import os
import subprocess
import time
import tempfile
from .models import JobPaths
from .manifest import load_manifest, save_manifest
from .utils import clear_files, require_command, sha256_file, sha256_text


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
    """Generate one atomic voice sample for listening before a full synthesis run."""
    output_dir = Path(output_dir or tempfile.gettempdir())
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_voice = ''.join(ch for ch in voice if ch.isalnum() or ch in '-_')
    final = output_dir / f'audition-{safe_voice}.mp3'
    partial = output_dir / f'audition-{safe_voice}.partial.mp3'
    partial.unlink(missing_ok=True)
    sample = '这是语音试听。价值投资的核心，是以合理的价格买入优秀的公司，并长期持有。'
    asyncio.run(_edge_save(sample, partial, voice=voice, rate=rate, pitch=pitch, volume=volume))
    validator(partial)
    os.replace(partial, final)
    return final


def _invalidate_audio(job: JobPaths, manifest: dict, signature: str) -> None:
    if manifest.get('audio', {}).get('signature') == signature:
        return
    clear_files(job.parts_audio, 'part-*.mp3')
    clear_files(job.parts_audio, 'part-*.mp3.partial')
    manifest['audio'] = {'signature': signature, 'completed': {}}


async def _edge_save(text: str, out_path: Path, *, voice: str, rate: str, pitch: str, volume: str) -> None:
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume).save(str(out_path))


def synthesize_parts(
    job: JobPaths,
    *,
    voice: str,
    rate: str = '+0%',
    pitch: str = '+0Hz',
    volume: str = '+0%',
    start: int = 1,
    end: int | None = None,
    retries: int = 3,
    gap_seconds: float = 2.0,
    save_func: Callable[..., object] | None = None,
    validator: Callable[[Path], dict] = validate_mp3,
) -> dict:
    manifest = load_manifest(job)
    signature = audio_signature(voice=voice, rate=rate, pitch=pitch, volume=volume)
    _invalidate_audio(job, manifest, signature)
    completed = manifest['audio']['completed']
    parts = manifest['parts']
    if not parts:
        raise RuntimeError('No text parts exist. Prepare or rebuild the job first.')
    end = end or int(parts[-1]['index'])
    save_func = save_func or _edge_save
    failures = []
    for item in parts:
        index = int(item['index'])
        if index < start or index > end:
            continue
        text_path = job.parts_text / item['file']
        audio_path = job.parts_audio / f'part-{index:04d}.mp3'
        partial = audio_path.with_name(audio_path.name + '.partial')
        if audio_path.exists():
            try:
                metadata = validator(audio_path)
                if completed.get(str(index), {}).get('text_sha256') == item['sha256']:
                    completed[str(index)] = {'text_sha256': item['sha256'], **metadata}
                    save_manifest(job, manifest)
                    continue
            except RuntimeError:
                audio_path.unlink(missing_ok=True)
        ok = False
        last_error = None
        for attempt in range(1, retries + 2):
            partial.unlink(missing_ok=True)
            try:
                maybe = save_func(text_path.read_text(encoding='utf-8'), partial, voice=voice, rate=rate, pitch=pitch, volume=volume)
                if asyncio.iscoroutine(maybe):
                    asyncio.run(maybe)
                metadata = validator(partial)
                os.replace(partial, audio_path)
                completed[str(index)] = {'text_sha256': item['sha256'], **metadata}
                save_manifest(job, manifest)
                ok = True
                break
            except Exception as exc:  # network, endpoint, filesystem or validation error
                last_error = f'{type(exc).__name__}: {exc}'
                partial.unlink(missing_ok=True)
                if attempt <= retries:
                    time.sleep(min(45.0, 5.0 * (3 ** (attempt - 1))))
        if not ok:
            failures.append({'index': index, 'error': last_error})
        if gap_seconds:
            time.sleep(gap_seconds)
    save_manifest(job, manifest)
    return {'failures': failures, 'completed': sorted(int(i) for i in completed)}


def merge_parts(job: JobPaths, *, output_name: str | None = None, validator: Callable[[Path], dict] = validate_mp3) -> Path:
    manifest = load_manifest(job)
    expected = expected_audio_paths(job, manifest)
    if not expected:
        raise RuntimeError('No manifest-declared audio parts exist.')
    for path in expected:
        validator(path)
    ffmpeg = require_command('ffmpeg', 'install FFmpeg')
    concat_list = job.work / 'concat.txt'
    concat_list.write_text(''.join(f"file '{path.resolve().as_posix()}'\n" for path in expected), encoding='utf-8', newline='\n')
    output = job.export / (output_name or f"{manifest['title']}.mp3")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.stem + '.partial' + output.suffix)
    partial.unlink(missing_ok=True)
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(concat_list), '-c', 'copy', str(partial)], check=True)
    validate_mp3(partial)
    os.replace(partial, output)
    return output
