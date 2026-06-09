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
import signal
from .durable_io import write_json as durable_write_json, write_text as durable_write_text

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
    durable_write_text(Path(path), text)


def atomic_write_json(path: Path, payload: object) -> None:
    durable_write_json(Path(path), payload)


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




def process_is_alive(pid: int) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == 'nt':
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return False
                return int(code.value) == STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_operation_lock(job: 'JobPaths') -> dict:
    path = job.work / '.operation.lock'
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def recover_stale_lock(job: 'JobPaths', *, process_checker=process_is_alive) -> dict:
    path = job.work / '.operation.lock'
    if not path.exists():
        return {'removed': False, 'reason': 'absent'}
    payload = read_operation_lock(job)
    pid = payload.get('pid')
    if not isinstance(pid, int):
        raise RuntimeError(f'Job lock is malformed and cannot be cleared automatically: {path}')
    if process_checker(pid):
        return {'removed': False, 'reason': 'live-process', 'pid': pid}
    path.unlink(missing_ok=True)
    append_job_log(job, 'stale-lock-removed', pid=pid, operation=payload.get('operation'))
    return {'removed': True, 'reason': 'dead-process', 'pid': pid}

def append_job_log(job: 'JobPaths', event: str, **fields: object) -> None:
    """Append one durable JSON-line event to a job log."""
    job.run_log.parent.mkdir(parents=True, exist_ok=True)
    payload = {'time': datetime.now().isoformat(timespec='seconds'), 'event': event, **fields}
    with job.run_log.open('a', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + '\n')


@contextmanager
def job_operation_lock(job: 'JobPaths', operation: str) -> Iterator[None]:
    """Reject concurrent mutations through a compatibility file lock and SQLite lease."""
    job.work.mkdir(parents=True, exist_ok=True)
    lock_path = job.work / '.operation.lock'
    if lock_path.exists():
        recovered = recover_stale_lock(job)
        if recovered.get('reason') == 'live-process':
            raise RuntimeError(f'Job is busy: {lock_path}')
    try:
        descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(
            f'Job is busy or a prior run ended unexpectedly: {lock_path}. '
            'Close other KR Book To Audio processes. Remove the lock file only after confirming no operation is running.'
        ) from exc
    lease_token: str | None = None
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps({'operation': operation, 'pid': os.getpid(), 'time': datetime.now().isoformat(timespec='seconds')}) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        if getattr(job, 'manifest', None) is not None and (job.manifest.exists() or getattr(job, 'state_db', Path()).exists()):
            from .manifest import load_manifest
            from .job_state import acquire_lease
            load_manifest(job)  # migrate legacy JSON before acquiring the authoritative lease
            lease_token = acquire_lease(job, operation=operation, pid=os.getpid(), process_checker=process_is_alive)
        yield
    finally:
        if lease_token:
            try:
                from .job_state import release_lease
                release_lease(job, lease_token)
            except Exception:
                pass
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
