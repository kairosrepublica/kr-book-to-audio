from __future__ import annotations
from dataclasses import dataclass, field
from typing import Mapping

KR_BLACK = '#0A0A0A'
KR_WHITE = '#FFFFFF'
KR_CHARCOAL = '#1F1F1F'
KR_SLATE = '#4A4A4A'
KR_STONE = '#8A8A8A'
KR_MIST = '#D8D8D8'
KR_PAPER_WARM = '#F4F3EF'
KR_PAPER_MANUSCRIPT = '#EFE9DB'
KR_PAPER_GAO = '#F2ECDE'
KR_VERMILLION_DARK = '#7C2520'
KR_VERMILLION = '#A8362C'
KR_VERMILLION_LIGHT = '#C45648'
KR_ZHE_SHI = '#845A33'
KR_DAI_LAN = '#425066'
KR_XIANG_SE = '#F0C239'
KR_YUE_BAI = '#D6ECF0'
KR_SUCCESS = '#2D7A4A'
KR_WARNING = '#C18A2E'
KR_ERROR = '#B23A2E'
KR_INFO = '#2D5B7A'

DIGITAL_UI_ALLOWED = {
    KR_BLACK, KR_WHITE, KR_CHARCOAL, KR_SLATE, KR_STONE, KR_MIST,
    KR_PAPER_WARM, KR_PAPER_MANUSCRIPT, KR_PAPER_GAO,
    KR_VERMILLION_DARK, KR_VERMILLION, KR_VERMILLION_LIGHT,
    KR_ZHE_SHI, KR_DAI_LAN, KR_XIANG_SE, KR_YUE_BAI,
    KR_SUCCESS, KR_WARNING, KR_ERROR, KR_INFO,
}
DIGITAL_UI_FORBIDDEN = {'#A8925A', '#FDECEC', '#EEF8F0', '#D6ECF0'}


def clamp_percent(value: float | int | None) -> float:
    try:
        return max(0.0, min(100.0, float(value or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def percent(completed: int, total: int) -> float:
    return clamp_percent((float(completed) / float(total) * 100.0) if total else 0.0)


@dataclass
class OCRPageState:
    page: int
    state: str = 'Pending'
    local_model: str = ''
    elapsed_seconds: float = 0.0
    attempts: int = 0


@dataclass
class OcrProgressSnapshot:
    mode: str = 'idle'
    total_pdf_pages: int = 0
    completed_pdf_pages: int = 0
    current_pdf_page: int = 0
    current_page_phase: str = ''
    current_page_elapsed: float = 0.0
    overall_elapsed: float = 0.0
    estimated_remaining: float | None = None
    actual_local_model: str = ''
    offline_enforced: bool = True
    current_attempt: int = 0
    attempts_total: int = 0
    pages: dict[int, OCRPageState] = field(default_factory=dict)

    @property
    def overall_percent(self) -> float:
        return percent(self.completed_pdf_pages, self.total_pdf_pages)

    def update(self, payload: Mapping[str, object], *, mode: str) -> 'OcrProgressSnapshot':
        self.mode = mode
        self.total_pdf_pages = int(payload.get('total_pages') or self.total_pdf_pages or 0)
        self.completed_pdf_pages = int(payload.get('completed_pages') or self.completed_pdf_pages or 0)
        self.current_pdf_page = int(payload.get('page') or self.current_pdf_page or 0)
        self.current_page_phase = str(payload.get('phase') or payload.get('state') or self.current_page_phase or '')
        self.current_page_elapsed = float(payload.get('page_elapsed_seconds') or payload.get('elapsed_seconds') or self.current_page_elapsed or 0.0)
        self.overall_elapsed = float(payload.get('elapsed_seconds') or self.overall_elapsed or 0.0)
        estimate = payload.get('estimated_remaining_seconds')
        self.estimated_remaining = float(estimate) if estimate is not None else self.estimated_remaining
        self.actual_local_model = str(payload.get('attempt_label') or payload.get('actual_provider') or payload.get('provider_id') or self.actual_local_model or '')
        self.offline_enforced = str(payload.get('offline_mode') or 'ENFORCED').upper() == 'ENFORCED'
        self.current_attempt = int(payload.get('attempt') or self.current_attempt or 0)
        self.attempts_total = int(payload.get('attempts_total') or self.attempts_total or 0)
        state = str(payload.get('state') or '')
        page = self.current_pdf_page
        if page > 0:
            current = self.pages.setdefault(page, OCRPageState(page))
            current.local_model = self.actual_local_model
            current.elapsed_seconds = self.current_page_elapsed
            current.attempts = max(current.attempts, self.current_attempt)
            if state in {'ocr-page-completed', 'ocr-page-recognized', 'ocr-page-reused'}:
                current.state = 'Completed'
            elif state == 'ocr-page-failed-continued':
                current.state = 'Failed'
            elif state in {'ocr-worker-started', 'ocr-worker-heartbeat', 'ocr-page-attempt', 'ocr-page-started'}:
                current.state = 'Recognizing'
            elif state == 'ocr-page-fallback':
                current.state = 'Fallback'
        return self
