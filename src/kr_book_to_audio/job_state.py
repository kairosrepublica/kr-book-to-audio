from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
import copy
import json
import os
import shutil
import sqlite3
import time
import uuid

from .durable_io import write_json

STATE_SCHEMA_VERSION = 1
DEFAULT_BUSY_TIMEOUT_MS = 5000


class JobStateError(RuntimeError):
    pass


class JobStateIntegrityError(JobStateError):
    pass


class JobStateBusyError(JobStateError):
    pass


class StaleStateRevisionError(JobStateError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(job, *, create: bool = True) -> sqlite3.Connection:
    state_db = Path(job.state_db)
    if not create and not state_db.exists():
        raise FileNotFoundError(state_db)
    state_db.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(state_db), timeout=DEFAULT_BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute(f'PRAGMA busy_timeout={DEFAULT_BUSY_TIMEOUT_MS}')
        connection.execute('PRAGMA synchronous=FULL')
        mode = str(connection.execute('PRAGMA journal_mode=WAL').fetchone()[0]).lower()
        if mode not in {'wal', 'memory'}:
            raise JobStateError(f'Unable to enable WAL journal mode for durable job state: {mode}')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS state_document (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                revision INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                updated_utc TEXT NOT NULL
            )
        ''')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                revision INTEGER,
                event TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_utc TEXT NOT NULL
            )
        ''')
        connection.execute('''
            CREATE TABLE IF NOT EXISTS job_lease (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                owner_token TEXT NOT NULL,
                pid INTEGER NOT NULL,
                operation TEXT NOT NULL,
                acquired_utc TEXT NOT NULL,
                heartbeat_utc TEXT NOT NULL
            )
        ''')
        return connection
    except BaseException:
        # sqlite3.connect() can succeed while a later PRAGMA or schema statement
        # fails, for example when a corrupted database is opened. Always close
        # the partially initialized handle before propagating the failure. On
        # Windows an unclosed handle prevents quarantine, cleanup and recovery.
        try:
            connection.close()
        except sqlite3.Error:
            pass
        raise


def quick_check(job) -> None:
    connection = _connect(job, create=False)
    try:
        result = str(connection.execute('PRAGMA quick_check').fetchone()[0])
    finally:
        connection.close()
    if result.lower() != 'ok':
        raise JobStateIntegrityError(f'Job-state SQLite quick_check failed: {result}')


def _retry_transaction(action: Callable[[], object], *, attempts: int = 7, initial_delay: float = 0.05):
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if 'locked' not in message and 'busy' not in message:
                raise
            last_error = exc
            if attempt >= attempts:
                break
            time.sleep(initial_delay * (2 ** (attempt - 1)) + min(0.02, attempt * 0.003))
    assert last_error is not None
    raise JobStateBusyError(f'Job-state database remained locked after bounded retries: {last_error}') from last_error


def state_exists(job) -> bool:
    return Path(job.state_db).exists()


def _append_event(connection: sqlite3.Connection, event: str, *, revision: int | None = None, **details: object) -> None:
    connection.execute(
        'INSERT INTO event_log(revision, event, details_json, created_utc) VALUES (?, ?, ?, ?)',
        (revision, event, json.dumps(details, ensure_ascii=False, sort_keys=True), _utc_now()),
    )


def initialize(job, payload: dict, *, preserve_legacy: bool = True) -> dict:
    if state_exists(job):
        return load(job)
    Path(job.state_dir).mkdir(parents=True, exist_ok=True)
    if preserve_legacy and Path(job.manifest).exists() and not Path(job.legacy_manifest).exists():
        shutil.copy2(job.manifest, job.legacy_manifest)
    document = copy.deepcopy(payload)
    document['_state_revision'] = 0
    connection = _connect(job)
    try:
        connection.execute('BEGIN IMMEDIATE')
        connection.execute(
            'INSERT OR REPLACE INTO state_document(singleton, revision, payload_json, updated_utc) VALUES (1, 0, ?, ?)',
            (json.dumps(document, ensure_ascii=False, sort_keys=True), _utc_now()),
        )
        _append_event(connection, 'state-initialized', revision=0, migrated_legacy=bool(Path(job.legacy_manifest).exists()))
        connection.execute('COMMIT')
    except Exception:
        connection.execute('ROLLBACK')
        raise
    finally:
        connection.close()
    try:
        write_json(Path(job.manifest), document)
    except OSError:
        pass
    return document


def load(job) -> dict:
    quick_check(job)
    connection = _connect(job, create=False)
    try:
        row = connection.execute('SELECT revision, payload_json FROM state_document WHERE singleton = 1').fetchone()
    finally:
        connection.close()
    if row is None:
        raise JobStateIntegrityError('Job-state database is missing its state document.')
    try:
        payload = json.loads(row['payload_json'])
    except (TypeError, json.JSONDecodeError) as exc:
        raise JobStateIntegrityError('Job-state payload JSON is corrupt inside SQLite.') from exc
    if not isinstance(payload, dict):
        raise JobStateIntegrityError('Job-state payload must be an object.')
    payload['_state_revision'] = int(row['revision'])
    return payload


def save(job, payload: dict, *, event: str = 'state-saved') -> int:
    if not state_exists(job):
        initialize(job, payload)
    expected_revision = payload.get('_state_revision')

    def action() -> int:
        connection = _connect(job, create=False)
        try:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT revision FROM state_document WHERE singleton = 1').fetchone()
            if row is None:
                raise JobStateIntegrityError('Job-state database is missing its state document.')
            current = int(row['revision'])
            if expected_revision is not None and int(expected_revision) != current:
                raise StaleStateRevisionError(f'Stale state revision: expected {expected_revision}, current {current}')
            revision = current + 1
            document = copy.deepcopy(payload)
            document['_state_revision'] = revision
            connection.execute(
                'UPDATE state_document SET revision = ?, payload_json = ?, updated_utc = ? WHERE singleton = 1',
                (revision, json.dumps(document, ensure_ascii=False, sort_keys=True), _utc_now()),
            )
            _append_event(connection, event, revision=revision)
            connection.execute('COMMIT')
            payload['_state_revision'] = revision
            return revision
        except Exception:
            try:
                connection.execute('ROLLBACK')
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    revision = int(_retry_transaction(action))
    try:
        write_json(Path(job.manifest), payload)
    except OSError:
        # JSON is a rebuildable human-readable snapshot. SQLite remains authoritative.
        pass
    return revision


def regenerate_snapshot(job) -> Path:
    payload = load(job)
    write_json(Path(job.manifest), payload)
    return Path(job.manifest)


def quarantine_corrupt_state(job) -> Path:
    source = Path(job.state_db)
    token = datetime.now().strftime('%Y%m%d_%H%M%S')
    destination = source.with_name(f'{source.stem}.corrupt.{token}{source.suffix}')
    shutil.copy2(source, destination)
    return destination


def acquire_lease(job, *, operation: str, pid: int, process_checker: Callable[[int], bool], stale_after_seconds: float = 600.0) -> str:
    token = uuid.uuid4().hex
    now = _utc_now()

    def action() -> str:
        connection = _connect(job)
        try:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT owner_token, pid, heartbeat_utc FROM job_lease WHERE singleton = 1').fetchone()
            if row is not None:
                other_pid = int(row['pid'])
                heartbeat_raw = str(row['heartbeat_utc'])
                try:
                    heartbeat = datetime.fromisoformat(heartbeat_raw)
                    age = max(0.0, (datetime.now(timezone.utc) - heartbeat).total_seconds())
                except ValueError:
                    age = stale_after_seconds + 1
                if process_checker(other_pid):
                    raise JobStateBusyError(f'Job is already owned by live process {other_pid}.')
            connection.execute(
                'INSERT OR REPLACE INTO job_lease(singleton, owner_token, pid, operation, acquired_utc, heartbeat_utc) VALUES (1, ?, ?, ?, ?, ?)',
                (token, int(pid), operation, now, now),
            )
            _append_event(connection, 'lease-acquired', owner_token=token, pid=int(pid), operation=operation)
            connection.execute('COMMIT')
            return token
        except Exception:
            try:
                connection.execute('ROLLBACK')
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    return str(_retry_transaction(action))


def heartbeat_lease(job, token: str) -> None:
    connection = _connect(job, create=False)
    try:
        connection.execute('UPDATE job_lease SET heartbeat_utc = ? WHERE singleton = 1 AND owner_token = ?', (_utc_now(), token))
    finally:
        connection.close()


def release_lease(job, token: str) -> None:
    if not state_exists(job):
        return
    connection = _connect(job, create=False)
    try:
        connection.execute('BEGIN IMMEDIATE')
        connection.execute('DELETE FROM job_lease WHERE singleton = 1 AND owner_token = ?', (token,))
        _append_event(connection, 'lease-released', owner_token=token)
        connection.execute('COMMIT')
    except Exception:
        try:
            connection.execute('ROLLBACK')
        except sqlite3.Error:
            pass
        raise
    finally:
        connection.close()
