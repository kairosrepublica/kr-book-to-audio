from __future__ import annotations
from pathlib import Path
from kr_book_to_audio.audio import audio_signature
from kr_book_to_audio.manifest import load_manifest, save_manifest
from kr_book_to_audio.pipeline import approve_proofread_and_rebuild, prepare_job
from kr_book_to_audio.utils import sha256_file


def make_prepared_job(root: Path, text: str = '中文内容。', *, chunk_chars: int = 100, dictionary: Path | None = None):
    source = root / 'source.txt'
    source.write_text(text, encoding='utf-8', newline='\n')
    job = prepare_job(source, work_root=root / 'jobs', export_root=root / 'exports', chunk_chars=chunk_chars, dictionary_path=dictionary)
    approve_proofread_and_rebuild(job, dictionary_path=dictionary, chunk_chars=chunk_chars)
    return job


def fake_save(text, out, **kwargs):
    out.write_bytes((text.encode('utf-8') + b'x' * 4096)[:4096])


def fake_validate(path: Path):
    if not path.exists() or path.stat().st_size <= 1024:
        raise RuntimeError(f'missing or too small: {path.name}')
    return {'bytes': path.stat().st_size, 'duration_seconds': 1.0, 'sha256': sha256_file(path)}


def approve_fake_audio(job, *, voice: str = 'voice', rate: str = '+0%'):
    manifest = load_manifest(job)
    signature = audio_signature(voice=voice, rate=rate)
    manifest['audio']['signature'] = signature
    for item in manifest['parts']:
        index = int(item['index'])
        path = job.parts_audio / f'part-{index:04d}.mp3'
        path.write_bytes(b'x' * (2048 + index))
        manifest['audio']['completed'][str(index)] = {'text_sha256': item['sha256'], 'signature': signature, **fake_validate(path)}
    manifest['gates']['preview'] = {
        'approved_audio_signature': signature,
        'approved_part_sha256': manifest['parts'][0]['sha256'],
        'approved_utc': 'test',
    }
    save_manifest(job, manifest)
    return signature
