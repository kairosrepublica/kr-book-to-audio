from __future__ import annotations
from pathlib import Path
from typing import Any, Callable
import json
from .audio import reconcile_audio_state, validate_mp3
from .history import rebuild_history
from .manifest import load_manifest
from .models import JobPaths
from .utils import append_job_log, process_is_alive, recover_stale_lock


def detect_interrupted_job(job: JobPaths, *, process_checker: Callable[[int], bool] = process_is_alive) -> bool:
    if not job.manifest.exists():
        return False
    manifest = load_manifest(job)
    execution = manifest.get('execution', {})
    if execution.get('status') != 'running':
        return bool(execution.get('resume_required', False))
    pid = execution.get('pid')
    if isinstance(pid, int) and process_checker(pid):
        return False
    from .execution import mark_interrupted
    mark_interrupted(job, manifest, reason='previous-process-ended-unexpectedly')
    recover_stale_lock(job, process_checker=process_checker)
    return True


def recover_job(job: JobPaths, *, validator: Callable[[Path], dict] = validate_mp3, process_checker: Callable[[int], bool] = process_is_alive) -> dict[str, Any]:
    lock_path = job.work / '.operation.lock'
    lock_existed_before = lock_path.exists()
    interrupted = detect_interrupted_job(job, process_checker=process_checker)
    stale = recover_stale_lock(job, process_checker=process_checker)
    stale_removed = bool(stale.get('removed')) or (lock_existed_before and not lock_path.exists())
    report = reconcile_audio_state(job, validator=validator)
    manifest = load_manifest(job)
    append_job_log(job, 'job-recovered', interrupted=interrupted, stale_lock=stale_removed, report=report)
    return {
        'interrupted': interrupted,
        'stale_lock_removed': stale_removed,
        'next_part': report.get('next_part'),
        **report,
        'status': manifest.get('execution', {}).get('status'),
    }


def scan_and_recover_jobs(work_root: Path, *, process_checker: Callable[[int], bool] = process_is_alive) -> list[dict[str, Any]]:
    work_root = Path(work_root)
    reports: list[dict[str, Any]] = []
    if not work_root.exists():
        rebuild_history(work_root)
        return reports
    for manifest_path in work_root.glob('*/_work/job_manifest.json'):
        job = JobPaths.from_root(manifest_path.parent.parent)
        try:
            if detect_interrupted_job(job, process_checker=process_checker):
                reports.append({'job_root': str(job.root), 'recovered': True})
        except Exception as exc:
            reports.append({'job_root': str(job.root), 'recovered': False, 'error': f'{type(exc).__name__}: {exc}'})
    rebuild_history(work_root)
    return reports
