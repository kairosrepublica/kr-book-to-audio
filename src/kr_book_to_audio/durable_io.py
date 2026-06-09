from __future__ import annotations
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Callable, Iterator
import errno
import json
import os
import shutil
import threading
import time
import uuid

RetryCallback = Callable[[dict[str, object]], None]

_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


def _path_key(path: Path) -> str:
    try:
        return os.path.normcase(str(Path(path).resolve()))
    except OSError:
        return os.path.normcase(str(Path(path).absolute()))


def path_lock(path: Path) -> threading.RLock:
    key = _path_key(path)
    with _LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, (PermissionError, BlockingIOError)):
        return True
    if isinstance(exc, OSError):
        return getattr(exc, 'winerror', None) in {5, 32, 33} or exc.errno in {errno.EACCES, errno.EBUSY, errno.EPERM}
    return False


def _emit(callback: RetryCallback | None, *, path: Path, attempt: int, max_attempts: int, error: BaseException) -> None:
    if callback:
        callback({
            'event': 'durable-write-retry',
            'path': str(path),
            'attempt': attempt,
            'max_attempts': max_attempts,
            'error': f'{type(error).__name__}: {error}',
        })


def _fsync_parent(path: Path) -> None:
    if os.name == 'nt':
        return
    try:
        descriptor = os.open(str(path.parent), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def unique_partial_path(destination: Path, *, before_suffix: bool = False) -> Path:
    destination = Path(destination)
    token = uuid.uuid4().hex
    if before_suffix and destination.suffix:
        return destination.with_name(f'{destination.stem}.{token}.partial{destination.suffix}')
    return destination.with_name(f'{destination.name}.{token}.partial')


def cleanup_stale_partials(destination: Path, *, older_than_seconds: float = 3600.0) -> list[str]:
    destination = Path(destination)
    removed: list[str] = []
    now = time.time()
    patterns = [f'{destination.name}.*.partial']
    if destination.suffix:
        patterns.append(f'{destination.stem}.*.partial{destination.suffix}')
    for pattern in patterns:
        for candidate in destination.parent.glob(pattern):
            try:
                if candidate.is_file() and now - candidate.stat().st_mtime >= older_than_seconds:
                    candidate.unlink(missing_ok=True)
                    removed.append(candidate.name)
            except OSError:
                continue
    return sorted(set(removed))


def replace_with_retry(
    source: Path,
    destination: Path,
    *,
    attempts: int = 7,
    initial_delay: float = 0.04,
    retry_callback: RetryCallback | None = None,
    cleanup_source_on_failure: bool = True,
) -> None:
    source = Path(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if attempts < 1:
        raise ValueError('attempts must be positive')
    lock = path_lock(destination)
    with lock:
        last_error: BaseException | None = None
        for attempt in range(1, attempts + 1):
            try:
                os.replace(source, destination)
                _fsync_parent(destination)
                return
            except BaseException as exc:  # preserve exact failure type after bounded retries
                last_error = exc
                if not _retryable(exc) or attempt >= attempts:
                    break
                _emit(retry_callback, path=destination, attempt=attempt, max_attempts=attempts, error=exc)
                time.sleep(initial_delay * (2 ** (attempt - 1)) + min(0.02, attempt * 0.003))
        if cleanup_source_on_failure:
            try:
                source.unlink(missing_ok=True)
            except OSError:
                pass
        assert last_error is not None
        raise last_error


def write_bytes(
    path: Path,
    payload: bytes,
    *,
    attempts: int = 7,
    retry_callback: RetryCallback | None = None,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cleanup_stale_partials(path)
    partial = unique_partial_path(path)
    lock = path_lock(path)
    with lock:
        try:
            with partial.open('wb') as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            replace_with_retry(partial, path, attempts=attempts, retry_callback=retry_callback)
        except Exception:
            partial.unlink(missing_ok=True)
            raise


def write_text(
    path: Path,
    text: str,
    *,
    attempts: int = 7,
    retry_callback: RetryCallback | None = None,
) -> None:
    write_bytes(Path(path), text.encode('utf-8'), attempts=attempts, retry_callback=retry_callback)


def write_json(
    path: Path,
    payload: object,
    *,
    attempts: int = 7,
    retry_callback: RetryCallback | None = None,
) -> None:
    write_text(
        Path(path),
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        attempts=attempts,
        retry_callback=retry_callback,
    )


def file_sha256(path: Path) -> str:
    digest = sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def copy_verified(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str | None = None,
    attempts: int = 7,
    retry_callback: RetryCallback | None = None,
) -> str:
    source = Path(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    cleanup_stale_partials(destination)
    partial = unique_partial_path(destination, before_suffix=True)
    lock = path_lock(destination)
    with lock:
        try:
            with source.open('rb') as src, partial.open('wb') as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
                dst.flush()
                os.fsync(dst.fileno())
            copied_sha = file_sha256(partial)
            source_sha = expected_sha256 or file_sha256(source)
            if copied_sha != source_sha:
                raise RuntimeError(f'Durable copy SHA-256 mismatch: {destination.name}')
            replace_with_retry(partial, destination, attempts=attempts, retry_callback=retry_callback)
            return copied_sha
        except Exception:
            partial.unlink(missing_ok=True)
            raise
