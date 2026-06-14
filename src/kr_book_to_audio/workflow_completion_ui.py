from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping

COLOR_DISABLED = '#D8D8D8'
COLOR_NORMAL = '#F2ECDE'
COLOR_NEXT = '#A8362C'
COLOR_OPTIONAL = '#D6ECF0'
COLOR_APPROVE = '#2D7A4A'
COLOR_REJECT = '#B23A2E'


@dataclass(frozen=True)
class CleanupActionPlan:
    roles: Mapping[str, str]
    apply_all_enabled: bool


@dataclass(frozen=True)
class AudioActionPlan:
    roles: Mapping[str, str]
    reload_role: str
    settings_locked: bool
    banner: str


def derive_cleanup_action_plan(analysis: Mapping[str, object] | None, *, available: bool = True) -> CleanupActionPlan:
    if not available:
        return CleanupActionPlan(roles={'cleanup_junk': 'blocked', 'cleanup_datetime': 'blocked'}, apply_all_enabled=False)
    payload = analysis or {}
    junk = payload.get('repeated_headers_and_junk', {}) if isinstance(payload, Mapping) else {}
    dates = payload.get('metadata_datetime_tags', {}) if isinstance(payload, Mapping) else {}
    junk_status = str(junk.get('status', 'not-analyzed')) if isinstance(junk, Mapping) else 'not-analyzed'
    date_status = str(dates.get('status', 'not-analyzed')) if isinstance(dates, Mapping) else 'not-analyzed'
    recommended = {
        'cleanup_junk': junk_status == 'recommended',
        'cleanup_datetime': date_status == 'recommended',
    }
    roles = {key: ('recommended' if value else 'normal') for key, value in recommended.items()}
    return CleanupActionPlan(roles=roles, apply_all_enabled=any(recommended.values()))


def derive_audio_action_plan(
    *,
    source_selected: bool,
    job_ready: bool,
    proofread_approved: bool,
    parts_total: int,
    part1_ready: bool,
    preview_approved: bool,
    all_parts_ready: bool,
    export_verified: bool,
    failed_parts: bool,
    running: bool,
    settings_locked: bool,
) -> AudioActionPlan:
    roles = {
        'preview': 'blocked',
        'reject_preview': 'blocked',
        'approve_preview': 'blocked',
        'synthesize': 'blocked',
        'retry_failed': 'blocked',
        'merge': 'blocked',
        'open_export': 'blocked',
    }
    reload_role = 'optional' if source_selected else 'blocked'
    if running:
        return AudioActionPlan(roles, reload_role='blocked', settings_locked=settings_locked, banner='A workflow operation is running.')
    if not job_ready:
        return AudioActionPlan(roles, reload_role=reload_role, settings_locked=False, banner='Prepare text before previewing Part 1.')
    if not proofread_approved:
        return AudioActionPlan(roles, reload_role=reload_role, settings_locked=False, banner='Approve reviewed text before Preview Part 1.')
    if export_verified:
        roles['open_export'] = 'next'
        roles['preview'] = 'completed'
        roles['approve_preview'] = 'completed'
        if parts_total <= 1:
            roles['synthesize'] = 'skipped'
            roles['merge'] = 'skipped'
            banner = 'Single-Part export completed. Open the final export folder.'
        else:
            roles['synthesize'] = 'completed'
            roles['merge'] = 'completed'
            banner = 'Export completed. Open the final export folder.'
        return AudioActionPlan(roles, reload_role='optional', settings_locked=settings_locked, banner=banner)
    if not part1_ready:
        roles['preview'] = 'next'
        return AudioActionPlan(roles, reload_role=reload_role, settings_locked=False, banner='Next step: Preview Part 1.')
    roles['preview'] = 'optional'
    roles['reject_preview'] = 'reject'
    if not preview_approved:
        roles['approve_preview'] = 'approve'
        return AudioActionPlan(roles, reload_role='next', settings_locked=True, banner='Review Part 1. Approve, reject or reload the current book.')
    roles['approve_preview'] = 'completed'
    if parts_total <= 1:
        roles['synthesize'] = 'skipped'
        roles['merge'] = 'skipped'
        return AudioActionPlan(roles, reload_role='optional', settings_locked=True, banner='Single-Part book approved. Final export should complete automatically.')
    if failed_parts:
        roles['retry_failed'] = 'next'
        return AudioActionPlan(roles, reload_role='optional', settings_locked=True, banner='Retry failed Parts before merging.')
    if not all_parts_ready:
        roles['synthesize'] = 'next'
        return AudioActionPlan(roles, reload_role='optional', settings_locked=True, banner='Next step: Synthesize all remaining Parts.')
    roles['synthesize'] = 'completed'
    roles['merge'] = 'next'
    return AudioActionPlan(roles, reload_role='optional', settings_locked=True, banner='Next step: Merge MP3 and finalize export.')


def single_part_export_receipt(*, parts_total: int, source_part: int = 1) -> dict[str, object]:
    enabled = int(parts_total) == 1
    return {
        'single_part_direct_export': enabled,
        'synthesize_all_skipped': enabled,
        'merge_ui_skipped': enabled,
        'source_part': int(source_part),
    }
