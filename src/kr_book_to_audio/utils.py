from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Iterator, TYPE_CHECKING
import json
import os
import re
import shutil

if TYPE_CHECKING:
    from .models import JobPaths

_ILLEGAL = re.compile(r'[\\/:*?"<>|\t\r\n]+')


def sha256_file(path: Path) -> str:
    h = sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return sha256(text.encode('utf-8')).hexdigest()


def sanitize_filename(name: str | None, fallback: str = 'book') -> str:
    value = _ILLEGAL.sub('', name or '').strip(' ._-')
    return value[:96] or fallback


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.partial')
    temp.write_text(text, encoding='utf-8', newline='\n')
    os.replace(temp, path)


def atomic_write_json(path: Path, payload: object) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n')


def clear_files(directory: Path, pattern: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob(pattern):
        if path.is_file():
            path.unlink()


def require_command(name: str, hint: str | None = None) -> str:
    found = shutil.which(name)
    if found:
        return found
    suffix = f' ({hint})' if hint else ''
    raise RuntimeError(f'Required command not found: {name}{suffix}')


def append_job_log(job: 'JobPaths', event: str, **fields: object) -> None:
    """Append one durable JSON-line event to a job log."""
    job.run_log.parent.mkdir(parents=True, exist_ok=True)
    payload = {'time': datetime.now().isoformat(timespec='seconds'), 'event': event, **fields}
    with job.run_log.open('a', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + '\n')


@contextmanager
def job_operation_lock(job: 'JobPaths', operation: str) -> Iterator[None]:
    """Reject concurrent mutations of one job directory across GUI and CLI processes."""
    job.work.mkdir(parents=True, exist_ok=True)
    lock_path = job.work / '.operation.lock'
    try:
        descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(
            f'Job is busy or a prior run ended unexpectedly: {lock_path}. '
            'Close other KR Book To Audio processes. Remove the lock file only after confirming no operation is running.'
        ) from exc
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps({'operation': operation, 'pid': os.getpid(), 'time': datetime.now().isoformat(timespec='seconds')}) + '\n')
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    import zipfile
    destination = destination.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if destination != target and destination not in target.parents:
                raise ValueError(f'Unsafe ZIP member: {member.filename}')
        archive.extractall(destination)
