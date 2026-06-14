from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

OCR_BORDER_NEUTRAL = '#D8D8D8'
OCR_BORDER_REQUIRED = '#425066'
OCR_BORDER_COMPLETE = '#2D7A4A'
OCR_BUTTON_DISABLED = '#D8D8D8'
OCR_BUTTON_NORMAL = '#F2ECDE'
OCR_BUTTON_NEXT = '#A8362C'
OCR_BUTTON_OPTIONAL = '#D6ECF0'
OCR_BUTTON_FAILED = '#B23A2E'


@dataclass(frozen=True)
class OCRUIPlan:
    state: str
    border: str
    banner: str
    roles: Mapping[str, str]


def derive_ocr_ui_plan(
    *,
    source_selected: bool,
    analysis_status: str | None,
    provider_available: bool,
    preview_ready: bool,
    output_ready: bool,
    operation: str | None,
    paused: bool = False,
) -> OCRUIPlan:
    '''Return the single authoritative OCR workflow state for the GUI.'''
    roles = {
        'analyze': 'blocked', 'preview': 'blocked', 'run': 'blocked',
        'advanced': 'blocked', 'output': 'blocked', 'prepare': 'blocked',
        'pause': 'blocked', 'resume': 'blocked', 'cancel': 'blocked',
    }
    if not source_selected:
        return OCRUIPlan('NO_SOURCE', OCR_BORDER_NEUTRAL, 'Select a book source.', roles)
    if operation == 'preview':
        roles.update({'cancel': 'optional'})
        return OCRUIPlan('OCR_PREVIEW_RUNNING', OCR_BORDER_REQUIRED, 'Preview OCR sample is running.', roles)
    if operation == 'full':
        roles.update({'cancel': 'optional'})
        if paused:
            roles.update({'resume': 'next'})
            return OCRUIPlan('OCR_FULL_PAUSED', OCR_BORDER_REQUIRED, 'Full OCR is paused. Completed checkpoints are preserved.', roles)
        roles.update({'pause': 'optional'})
        return OCRUIPlan('OCR_FULL_RUNNING', OCR_BORDER_REQUIRED, 'Full OCR is running. Completed checkpoints are preserved.', roles)
    if output_ready:
        roles.update({'preview': 'optional', 'output': 'normal', 'prepare': 'next', 'advanced': 'normal'})
        return OCRUIPlan('OCR_FULL_COMPLETED', OCR_BORDER_COMPLETE, 'OCR completed. Next step: Prepare text.', roles)
    if analysis_status is None:
        roles.update({'analyze': 'next'})
        return OCRUIPlan('SOURCE_SELECTED_PENDING_ANALYSIS', OCR_BORDER_NEUTRAL, 'Next step: Analyze book source.', roles)
    if analysis_status in {'not-needed', 'not-applicable'}:
        roles.update({'prepare': 'next'})
        return OCRUIPlan('TEXT_LAYER_READY', OCR_BORDER_NEUTRAL, 'Usable native text detected. OCR is not required. Next step: Prepare text.', roles)
    if analysis_status == 'required':
        if not provider_available:
            roles.update({'advanced': 'normal'})
            return OCRUIPlan('OCR_FOUNDATION_REQUIRED', OCR_BORDER_REQUIRED, 'OCR is required, but the local OCR foundation is unavailable. Open Advanced and run repair.', roles)
        if preview_ready:
            roles.update({'preview': 'optional', 'run': 'next', 'advanced': 'normal', 'output': 'normal'})
            return OCRUIPlan('OCR_PREVIEW_READY_FOR_CONFIRMATION', OCR_BORDER_REQUIRED, 'OCR sample is ready. Review the sample, then run full OCR.', roles)
        roles.update({'preview': 'next', 'run': 'optional', 'advanced': 'normal'})
        return OCRUIPlan('OCR_REQUIRED_PENDING_PREVIEW', OCR_BORDER_REQUIRED, 'Image-only PDF detected. Preview a 3-page OCR sample before processing the full book.', roles)
    roles.update({'analyze': 'next'})
    return OCRUIPlan('SOURCE_SELECTED_PENDING_ANALYSIS', OCR_BORDER_NEUTRAL, 'Next step: Analyze book source.', roles)


def format_seconds(value: float | int | None) -> str:
    if value is None:
        return 'calculating'
    total = max(0, int(float(value)))
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes:02d}:{seconds:02d}'


def ocr_results_dir(export_root: Path, source: Path) -> Path:
    '''Return a stable user-facing OCR results folder below Export root.'''
    from .utils import sanitize_filename
    return Path(export_root) / sanitize_filename(Path(source).stem, 'book') / 'OCR'


def provider_display_label(provider_id: str, *, recommended_provider: str | None = None, labels: Mapping[str, str] | None = None) -> str:
    label = (labels or {}).get(provider_id, provider_id)
    return f'{label} · recommended' if provider_id == recommended_provider and 'recommended' not in label.lower() else label
