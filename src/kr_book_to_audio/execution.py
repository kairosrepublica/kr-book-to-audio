from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import os
from .manifest import ensure_manifest_defaults, save_manifest
from .models import JobPaths
from .utils import append_job_log


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def begin_execution(job: JobPaths, manifest: dict[str, Any], operation: str, *, current_part: int | None = None, last_step: str = 'started') -> None:
    ensure_manifest_defaults(manifest)
    execution = manifest['execution']
    execution.update({
        'status': 'running',
        'last_operation': operation,
        'last_step': last_step,
        'current_part': current_part,
        'current_part_state': 'running' if current_part is not None else None,
        'pid': os.getpid(),
        'operation_started_utc': _utc_now(),
        'heartbeat_utc': _utc_now(),
        'interrupted_detected_utc': None,
        'resume_required': False,
    })
    save_manifest(job, manifest)
    append_job_log(job, 'execution-started', operation=operation, current_part=current_part)


def checkpoint_execution(job: JobPaths, manifest: dict[str, Any], *, last_step: str, current_part: int | None = None, current_part_state: str | None = None, last_completed_part: int | None = None) -> None:
    ensure_manifest_defaults(manifest)
    execution = manifest['execution']
    execution['heartbeat_utc'] = _utc_now()
    execution['last_step'] = last_step
    if current_part is not None:
        execution['current_part'] = current_part
    if current_part_state is not None:
        execution['current_part_state'] = current_part_state
    if last_completed_part is not None:
        execution['last_completed_part'] = last_completed_part
    save_manifest(job, manifest)


def finish_execution(job: JobPaths, manifest: dict[str, Any], *, status: str = 'idle', last_step: str = 'finished') -> None:
    ensure_manifest_defaults(manifest)
    execution = manifest['execution']
    execution.update({
        'status': status,
        'last_step': last_step,
        'current_part': None,
        'current_part_state': None,
        'pid': None,
        'heartbeat_utc': _utc_now(),
        'resume_required': status in {'interrupted', 'failed', 'completed-with-failures'},
    })
    save_manifest(job, manifest)
    append_job_log(job, 'execution-finished', status=status, last_step=last_step)


def mark_interrupted(job: JobPaths, manifest: dict[str, Any], *, reason: str) -> None:
    ensure_manifest_defaults(manifest)
    execution = manifest['execution']
    execution.update({
        'status': 'interrupted',
        'last_step': 'interrupted',
        'pid': None,
        'heartbeat_utc': _utc_now(),
        'interrupted_detected_utc': _utc_now(),
        'resume_required': True,
        'interruption_reason': reason,
    })
    save_manifest(job, manifest)
    append_job_log(job, 'execution-interrupted', reason=reason, current_part=execution.get('current_part'))
