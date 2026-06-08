from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from .manifest import load_manifest
from .models import JobPaths
from .utils import sha256_text

WORKFLOW_ORDER = (
    'prepare',
    'open_cleaned',
    'approve_text',
    'audition',
    'preview',
    'approve_preview',
    'synthesize',
    'retry_failed',
    'merge',
    'open_export',
)

@dataclass(frozen=True)
class WorkflowAction:
    state: str
    reason: str = ''


def _proofread_approved(job: JobPaths, manifest: dict) -> bool:
    if not job.proofread.exists():
        return False
    actual = sha256_text(job.proofread.read_text(encoding='utf-8'))
    return manifest.get('gates', {}).get('proofread', {}).get('approved_sha256') == actual


def _preview_approved(manifest: dict) -> bool:
    preview = manifest.get('gates', {}).get('preview', {})
    first = (manifest.get('parts') or [{}])[0]
    signature = manifest.get('audio', {}).get('signature')
    return bool(
        signature
        and preview.get('approved_audio_signature') == signature
        and preview.get('approved_part_sha256') == first.get('sha256')
    )


def _completed(manifest: dict) -> tuple[int, int]:
    return len(manifest.get('audio', {}).get('completed', {})), len(manifest.get('parts', []))


def derive_workflow_state(job: JobPaths | None, *, source_selected: bool, running_label: str | None = None) -> dict[str, WorkflowAction]:
    """Derive workflow presentation from authoritative job state, never click history."""
    actions = {key: WorkflowAction('blocked') for key in WORKFLOW_ORDER}
    if job is None or not job.manifest.exists():
        actions['prepare'] = WorkflowAction('next' if source_selected else 'blocked', 'Select a source book first.' if not source_selected else '')
        return _overlay_running(actions, running_label)

    manifest = load_manifest(job)
    prepared = job.proofread.exists() and bool(manifest.get('parts'))
    proofread_ok = _proofread_approved(job, manifest)
    preview_ok = _preview_approved(manifest)
    completed_count, total_parts = _completed(manifest)
    failures = bool(manifest.get('audio', {}).get('failures'))
    all_audio = bool(total_parts and completed_count == total_parts and not failures)
    export_verified = manifest.get('export', {}).get('status') == 'verified'
    merged = bool(manifest.get('merge', {}).get('output_runtime_only'))
    cleanup_analysis = manifest.get('cleanup', {}).get('analysis', {})
    cleanup_needed = any(
        isinstance(value, dict) and value.get('status') in {'recommended', 'review'} and int(value.get('count', 0) or 0) > 0
        for value in cleanup_analysis.values()
    )

    actions['prepare'] = WorkflowAction('completed' if prepared else 'next')
    if prepared:
        actions['open_cleaned'] = WorkflowAction('completed' if proofread_ok else 'next')
        actions['approve_text'] = WorkflowAction('completed' if proofread_ok else 'next')
    if proofread_ok:
        actions['audition'] = WorkflowAction('optional')
        part_one_done = '1' in manifest.get('audio', {}).get('completed', {})
        actions['preview'] = WorkflowAction('completed' if part_one_done else 'next')
        actions['approve_preview'] = WorkflowAction('completed' if preview_ok else ('next' if part_one_done else 'blocked'))
    if preview_ok:
        if failures:
            actions['retry_failed'] = WorkflowAction('failed')
            actions['synthesize'] = WorkflowAction('optional')
        elif all_audio:
            actions['synthesize'] = WorkflowAction('completed')
        else:
            actions['synthesize'] = WorkflowAction('next')
            actions['retry_failed'] = WorkflowAction('blocked')
    if all_audio:
        actions['merge'] = WorkflowAction('completed' if merged else 'next')
        actions['open_export'] = WorkflowAction('next' if export_verified else 'blocked')
    if merged:
        actions['open_export'] = WorkflowAction('next' if export_verified else 'blocked')
    # Cleanup is displayed in the Text process module, not the numbered primary chain.
    actions['cleanup_all'] = WorkflowAction('optional' if prepared and cleanup_needed else ('completed' if prepared else 'blocked'))
    return _overlay_running(actions, running_label)


def _overlay_running(actions: Mapping[str, WorkflowAction], running_label: str | None) -> dict[str, WorkflowAction]:
    result = dict(actions)
    if not running_label:
        return result
    label = running_label.lower()
    mapping = {
        'prepare text': 'prepare',
        'apply all recommended cleanup': 'cleanup_all',
        'apply cleanup': 'cleanup_all',
        'approve reviewed text': 'approve_text',
        'audition voice': 'audition',
        'preview part 1': 'preview',
        'approve part 1': 'approve_preview',
        'synthesize': 'synthesize',
        'resume synthesis': 'synthesize',
        'retry failed': 'retry_failed',
        'merge mp3': 'merge',
        'automatic legacy export': 'open_export',
    }
    for needle, key in mapping.items():
        if needle in label:
            result[key] = WorkflowAction('running')
            break
    return result
