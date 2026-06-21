from __future__ import annotations
from pathlib import Path
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from .audio import approve_legacy_resume_controls, approve_preview, audio_signature, audition_sample, generate_resume_voice_check, merge_parts, recover_speech_controls, retry_failed_parts, speech_controls, synthesize_parts
from .config import DEFAULT_KEEP_AWAKE, DEFAULT_PITCH, DEFAULT_PROCESSING_PROFILE, DEFAULT_RATE, DEFAULT_TTS_ENGINE, DEFAULT_VOICE, DEFAULT_VOLUME, default_export_root, load_config, local_work_root, save_config
from .manifest import load_manifest, save_manifest
from .history import display_status, format_last_active, list_recent_jobs, list_resumable_jobs, rebuild_history, remove_from_history
from .export import export_is_verified, finalize_export
from .diagnostics import diagnostics_root, export_diagnostic_zip, export_prejob_ocr_diagnostic_zip
from .durable_io import replace_with_retry
from .recovery import recover_job, scan_and_recover_jobs
from .models import JobPaths
from .ocr import OCRAnalysis, OCRControl, analyze_source, preview_sample_ocr, retry_failed_ocr_pages, run_recommended_ocr
from .local_ocr import install_or_repair_foundation, local_ocr_foundation
from .pipeline import approve_proofread_and_rebuild, apply_cleanup_and_rebuild, job_status, prepare_job
from .providers import OCR_PROVIDER_SPECS, enabled_tts_specs
from .subprocess_utils import process_trace
from .workflow_state import derive_workflow_state
from .ocr_workflow_ui import OCR_BUTTON_DISABLED, OCR_BUTTON_FAILED, OCR_BUTTON_NEXT, OCR_BUTTON_NORMAL, OCR_BUTTON_OPTIONAL, derive_ocr_ui_plan, format_seconds as format_ocr_seconds, ocr_results_dir, provider_display_label
from .workflow_completion_ui import COLOR_APPROVE, COLOR_DISABLED, COLOR_NEXT, COLOR_NORMAL, COLOR_OPTIONAL, COLOR_REJECT, derive_audio_action_plan, derive_cleanup_action_plan, single_part_export_receipt
from .utils import append_job_log
from .voices import filter_voices, load_voice_cache, refresh_voice_cache
from .providers import get_tts_provider
from .edge_voice_samples import EdgeSampleCache
from .ui_v295 import KR_CHARCOAL, KR_DAI_LAN, KR_ERROR, KR_MIST, KR_PAPER_GAO, KR_PAPER_WARM, KR_SUCCESS, KR_WARNING, KR_WHITE, KR_XIANG_SE, KR_YUE_BAI, OcrProgressSnapshot

PROFILE_LABELS = {
    'Auto detect · recommended': 'auto',
    'Chinese optimized': 'chinese',
    'English optimized': 'english',
    'Mixed Chinese-English': 'mixed',
    'General prose': 'general-prose',
}
PROFILE_BY_ID = {value: key for key, value in PROFILE_LABELS.items()}

PREPARE_MODE_LABELS = {
    'Auto smart cleanup': 'auto',
    'Minimal preserve layout': 'minimal',
    'Aggressive OCR cleanup': 'standard',
}
PREPARE_MODE_BY_ID = {value: key for key, value in PREPARE_MODE_LABELS.items()}
PREPARE_MODE_TOOLTIPS = {
    'auto': (
        'Default. Use this for most TXT, Markdown and DOCX books.\n'
        'It keeps high-confidence title, subtitle and article breaks, while still cleaning broken line wraps and extra spaces.'
    ),
    'minimal': (
        'Use only when the TXT has already been manually or AI-cleaned.\n'
        'It preserves paragraph breaks and layout as much as possible, so messy ebook line breaks can pass through.'
    ),
    'standard': (
        'Use for PDF/OCR/extracted text with many bad line breaks or spacing defects.\n'
        'It performs stronger reflow cleanup and may collapse intentional title spacing.'
    ),
}


BRANDING_DIR_PARTS = ('assets', 'branding')
BRANDING_ICO = 'kr_book_to_audio.ico'
BRANDING_PNG = 'ba_round_corner_small_square_fill-800.png'
WINDOWS_APP_ID = 'KairosRepublica.KRBookToAudio'
ANSI_ESCAPE_RE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


def sanitize_user_error(text: str) -> str:
    clean = ANSI_ESCAPE_RE.sub('', str(text or '')).strip()
    if 'PaddleOCR local worker failed' in clean:
        return 'OCR preview failed after recognition. The local OCR worker could not return its completion receipt. Diagnostics were preserved. Open diagnostics for technical details.'
    return clean


def branding_asset_path(filename: str) -> Path | None:
    """Resolve branding assets from source layouts and future frozen bundles."""
    roots: list[Path] = []
    frozen_root = getattr(sys, '_MEIPASS', None)
    if frozen_root:
        roots.append(Path(frozen_root))
    roots.extend([
        Path(__file__).resolve().parent,
        Path(__file__).resolve().parents[2],
    ])
    for root in roots:
        candidate = root.joinpath(*BRANDING_DIR_PARTS, filename)
        if candidate.exists():
            return candidate
    return None


def set_windows_app_id() -> bool:
    """Assign a stable Windows app identity when the native API is available."""
    if os.name != 'nt':
        return False
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
        return True
    except (AttributeError, OSError):
        return False


def open_in_file_manager(path: Path, *, select_file: bool = False) -> None:
    """Open an existing directory, or reveal an existing file, without creating paths silently."""
    candidate = Path(path).expanduser()
    if not candidate.exists():
        raise RuntimeError(f'The selected path does not exist yet: {candidate}')
    if candidate.is_file():
        if os.name == 'nt' and select_file:
            subprocess.Popen(['explorer', '/select,', str(candidate.resolve())])
        else:
            folder = candidate.resolve().parent
            os.startfile(folder) if os.name == 'nt' else subprocess.Popen(['xdg-open', str(folder)])
        return
    os.startfile(candidate) if os.name == 'nt' else subprocess.Popen(['xdg-open', str(candidate)])


def apply_window_icon(root: tk.Tk, *, resolver=branding_asset_path, image_loader=None) -> bool:
    """Apply the BA icon without blocking startup when an optional asset is missing."""
    configured = False
    ico = resolver(BRANDING_ICO)
    if ico:
        try:
            root.iconbitmap(default=str(ico))
            configured = True
        except (tk.TclError, OSError):
            pass
    png = resolver(BRANDING_PNG)
    if png:
        try:
            loader = image_loader or (lambda path: tk.PhotoImage(file=str(path)))
            image = loader(png)
            root.iconphoto(True, image)
            root._kr_book_to_audio_icon = image
            configured = True
        except (tk.TclError, OSError):
            pass
    return configured


def manifest_completed(job: JobPaths) -> set[str]:
    return set(load_manifest(job).get('audio', {}).get('completed', {}))


class BusyGuard:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._label: str | None = None

    def start(self, label: str) -> bool:
        with self._lock:
            if self._label is not None:
                return False
            self._label = label
            return True

    def finish(self) -> None:
        with self._lock:
            self._label = None

    @property
    def label(self) -> str | None:
        with self._lock:
            return self._label


class LatestTelemetryMailbox:
    """Keep only the latest high-frequency Provider telemetry per active Part.

    Audio streaming can emit thousands of low-level chunk updates. GUI history does not
    need every chunk. Keeping a latest-only snapshot prevents unbounded queue growth
    while preserving truthful current status. Terminal Parts reject stale telemetry
    until a later retry explicitly reopens the Part.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: dict[int, dict[str, object]] = {}
        self._terminal: set[int] = set()

    def reopen(self, index: int) -> None:
        with self._lock:
            self._terminal.discard(int(index))
            self._latest.pop(int(index), None)

    def publish(self, payload: dict[str, object]) -> bool:
        index = int(payload.get('index') or 0)
        if index <= 0:
            return False
        with self._lock:
            if index in self._terminal:
                return False
            self._latest[index] = dict(payload)
            return True

    def mark_terminal(self, index: int) -> None:
        with self._lock:
            index = int(index)
            self._terminal.add(index)
            self._latest.pop(index, None)

    def take_latest(self, *, limit: int = 8) -> list[dict[str, object]]:
        with self._lock:
            indexes = sorted(self._latest)[:max(0, int(limit))]
            snapshots = [self._latest.pop(index) for index in indexes]
        return snapshots

    def pending_count(self) -> int:
        with self._lock:
            return len(self._latest)


CONTROL_EVENT_QUEUE_MAXSIZE = 2048
CONTROL_EVENTS_PER_DRAIN = 48
CONTROL_DRAIN_TIME_BUDGET_SECONDS = 0.010
TELEMETRY_SNAPSHOTS_PER_DRAIN = 8
GUI_DRAIN_INTERVAL_MS = 50


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str):
        self.widget = widget
        self.text = text
        self.window: tk.Toplevel | None = None
        self.after_id: str | None = None
        widget.bind('<Enter>', self._schedule, add='+')
        widget.bind('<Leave>', self._hide, add='+')
        widget.bind('<ButtonPress>', self._hide, add='+')

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self.after_id = self.widget.after(400, self._show)

    def _cancel(self) -> None:
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

    def _show(self) -> None:
        if self.window or not self.text:
            return
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f'+{x}+{y}')
        tk.Label(self.window, text=self.text, justify='left', relief='solid', borderwidth=1, padx=7, pady=5, wraplength=470).pack()

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self.window:
            self.window.destroy()
            self.window = None


def add_help(parent: tk.Widget, text: str, **grid_options) -> ttk.Label:
    label = ttk.Label(parent, text='ⓘ', cursor='question_arrow')
    label.grid(**grid_options)
    Tooltip(label, text)
    return label


def add_triangle_help(parent: tk.Widget, text: str, **grid_options) -> ttk.Label:
    label = ttk.Label(parent, text='▸', cursor='question_arrow')
    label.grid(**grid_options)
    Tooltip(label, text)
    return label




DEFAULT_WINDOW_WIDTH = 1200
MIN_WINDOW_WIDTH = 1150
MIN_WINDOW_HEIGHT = 520
WINDOW_SAFE_WIDTH_MARGIN = 80
WINDOW_SAFE_HEIGHT_MARGIN = 120
LARGE_SCREEN_HEIGHT_THRESHOLD = 1870
LARGE_WINDOW_HEIGHT = 1870


def compute_window_geometry(screen_width: int, screen_height: int, saved: str | None = None) -> tuple[str, str]:
    """Return a deterministic visible initial geometry and responsive layout mode.

    Width is intentionally constrained for readability: the normal desktop starts
    at 1200 px and may never shrink below 1150 px. Screens narrower than that
    physical minimum cannot contain the full desktop shell without overflow.
    """
    screen_width = int(screen_width)
    screen_height = int(screen_height)
    max_visible_width = max(MIN_WINDOW_WIDTH, screen_width - WINDOW_SAFE_WIDTH_MARGIN)
    max_visible_height = max(MIN_WINDOW_HEIGHT, screen_height - WINDOW_SAFE_HEIGHT_MARGIN)
    width = min(DEFAULT_WINDOW_WIDTH, max_visible_width)
    if screen_height > LARGE_SCREEN_HEIGHT_THRESHOLD:
        mode = 'expanded'
        height = LARGE_WINDOW_HEIGHT
    elif screen_height >= 1000:
        mode = 'medium'
        height = max_visible_height
    else:
        mode = 'compact'
        height = max_visible_height
    if saved:
        import re
        match = re.match(r'^(\d+)x(\d+)', str(saved))
        if match:
            width = min(max(MIN_WINDOW_WIDTH, int(match.group(1))), max_visible_width)
            height_limit = LARGE_WINDOW_HEIGHT if screen_height > LARGE_SCREEN_HEIGHT_THRESHOLD else max_visible_height
            height = min(max(MIN_WINDOW_HEIGHT, int(match.group(2))), height_limit)
    return f'{width}x{height}', mode


def wheel_scroll_units(delta: int) -> int:
    """Translate Windows MouseWheel or touchpad delta into Canvas scroll units."""
    delta = int(delta or 0)
    if delta == 0:
        return 0
    magnitude = max(1, abs(delta) // 120)
    return -magnitude if delta > 0 else magnitude


def preserves_native_wheel(widget_class: str) -> bool:
    """Return True when an inner widget should retain its native wheel behavior."""
    return str(widget_class) in {'Text', 'Treeview', 'Listbox', 'TCombobox'}


def outer_scroll_enabled(window_height: int) -> bool:
    """Return True only while the physical visible outer shell is below the fixed threshold."""
    return int(window_height) < LARGE_WINDOW_HEIGHT


def visible_window_height_px(root: tk.Misc) -> int:
    """Return the visible top-level window height in physical screen pixels when Windows exposes it.

    Tk window geometry can be expressed in toolkit coordinates that do not reliably match a
    physical-pixel desktop contract under Windows display scaling. Desktop Window Manager
    extended frame bounds are returned in physical screen-space pixels and therefore govern
    the fixed-shell threshold. Other platforms retain the Tk fallback.
    """
    fallback = max(0, int(root.winfo_height()))
    if os.name != 'nt':
        return fallback
    try:
        import ctypes
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [
                ('left', wintypes.LONG),
                ('top', wintypes.LONG),
                ('right', wintypes.LONG),
                ('bottom', wintypes.LONG),
            ]

        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi
        hwnd = int(root.winfo_id())
        root_hwnd = int(user32.GetAncestor(hwnd, 2) or hwnd)  # GA_ROOT
        rect = RECT()
        result = int(dwmapi.DwmGetWindowAttribute(root_hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)))  # DWMWA_EXTENDED_FRAME_BOUNDS
        height = int(rect.bottom - rect.top)
        if result == 0 and height > 0:
            return height
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    return fallback


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title('KR Book To Audio 3.3')
        apply_window_icon(self.root)
        cfg = load_config()
        geometry, self.layout_mode = compute_window_geometry(self.root.winfo_screenwidth(), self.root.winfo_screenheight(), cfg.get('window_geometry_v231'))
        self.root.geometry(geometry)
        self.root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.events: queue.Queue[tuple] = queue.Queue(maxsize=CONTROL_EVENT_QUEUE_MAXSIZE)
        self.telemetry_mailbox = LatestTelemetryMailbox()
        self.job: JobPaths | None = None
        self.busy = BusyGuard()
        self.action_buttons: list[tk.Widget] = []
        self.workflow_buttons: dict[str, tk.Button] = {}
        self.workflow_base_labels: dict[str, str] = {}
        self.ui_actions_enabled = True
        self.part_states: dict[int, str] = {}
        self.current_index: int | None = None
        self.current_estimate = 0
        self.estimate_token = 0
        self.current_started_monotonic: float | None = None
        self.current_expected_seconds = 30.0
        self.runtime_seconds_per_char: list[float] = []
        self.logged_progress_buckets: dict[int, int] = {}
        self.provider_runtime: dict[str, object] = {}
        self._last_centered_part_status_index: int | None = None
        self._last_provider_log_signature = ''
        self._last_provider_log_at = 0.0
        self._last_provider_log_bytes_bucket = -1
        self.preview_playback_token = 0
        self.last_played_preview_token = 0
        self.speech_settings_locked = False
        self.speech_setting_widgets: list[tuple[tk.Widget, str]] = []
        self.cleanup_analysis: dict[str, object] = {}
        self.ocr_analysis: OCRAnalysis | None = None
        self.ocr_last_output_dir: Path | None = None
        self.ocr_preview_report: dict[str, object] | None = None
        self.ocr_operation_kind: str | None = None
        self.ocr_operation_started_monotonic: float | None = None
        self.ocr_progress_snapshot: dict[str, object] = {}
        self.ocr_v295_snapshot = OcrProgressSnapshot()
        self._last_ocr_log_state = ''
        self._last_ocr_heartbeat_at = 0.0
        self.ocr_progress_token = 0
        self.ocr_control: OCRControl | None = None
        self.ocr_paused = False
        self.ocr_source_before_output: Path | None = None
        self._suppress_source_trace = False
        self.source = tk.StringVar()
        self.source_folder = str(cfg.get('source_folder', Path.home()))
        self.work_root = tk.StringVar(value=cfg.get('work_root', str(local_work_root())))
        self.export_root = tk.StringVar(value=cfg.get('export_root', str(default_export_root())))
        self.dictionary = tk.StringVar(value=cfg.get('dictionary', ''))
        self.profile = tk.StringVar(value=PROFILE_BY_ID.get(str(cfg.get('processing_profile', DEFAULT_PROCESSING_PROFILE)), 'Auto detect · recommended'))
        configured_prepare_mode = str(cfg.get('prepare_layout_mode', 'auto'))
        if configured_prepare_mode not in PREPARE_MODE_BY_ID:
            configured_prepare_mode = 'auto'
        self.prepare_layout_mode = tk.StringVar(value=configured_prepare_mode)
        specs = enabled_tts_specs()
        self.tts_engine_labels = {spec.label: spec.provider_id for spec in specs}
        configured_tts_engine = str(cfg.get('tts_engine', 'edge-tts'))
        configured_tts_label = next(
            (label for label, provider_id in self.tts_engine_labels.items() if provider_id == configured_tts_engine),
            next(iter(self.tts_engine_labels), 'Microsoft Edge Online TTS · edge-tts'),
        )
        self.tts_engine = tk.StringVar(value=configured_tts_label)
        self.voice = tk.StringVar(value=cfg.get('voice', DEFAULT_VOICE))
        self.rate = tk.StringVar(value=cfg.get('rate', DEFAULT_RATE))
        self.pitch = tk.StringVar(value=cfg.get('pitch', DEFAULT_PITCH))
        self.volume = tk.StringVar(value=cfg.get('volume', DEFAULT_VOLUME))
        self.show_all_voices = tk.BooleanVar(value=bool(cfg.get('show_all_voices', False)))
        self.show_older_attempts = tk.BooleanVar(value=False)
        self.keep_awake = tk.BooleanVar(value=bool(cfg.get('keep_awake', DEFAULT_KEEP_AWAKE)))
        self.recent_by_iid: dict[str, dict] = {}
        self.voice_records = load_voice_cache(self._tts_engine_id())
        self.last_tts_engine_id = self._tts_engine_id()
        self.advanced_ocr_visible = False
        self.ocr_override = tk.StringVar(value='')
        self.ocr_provider_by_label: dict[str, str] = {}
        self._build()
        self.source.trace_add('write', self._source_changed)
        self.root.protocol('WM_DELETE_WINDOW', self._close)
        self._apply_voice_filter()
        for var in (self.voice, self.rate, self.pitch, self.volume, self.tts_engine):
            var.trace_add('write', self._voice_controls_changed)
        self.profile.trace_add('write', self._profile_changed)
        self.show_all_voices.trace_add('write', self._profile_changed)
        self.show_older_attempts.trace_add('write', lambda *_: self.refresh_recent_jobs())
        self.root.after(GUI_DRAIN_INTERVAL_MS, self._drain)
        self.root.after(250, self._startup_recovery)
        self._refresh_voices(background=True)


    def _close(self) -> None:
        try:
            cfg = load_config(); cfg['window_geometry_v231'] = self.root.geometry(); save_config(cfg)
        finally:
            self.root.destroy()

    def _source_changed(self, *_: object) -> None:
        if self._suppress_source_trace:
            return
        self.speech_settings_locked = False
        self._apply_speech_settings_lock()
        self.ocr_analysis = None
        self.ocr_preview_report = None
        self.ocr_last_output_dir = None
        self.ocr_source_before_output = None
        self.ocr_operation_kind = None
        self.ocr_control = None
        self.ocr_paused = False
        if hasattr(self, 'ocr_status'):
            self.ocr_status.config(text='Status: Not analyzed')
            self.ocr_reason.config(text='Next step: Analyze book source.')
            self._render_ocr_ui_state()
        self._render_workflow_state()

    def _ocr_provider_available(self) -> bool:
        if not self.ocr_analysis:
            return False
        provider = self._selected_ocr_provider()
        return bool(provider and provider != 'native-text')

    def _ocr_output_ready(self) -> bool:
        analysis = getattr(self, 'ocr_analysis', None)
        return bool(analysis is not None and str(getattr(analysis, 'status', '') or '') == 'completed')

    def _ocr_plan(self):
        return derive_ocr_ui_plan(
            source_selected=bool(self.source.get().strip()),
            analysis_status=self.ocr_analysis.status if self.ocr_analysis else None,
            provider_available=self._ocr_provider_available(),
            preview_ready=bool(self.ocr_preview_report),
            output_ready=self._ocr_output_ready() and bool(self.ocr_analysis and self.ocr_analysis.status == 'completed'),
            operation=self.ocr_operation_kind,
            paused=self.ocr_paused,
        )

    @staticmethod
    def _ocr_button_palette(role: str) -> tuple[str, str, str]:
        if role in {'next', 'running'}:
            return 'SystemHighlight', 'SystemHighlightText', 'normal' if role == 'next' else 'disabled'
        if role in {'optional', 'normal', 'failed'}:
            return 'SystemButtonFace', 'SystemButtonText', 'normal'
        return 'SystemButtonFace', 'SystemGrayText', 'disabled'

    def _render_ocr_ui_state(self) -> None:
        if not hasattr(self, 'ocr_buttons'):
            return
        plan = self._ocr_plan()
        source_selected = bool(self.source.get().strip())
        force_analyze = source_selected and getattr(self, 'ocr_analysis', None) is None and self.ocr_operation_kind is None
        self.ocr_flow_hint.config(text=plan.banner)
        for key, button in self.ocr_buttons.items():
            role = 'next' if key == 'analyze' and force_analyze else plan.roles.get(key, 'blocked')
            if role in {'next', 'running'}:
                bg, fg, state = 'SystemHighlight', 'SystemHighlightText', 'normal'
            elif role in {'normal', 'optional'}:
                bg, fg, state = 'SystemButtonFace', 'SystemButtonText', 'normal'
            else:
                bg, fg, state = 'SystemButtonFace', 'SystemGrayText', 'disabled'
            if not self.ui_actions_enabled and key not in {'pause','resume','cancel'}:
                state = 'disabled'
            if self.ocr_operation_kind is None and key in {'pause','resume','cancel'}:
                state = 'disabled'
            button.config(bg=bg, fg=fg, state=state, disabledforeground=fg, font=('TkDefaultFont',9,'bold') if role in {'next','running'} else ('TkDefaultFont',9))
        combo_state = 'readonly' if self.ui_actions_enabled and self.ocr_operation_kind is None and self.ocr_analysis and self.ocr_analysis.status == 'required' else 'disabled'
        self.ocr_override_combo.config(state=combo_state)

    def _update_ocr_action_state(self) -> None:
        self._render_ocr_ui_state()

    def _build(self) -> None:
        # V20_WORKFLOW_STATUS_SHELL: approved layout with one overall bar and one current-item bar.
        # V23_RELEASE_3_0_SHELL: minimum-height, persistent-window and reject-color contract.
        # V26_RUNTIME_CANCELLATION_OCR_PROGRESS_AND_SAVE_JOB_SHELL
        self.root.geometry('1580x1260')
        self.root.minsize(1480, 1260)
        self.shell = ttk.Frame(self.root, padding=12)
        self.shell.pack(fill='both', expand=True)
        self.viewport = self.shell
        self.canvas = tk.Canvas(self.shell, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.shell, orient='vertical')

        def button(parent, text, command, *, width=0):
            return tk.Button(parent, text=text, command=command, width=width, padx=8, pady=3)

        def card(parent, title, subtitle='', *, row=0, column=0, columnspan=1, rowspan=1, sticky='nsew', padx=0, pady=0):
            outer = ttk.Labelframe(parent, text=title, padding=8)
            outer.grid(row=row, column=column, columnspan=columnspan, rowspan=rowspan, sticky=sticky, padx=padx, pady=pady)
            if subtitle:
                ttk.Label(outer, text=subtitle).pack(anchor='w', pady=(0, 5))
            body = ttk.Frame(outer)
            body.pack(fill='both', expand=True)
            return outer, body

        content = ttk.Frame(self.shell)
        content.pack(fill='both', expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(5, weight=1)

        _, paths = card(content, 'Source and storage', row=0, column=0, pady=(0, 8))
        paths.columnconfigure(1, weight=1)
        rows = [
            ('Book', self.source, self._browse_source, self._open_source, self._set_source_folder_default),
            ('Local working root', self.work_root, self._browse_work, self._open_work_root, self._set_work_default),
            ('Export root', self.export_root, self._browse_export, self._open_export_root, self._set_export_default),
            ('Pronunciation dictionary', self.dictionary, self._browse_dict, self._open_dictionary, self._set_dictionary_default),
        ]
        for row, (name, variable, browse, open_path, set_default) in enumerate(rows):
            ttk.Label(paths, text=name).grid(row=row, column=0, sticky='w', padx=(0, 8), pady=3)
            ttk.Entry(paths, textvariable=variable).grid(row=row, column=1, sticky='ew', pady=3)
            ttk.Button(paths, text='Browse', command=browse).grid(row=row, column=2, padx=(7, 3), pady=3)
            ttk.Button(paths, text='Open', command=open_path).grid(row=row, column=3, padx=3, pady=3)
            ttk.Button(paths, text='Set as default', command=set_default).grid(row=row, column=4, padx=3, pady=3)

        upper = ttk.Frame(content)
        upper.grid(row=1, column=0, sticky='ew', pady=(0, 8))
        upper.columnconfigure(0, weight=2)
        upper.columnconfigure(1, weight=1)
        _, recent = card(upper, 'Resume interrupted or incomplete jobs', row=0, column=0, padx=(0, 4))
        self.recent_jobs = ttk.Treeview(recent, columns=('title', 'status', 'progress', 'last_active'), show='headings', height=4)
        for key, title, width in [('title','Book title',340), ('status','Status',145), ('progress','Progress',90), ('last_active','Last active',150)]:
            self.recent_jobs.heading(key, text=title); self.recent_jobs.column(key, width=width, anchor='w')
        self.recent_jobs.pack(fill='x')
        recent_buttons = ttk.Frame(recent); recent_buttons.pack(fill='x', pady=(7, 0))
        for name, method in [('Resume selected', self.resume_selected), ('Open output folder', self.open_selected_output), ('Remove from history', self.remove_selected_history), ('Refresh', self.refresh_recent_jobs), ('Advanced recovery', self.advanced_recovery)]:
            item = ttk.Button(recent_buttons, text=name, command=method); item.pack(side='left', padx=(0, 5)); self.action_buttons.append(item)
        ttk.Checkbutton(recent, text='Show older attempts', variable=self.show_older_attempts).pack(anchor='w', pady=(6, 0))

        _, workspace = card(upper, 'Current workspace', row=0, column=1, padx=(4, 0))
        self.reload_button = button(workspace, 'Reload book', self.reload_current_book)
        self.reload_button.pack(fill='x', pady=2); self.action_buttons.append(self.reload_button)
        self.edge_samples_button = button(workspace, 'Refresh voice samples', self.refresh_edge_voice_samples)
        self.edge_samples_button.pack(fill='x', pady=2); self.action_buttons.append(self.edge_samples_button)
        ttk.Checkbutton(workspace, text='Keep computer awake during OCR or TTS', variable=self.keep_awake).pack(anchor='w', pady=(7, 2))

        _, opts = card(content, 'Text and speech settings', row=2, column=0, pady=(0, 8))
        for col in (1, 3, 5): opts.columnconfigure(col, weight=1)
        ttk.Label(opts, text='Processing profile').grid(row=0, column=0, sticky='w', pady=3)
        self.profile_combo = ttk.Combobox(opts, textvariable=self.profile, values=list(PROFILE_LABELS), state='readonly', width=28)
        self.profile_combo.grid(row=0, column=1, sticky='ew', padx=(4, 14), pady=3)
        ttk.Label(opts, text='TTS engine').grid(row=0, column=2, sticky='w', pady=3)
        self.tts_engine_combo = ttk.Combobox(opts, textvariable=self.tts_engine, values=list(self.tts_engine_labels), state='readonly', width=38)
        self.tts_engine_combo.grid(row=0, column=3, sticky='ew', padx=(4, 14), pady=3)
        ttk.Label(opts, text='Voice').grid(row=0, column=4, sticky='w', pady=3)
        self.voice_combo = ttk.Combobox(opts, textvariable=self.voice, state='readonly', width=34)
        self.voice_combo.grid(row=0, column=5, sticky='ew', padx=(4, 4), pady=3)
        self.play_voice_button = button(opts, 'Play sample', self.audition)
        self.play_voice_button.grid(row=0, column=6, padx=(5, 0), pady=3)
        self.show_all_voices_button = ttk.Checkbutton(opts, text='Show all voices', variable=self.show_all_voices)
        self.show_all_voices_button.grid(row=1, column=0, sticky='w', pady=3)
        self.rate_slider_value = tk.IntVar(value=self._percent_text_to_int(self.rate.get()))
        self.volume_slider_value = tk.IntVar(value=self._percent_text_to_int(self.volume.get()))
        ttk.Label(opts, text='Rate').grid(row=1, column=1, sticky='e', padx=(4, 2))
        self.rate_scale = tk.Scale(opts, from_=-50, to=100, resolution=5, orient='horizontal', variable=self.rate_slider_value, command=self._rate_slider_changed, showvalue=True, length=210)
        self.rate_scale.grid(row=1, column=2, sticky='ew', padx=(2, 12))
        ttk.Label(opts, text='Pitch').grid(row=1, column=3, sticky='e', padx=(4, 2))
        self.pitch_entry = ttk.Entry(opts, textvariable=self.pitch, width=12); self.pitch_entry.grid(row=1, column=4, sticky='w', padx=(2, 12))
        ttk.Label(opts, text='Volume').grid(row=1, column=5, sticky='e', padx=(4, 2))
        self.volume_scale = tk.Scale(opts, from_=-100, to=100, resolution=5, orient='horizontal', variable=self.volume_slider_value, command=self._volume_slider_changed, showvalue=True, length=210)
        self.volume_scale.grid(row=1, column=6, sticky='ew', padx=(2, 0))
        self.speech_lock_hint = ttk.Label(opts, text=''); self.speech_lock_hint.grid(row=2, column=0, columnspan=7, sticky='w', pady=(3, 0))
        self.rate_entry = self.rate_scale; self.volume_entry = self.volume_scale
        self.refresh_voice_button = self.edge_samples_button
        self.speech_setting_widgets = [
            (self.profile_combo, 'readonly'), (self.tts_engine_combo, 'readonly'), (self.voice_combo, 'readonly'),
            (self.play_voice_button, 'normal'), (self.show_all_voices_button, 'normal'),
            (self.rate_scale, 'normal'), (self.pitch_entry, 'normal'), (self.volume_scale, 'normal'),
        ]
        self.action_buttons.append(self.play_voice_button)

        workflow = ttk.Frame(content)
        workflow.grid(row=3, column=0, sticky='ew', pady=(0, 8))
        for col in range(3): workflow.columnconfigure(col, weight=1, uniform='workflow')

        _, ocr = card(workflow, 'OCR', row=0, column=0, padx=(0, 4))
        self.ocr_border = ocr.master; self.ocr_accent = ttk.Frame(ocr)
        self.ocr_status = ttk.Label(ocr, text='Status: Not analyzed'); self.ocr_status.grid(row=0, column=0, columnspan=3, sticky='w')
        self.ocr_reason = ttk.Label(ocr, text='Select a book, then analyze text.', wraplength=390); self.ocr_reason.grid(row=1, column=0, columnspan=3, sticky='w', pady=(2, 5))
        self.ocr_flow_hint = ttk.Label(ocr, text='Select a book source.', wraplength=390); self.ocr_flow_hint.grid(row=2, column=0, columnspan=3, sticky='w', pady=(0, 5))
        self.ocr_override_combo = ttk.Combobox(ocr, textvariable=self.ocr_override, state='disabled', width=36); self.ocr_override_combo.grid(row=3, column=0, columnspan=3, sticky='ew', pady=(0, 5))
        self.ocr_buttons = {}
        for idx, (key, title, command) in enumerate([('analyze','Analyze text',self.analyze_ocr), ('preview','Preview 3-page OCR sample',self.preview_ocr), ('run','Run full OCR',self.run_ocr), ('output','Open OCR results',self.open_ocr_output_folder)]):
            item = button(ocr, title, command); item.grid(row=4 + idx // 2, column=idx % 2, sticky='ew', padx=(0 if idx % 2 == 0 else 3, 3 if idx % 2 == 0 else 0), pady=2); self.ocr_buttons[key] = item; self.action_buttons.append(item)
        self.ocr_pause_button = button(ocr, 'Pause OCR', self.pause_ocr); self.ocr_pause_button.grid(row=6,column=0,sticky='ew',pady=2)
        self.ocr_resume_button = button(ocr, 'Resume OCR', self.resume_ocr); self.ocr_resume_button.grid(row=6,column=1,sticky='ew',padx=3,pady=2)
        self.ocr_cancel_button = button(ocr, 'Cancel OCR', self.cancel_ocr); self.ocr_cancel_button.grid(row=7,column=0,sticky='ew',pady=2)
        self.ocr_advanced_button = button(ocr, 'Advanced', self.toggle_ocr_advanced); self.ocr_advanced_button.grid(row=7,column=1,sticky='ew',padx=3,pady=2)
        self.ocr_buttons.update({'pause':self.ocr_pause_button,'resume':self.ocr_resume_button,'cancel':self.ocr_cancel_button})
        self.ocr_advanced = ttk.Frame(ocr)
        self.ocr_install_button = button(self.ocr_advanced, 'Install / repair local OCR foundation', self.install_or_repair_ocr); self.ocr_install_button.grid(row=0,column=0,sticky='ew',pady=2)
        self.ocr_resource_button = button(self.ocr_advanced, 'Open OCR resource folder', self.open_ocr_resource_folder); self.ocr_resource_button.grid(row=0,column=1,sticky='ew',padx=3,pady=2)
        self.action_buttons.extend([self.ocr_install_button,self.ocr_resource_button]); ocr.columnconfigure(0,weight=1); ocr.columnconfigure(1,weight=1)

        _, text_process = card(workflow, 'Text process', row=0, column=1, padx=4)
        prepare_modes = ttk.Frame(text_process); prepare_modes.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 4)); prepare_modes.columnconfigure(1, weight=1)
        ttk.Label(prepare_modes, text='Prepare mode:').grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 2))
        for idx, (label, mode_id) in enumerate(PREPARE_MODE_LABELS.items(), start=1):
            rb = ttk.Radiobutton(prepare_modes, text=label, variable=self.prepare_layout_mode, value=mode_id)
            rb.grid(row=idx, column=0, sticky='w', pady=1)
            add_triangle_help(prepare_modes, PREPARE_MODE_TOOLTIPS[mode_id], row=idx, column=1, sticky='w', padx=(4, 0), pady=1)
        self._workflow_button(text_process, 'prepare', 'Prepare text', self.prepare, row=1, column=0)
        cleanup = ttk.Frame(text_process); cleanup.grid(row=2,column=0,columnspan=2,sticky='ew',pady=(6,3)); cleanup.columnconfigure(0,weight=1)
        self.cleanup_junk = ttk.Label(cleanup, text='Repeated headers and junk: Not analyzed'); self.cleanup_junk.grid(row=0,column=0,sticky='w',pady=2)
        self.cleanup_junk_button = button(cleanup, 'Apply cleanup', lambda: self.apply_cleanup('repeated-headers-and-junk')); self.cleanup_junk_button.grid(row=0,column=1,sticky='e',pady=2)
        self.cleanup_datetime = ttk.Label(cleanup, text='Metadata-like date/time tags: Not analyzed'); self.cleanup_datetime.grid(row=1,column=0,sticky='w',pady=2)
        self.cleanup_datetime_button = button(cleanup, 'Apply cleanup', lambda: self.apply_cleanup('metadata-date-time-tags')); self.cleanup_datetime_button.grid(row=1,column=1,sticky='e',pady=2)
        self.action_buttons.extend([self.cleanup_junk_button,self.cleanup_datetime_button])
        self.cleanup_all_button = button(cleanup, 'Apply all recommended cleanup', self.apply_all_cleanup)
        self.cleanup_all_button.grid(row=2,column=1,sticky='e',pady=2)
        self.workflow_buttons['cleanup_all'] = self.cleanup_all_button
        self.workflow_base_labels['cleanup_all'] = 'Apply all recommended cleanup'
        self.action_buttons.append(self.cleanup_all_button)
        self._workflow_button(text_process, 'open_cleaned', 'Open cleaned text', self.open_cleaned_text_and_advance, row=4, column=0)
        self._workflow_button(text_process, 'approve_text', 'Approve reviewed text', self.approve_proofread, row=4, column=1)
        text_process.columnconfigure(0,weight=1); text_process.columnconfigure(1,weight=1)

        _, audio = card(workflow, 'Audio process', row=0, column=2, padx=(4, 0))
        for idx, (key,title,command) in enumerate([('preview','Preview Part 1',self.preview),('reject_preview','Reject Part 1',self.reject_part_one),('approve_preview','Approve Part 1',self.approve_part_one),('synthesize','Synthesize all',self.synthesize),('retry_failed','Retry failed',self.retry_failed),('merge','Merge MP3',self.merge),('open_export','Open final export folder',self.open_current_export)]):
            self._workflow_button(audio, key, title, command, row=idx // 2, column=idx % 2)
        playback = ttk.Labelframe(audio, text='Part 1 playback', padding=5); playback.grid(row=4,column=0,columnspan=2,sticky='ew',pady=(6,2)); playback.columnconfigure(3,weight=1)
        self.audio_play_button = button(playback, 'Play', self.play_part_one_audio); self.audio_play_button.grid(row=0,column=0,padx=(0,3))
        self.audio_pause_button = button(playback, 'Pause', self.pause_audio_playback); self.audio_pause_button.grid(row=0,column=1,padx=3)
        self.audio_stop_button = button(playback, 'Stop', self.stop_audio_playback); self.audio_stop_button.grid(row=0,column=2,padx=3)
        self.audio_playback_volume = tk.IntVar(value=100)
        ttk.Label(playback, text='Volume').grid(row=0,column=3,sticky='e',padx=(8,2))
        self.audio_playback_volume_scale = tk.Scale(playback, from_=0, to=100, resolution=5, orient='horizontal', variable=self.audio_playback_volume, command=self._audio_playback_volume_changed, showvalue=True, length=150)
        self.audio_playback_volume_scale.grid(row=0,column=4,sticky='ew')
        self.export_status = ttk.Label(audio, text='Final export is automatic after synthesis.', wraplength=390); self.export_status.grid(row=5,column=0,columnspan=2,sticky='w',pady=(5,0))
        audio.columnconfigure(0,weight=1); audio.columnconfigure(1,weight=1)

        tools = ttk.Frame(content); tools.grid(row=4,column=0,sticky='ew',pady=(0,8))
        self.diagnostic_button = ttk.Button(tools, text='Export diagnostic ZIP', command=self.export_diagnostics_action); self.diagnostic_button.pack(side='right')
        self.open_diagnostics_button = ttk.Button(tools, text='Open diagnostics folder', command=self.open_diagnostics_folder); self.open_diagnostics_button.pack(side='right', padx=(0,5))

        activity = ttk.Frame(content); activity.grid(row=5,column=0,sticky='nsew'); activity.columnconfigure(0,weight=1); activity.columnconfigure(1,weight=0,minsize=430); activity.rowconfigure(0,weight=1)
        _, log_body = card(activity, 'Run log', row=0,column=0,padx=(0,4))
        self.log_progress = ttk.Progressbar(log_body, maximum=100); self.log_progress.pack(side='top',fill='x',pady=(0,6))
        self.log = tk.Text(log_body, height=13, width=110, wrap='word'); self.log.pack(fill='both',expand=True)
        self.parts_frame, status_body = card(activity, 'Status', row=0,column=1,padx=(4,0))
        self.parts_frame.configure(width=430); self.parts_frame.grid_propagate(False)
        self.status_body = status_body; self.status_body.configure(width=410); self.status_body.pack_propagate(False)
        self.parts = ttk.Treeview(status_body, columns=('part','state'), show='headings', height=8)
        self.parts.heading('part',text='Part/Page'); self.parts.heading('state',text='Status')
        self.parts.column('part',width=92,anchor='center',stretch=False); self.parts.column('state',width=292,anchor='w',stretch=False)
        self.parts_scroll = ttk.Scrollbar(status_body,orient='vertical',command=self.parts.yview); self.parts.configure(yscrollcommand=self.parts_scroll.set)
        self.parts.pack(side='top',fill='both',expand=True); self.parts_scroll.pack(side='right',fill='y')
        self.status = ttk.Label(status_body,text='0%',width=52,anchor='w'); self.status.pack(side='top',anchor='w',pady=(6,0))
        self.status_current_progress = ttk.Progressbar(status_body,maximum=100); self.status_current_progress.pack(side='top',fill='x',pady=(6,2))
        self.status_overall_progress = self.status_current_progress
        self.overall_progress = self.log_progress
        self.current_progress = self.status_current_progress
        self.current_label = ttk.Label(status_body,text=''); self.overall_label = ttk.Label(status_body,text='')
        self.cleaned_text_opened = False
        self.reload_generation = 0
        self._status_message = '0%'; self._status_marquee_offset = 0
        self.root.after(350, self._status_marquee_tick)

        footer = ttk.Frame(self.shell); footer.pack(side='bottom',fill='x',pady=(6,0))
        ttk.Label(footer,text='COPYRIGHT \xa9 KENT REIS & KAIROS REP\xdaBLICA').pack(side='left')
        ttk.Label(footer,text='BUILT IN CONSTANTINOPLE WITH LOVE').pack(side='right')
        self._render_workflow_state()

    def _bind_mousewheel(self) -> None:
        self.root.bind_all('<MouseWheel>', self._on_mousewheel, add='+')
        self.root.bind_all('<Button-4>', self._on_linux_mousewheel, add='+')
        self.root.bind_all('<Button-5>', self._on_linux_mousewheel, add='+')

    @staticmethod
    def _widget_class(widget: tk.Widget) -> str:
        try:
            return str(widget.winfo_class())
        except Exception:
            return ''

    def _on_root_configure(self, event) -> None:
        if event.widget is self.root:
            self._sync_outer_scroll_policy()

    def _outer_scroll_enabled(self) -> bool:
        return outer_scroll_enabled(visible_window_height_px(self.root))

    def _sync_outer_scroll_policy(self) -> None:
        if not hasattr(self, 'scrollbar'):
            return
        if self._outer_scroll_enabled():
            if not self.scrollbar.winfo_manager():
                self.scrollbar.pack(side='right', fill='y')
            return
        self.canvas.yview_moveto(0.0)
        if self.scrollbar.winfo_manager():
            self.scrollbar.pack_forget()

    def _scroll_outer_viewport(self, units: int) -> str | None:
        if not units:
            return None
        if not self._outer_scroll_enabled():
            return 'break'
        self.canvas.yview_scroll(int(units), 'units')
        return 'break'

    def _on_mousewheel(self, event) -> str | None:
        if preserves_native_wheel(self._widget_class(event.widget)):
            return None
        return self._scroll_outer_viewport(wheel_scroll_units(getattr(event, 'delta', 0)))

    def _on_linux_mousewheel(self, event) -> str | None:
        if preserves_native_wheel(self._widget_class(event.widget)):
            return None
        number = int(getattr(event, 'num', 0) or 0)
        return self._scroll_outer_viewport(-1 if number == 4 else (1 if number == 5 else 0))

    def _workflow_button(self, parent: tk.Widget, key: str, text: str, command, *, row: int, column: int) -> tk.Button:
        item = tk.Button(parent, text=text, command=command, padx=7, pady=3)
        item.grid(row=row, column=column, sticky='ew', padx=3, pady=3)
        self.workflow_buttons[key] = item
        self.workflow_base_labels[key] = text
        return item

    def _tts_engine_id(self) -> str:
        return self.tts_engine_labels.get(self.tts_engine.get(), DEFAULT_TTS_ENGINE)

    def _profile_id(self) -> str:
        return PROFILE_LABELS.get(self.profile.get(), DEFAULT_PROCESSING_PROFILE)

    def _prepare_layout_mode(self) -> str:
        mode = self.prepare_layout_mode.get() if hasattr(self, 'prepare_layout_mode') else 'auto'
        return mode if mode in PREPARE_MODE_BY_ID else 'auto'


    def _current_speech_controls(self) -> dict[str, str]:
        return speech_controls(
            provider_id=self._tts_engine_id(),
            voice=self.voice.get(),
            rate=self.rate.get(),
            pitch=self.pitch.get(),
            volume=self.volume.get(),
        )

    def _speech_request_snapshot(self) -> dict[str, object]:
        """Read Tkinter values on the GUI thread before starting background work."""
        controls = self._current_speech_controls()
        return {**controls, 'keep_awake': bool(self.keep_awake.get())}

    def _set_speech_controls(self, controls: dict[str, str]) -> None:
        labels_by_id = {provider_id: label for label, provider_id in self.tts_engine_labels.items()}
        provider_id = controls.get('provider_id', DEFAULT_TTS_ENGINE)
        if provider_id in labels_by_id:
            self.tts_engine.set(labels_by_id[provider_id])
        self.rate.set(controls.get('rate', DEFAULT_RATE))
        self.pitch.set(controls.get('pitch', DEFAULT_PITCH))
        self.volume.set(controls.get('volume', DEFAULT_VOLUME))
        if hasattr(self, 'rate_slider_value'):
            self.rate_slider_value.set(self._percent_text_to_int(self.rate.get()))
        if hasattr(self, 'volume_slider_value'):
            self.volume_slider_value.set(self._percent_text_to_int(self.volume.get()))
        voice = controls.get('voice', DEFAULT_VOICE)
        available = list(self.voice_combo['values'])
        if voice not in available:
            self.voice_combo['values'] = [voice, *available]
        self.voice.set(voice)

    def _rehydrate_job_speech_controls(self, job: JobPaths, manifest: dict) -> bool:
        candidates = [str(item.get('short_name')) for item in self.voice_records if item.get('short_name')]
        controls = recover_speech_controls(
            manifest,
            preferred=self._current_speech_controls(),
            candidate_voices=candidates,
        )
        if not controls:
            return False
        manifest['audio']['controls'] = controls
        save_manifest(job, manifest)
        self._set_speech_controls(controls)
        return True

    def _resume_controls_are_approved(self, job: JobPaths) -> bool:
        manifest = load_manifest(job)
        current_signature = audio_signature(**self._current_speech_controls())
        preview = manifest.get('gates', {}).get('preview', {})
        return bool(
            preview.get('approved_audio_signature') == current_signature
            and preview.get('approved_part_sha256') == (manifest.get('parts') or [{}])[0].get('sha256')
        )

    def _browse_source(self) -> None:
        initial = self.source_folder if Path(self.source_folder).exists() else str(Path.home())
        value = filedialog.askopenfilename(initialdir=initial, filetypes=[('Books', '*.pdf *.epub *.mobi *.azw *.prc *.docx *.txt *.md'), ('All files', '*.*')])
        if value:
            self.source.set(value)
            self.job = None
            if hasattr(self, 'parts'):
                self._reset_part_view()
            self.ocr_analysis = None
            self.ocr_status.config(text='Status: Not analyzed')
            self.ocr_reason.config(text='Next step: Analyze book source.')
            self._render_workflow_state()

    def _browse_work(self) -> None:
        value = filedialog.askdirectory(initialdir=self.work_root.get() or str(local_work_root()))
        if value: self.work_root.set(value)

    def _browse_export(self) -> None:
        value = filedialog.askdirectory(initialdir=self.export_root.get() or str(default_export_root()))
        if value: self.export_root.set(value)

    def _browse_dict(self) -> None:
        value = filedialog.askopenfilename(filetypes=[('JSON', '*.json'), ('All files', '*.*')])
        if value: self.dictionary.set(value)

    def _open_configured_path(self, raw: str, *, label: str, select_file: bool = False) -> None:
        value = raw.strip()
        if not value:
            messagebox.showerror(label, f'No {label.lower()} path is selected.')
            return
        try:
            open_in_file_manager(Path(value), select_file=select_file)
            self._log_event(f'Opened {label.lower()}: {value}')
        except RuntimeError as exc:
            messagebox.showerror(label, str(exc))

    def _open_source(self) -> None:
        self._open_configured_path(self.source.get(), label='Book', select_file=True)

    def _open_work_root(self) -> None:
        self._open_configured_path(self.work_root.get(), label='Local working root')

    def _open_export_root(self) -> None:
        self._open_configured_path(self.export_root.get(), label='Export root')

    def _open_dictionary(self) -> None:
        self._open_configured_path(self.dictionary.get(), label='Pronunciation dictionary', select_file=True)

    def _persist_default(self, key: str, value: str, message: str) -> None:
        cfg = load_config(); cfg[key] = value; save_config(cfg); self.status.config(text=message)

    def _set_source_folder_default(self) -> None:
        value = self.source.get().strip()
        if not value:
            messagebox.showerror('No book', 'Select a book first.'); return
        folder = str(Path(value).expanduser().resolve().parent)
        self.source_folder = folder
        self._persist_default('source_folder', folder, 'Default book folder saved.')

    def _set_work_default(self) -> None:
        self._persist_default('work_root', self.work_root.get().strip(), 'Default local working root saved.')

    def _set_export_default(self) -> None:
        self._persist_default('export_root', self.export_root.get().strip(), 'Default export root saved.')

    def _set_dictionary_default(self) -> None:
        self._persist_default('dictionary', self.dictionary.get().strip(), 'Default pronunciation dictionary saved.')

    def _dict(self) -> Path | None:
        return Path(self.dictionary.get()) if self.dictionary.get().strip() else None

    def _save_runtime_cfg(self) -> None:
        cfg = load_config(); cfg.update({'dictionary': self.dictionary.get(), 'tts_engine': self._tts_engine_id(), 'voice': self.voice.get(), 'rate': self.rate.get(), 'pitch': self.pitch.get(), 'volume': self.volume.get(), 'processing_profile': self._profile_id(), 'prepare_layout_mode': self._prepare_layout_mode(), 'show_all_voices': self.show_all_voices.get(), 'keep_awake': self.keep_awake.get()}); save_config(cfg)

    def _job_required(self) -> JobPaths | None:
        if not self.job: messagebox.showerror('No job', 'Prepare text or resume an existing job first.')
        return self.job

    def _voice_controls_changed(self, *_: object) -> None:
        if self.speech_settings_locked:
            self._apply_speech_settings_lock()
            return
        provider_id = self._tts_engine_id()
        if getattr(self, 'last_tts_engine_id', provider_id) != provider_id:
            self.last_tts_engine_id = provider_id
            self.voice_records = load_voice_cache(provider_id)
            if hasattr(self, 'voice_combo'):
                self._apply_voice_filter()
                self._refresh_voices(background=True)
        if self.job: self.status.config(text='Speech settings changed. Generate and approve Part 1 again before full synthesis.')
        self._render_workflow_state()

    def _profile_changed(self, *_: object) -> None:
        self._apply_voice_filter()

    def _apply_voice_filter(self) -> None:
        voices = filter_voices(self.voice_records, self._profile_id(), show_all=self.show_all_voices.get())
        names = [item['short_name'] for item in voices]
        self.voice_combo['values'] = names
        if self.voice.get() not in names and names:
            self.voice.set(names[0])

    def _refresh_voices(self, *, background: bool) -> None:
        provider_id = self._tts_engine_id()
        def work(): return refresh_voice_cache(provider_id)
        def done(voices):
            self.voice_records = voices; self._apply_voice_filter(); self.status.config(text=f'Voice list refreshed: {len(voices)} voices.')
        if background:
            def worker():
                try: self.events.put(('silent-ok', 'Refresh voices', work(), done))
                except Exception as exc: self.events.put(('silent-error', 'Refresh voices', f'{type(exc).__name__}: {exc}', None))
            threading.Thread(target=worker, daemon=True).start()
        else:
            self._run('Refresh voices', work, done)

    def _set_actions_enabled(self, enabled: bool) -> None:
        self.ui_actions_enabled = enabled
        state = 'normal' if enabled else 'disabled'
        for button in self.action_buttons:
            button.config(state=state)
        self._update_ocr_action_state()
        self._render_workflow_state()
        self._apply_speech_settings_lock()

    def _process_trace_event(self, payload: dict[str, object]) -> None:
        if str(payload.get('phase') or '') == 'error':
            self.events.put(('process', 'External process', payload, None))

    def _run(self, label: str, fn, on_success=None) -> None:
        if not self.busy.start(label):
            messagebox.showwarning('Job busy', f'Another operation is still running: {self.busy.label}'); return
        generation = self._current_operation_generation()
        self._cancel_event().clear()
        if not hasattr(self, '_v23_thread_local'):
            self._v23_thread_local = threading.local()
        if not hasattr(self, '_active_worker_threads'):
            self._active_worker_threads = {}
        self._set_actions_enabled(False)
        self._render_reload_button()
        self._set_status_message(label)
        self._log_event(f'Started: {label}')
        def worker() -> None:
            self._v23_thread_local.generation = generation
            try:
                with process_trace(self._process_trace_event, operation=label):
                    result = fn()
                if generation != self._current_operation_generation() or self._cancel_event().is_set():
                    return
                self.events.put(('ok', label, result, on_success))
            except (SystemExit, KeyboardInterrupt):
                return
            except Exception as exc:
                if generation != self._current_operation_generation() or self._cancel_event().is_set():
                    return
                self.events.put(('error', label, f'{type(exc).__name__}: {exc}', None))
            finally:
                self._active_worker_threads.pop(generation, None)
        thread = threading.Thread(target=worker, daemon=True, name=f'kr-b2a-worker-{generation}')
        self._active_worker_threads[generation] = thread
        thread.start()

    def _progress_event(self, payload: dict) -> None:
        payload = dict(payload or {})
        thread_local = getattr(self, '_v23_thread_local', None)
        generation = int(getattr(thread_local, 'generation', self._current_operation_generation()) or 0)
        payload['_operation_generation'] = generation
        if generation != self._current_operation_generation() or self._cancel_event().is_set():
            return
        if 'index' not in payload:
            self._voice_sample_progress_event(payload)
            return
        state = str(payload.get('state') or '')
        index = int(payload.get('index') or 0)
        if state == 'provider-status':
            self.telemetry_mailbox.publish(payload)
            return
        if index > 0 and state in {'running', 'retrying'}:
            self.telemetry_mailbox.reopen(index)
        elif index > 0 and state in {'validating', 'done', 'failed'}:
            self.telemetry_mailbox.mark_terminal(index)
        self.events.put(('progress', 'Synthesis', payload, None))

    def _drain(self) -> None:
        self._apply_owner_ui_runtime_contract()
        """Drain bounded control work, then apply latest-only Provider snapshots.

        Every callback yields to Tk quickly. This prevents audio-chunk telemetry from
        starving the Windows message pump while keeping the current Provider state
        visible.
        """
        started = time.monotonic()
        processed = 0
        while processed < CONTROL_EVENTS_PER_DRAIN:
            if time.monotonic() - started >= CONTROL_DRAIN_TIME_BUDGET_SECONDS:
                break
            try:
                kind, label, payload, callback = self.events.get_nowait()
            except queue.Empty:
                break
            processed += 1
            if kind == 'voice-sample-progress':
                try:
                    self._update_voice_sample_progress(payload)
                except Exception as exc:
                    self._log_event(f'Ignored malformed voice-sample telemetry - {type(exc).__name__}: {exc}')
                continue
            if kind == 'progress':
                try:
                    self._update_part_progress(payload)
                except Exception as exc:
                    self._log_event(f'Ignored malformed synthesis telemetry - {type(exc).__name__}: {exc}')
                continue
            if kind == 'ocr-progress':
                try:
                    self._update_ocr_progress(payload)
                except Exception as exc:
                    self._log_event(f'Ignored malformed OCR telemetry - {type(exc).__name__}: {exc}')
                continue
            if kind == 'process':
                self._handle_process_trace(payload)
                continue
            if kind == 'silent-ok':
                if callback:
                    callback(payload)
                continue
            if kind == 'silent-error':
                self._log_event(f'{label}: {payload}')
                continue
            self.busy.finish()
            self._set_actions_enabled(True)
            if kind == 'error':
                if label in {'Preview OCR sample', 'Run full OCR'}:
                    self._set_ocr_operation(None)
                user_payload = sanitize_user_error(str(payload))
                self.status.config(text=f'Failed: {label}')
                self._log_event(f'Failed: {label} · {user_payload}')
                messagebox.showerror(label, user_payload)
            else:
                failures = payload.get('failures') if isinstance(payload, dict) else None
                if failures:
                    if label in {'Preview OCR sample', 'Run full OCR'}:
                        self._set_ocr_operation(None)
                    self.status.config(text=f'Failed: {label}')
                    detail = str(failures[0].get('switch_recommendation') or failures[0].get('error') or failures[0])
                    self._log_event(f'Failed: {label} · {detail}')
                    messagebox.showerror(label, detail)
                else:
                    self.status.config(text=f'Completed: {label}')
                    self._log_event(f'Completed: {label}')
                    if callback:
                        callback(payload)
                    self._refresh_job_view()
            self._render_workflow_state()
        for telemetry in self.telemetry_mailbox.take_latest(limit=TELEMETRY_SNAPSHOTS_PER_DRAIN):
            self._update_provider_telemetry(telemetry)
        self.root.after(GUI_DRAIN_INTERVAL_MS, self._drain)

    def _handle_process_trace(self, payload: dict[str, object]) -> None:
        phase = str(payload.get('phase') or '')
        tool = str(payload.get('tool') or 'unknown')
        if phase == 'error':
            self._log_event(f'External tool failed: {tool} · {payload.get("error")}')

    def _render_workflow_state(self) -> None:
        # V28_SAFE_RELOAD_UI_TEXT_PREPARE_WATCHDOG_DIALOG_RUNTIME
        if not hasattr(self, 'workflow_buttons'):
            return
        roles = {key: 'blocked' for key in self.workflow_buttons}
        source_selected = bool(self.source.get().strip())
        running = bool(self.busy.label)
        snapshot = self._audio_manifest_snapshot()
        if source_selected:
            is_pdf = Path(self.source.get().strip()).suffix.lower() == '.pdf'
            analysis = getattr(self, 'ocr_analysis', None)
            ocr_status = str(getattr(analysis, 'status', '') or '')
            ocr_ready = (not is_pdf) or (analysis is not None and ocr_status != 'required') or self._ocr_output_ready()
            if ocr_ready:
                if not snapshot.get('job_ready'):
                    roles['prepare'] = 'next'
                elif not snapshot.get('proofread_approved'):
                    roles['prepare'] = 'completed'
                    if bool(getattr(self, 'cleaned_text_opened', False)):
                        roles['open_cleaned'] = 'completed'; roles['approve_text'] = 'next'
                    else:
                        roles['open_cleaned'] = 'next'; roles['approve_text'] = 'blocked'
                elif bool(getattr(self, '_part_one_rejected_pending_preview', False)):
                    roles['prepare'] = 'completed'; roles['open_cleaned'] = 'completed'; roles['approve_text'] = 'completed'; roles['preview'] = 'next'
                elif not snapshot.get('part1_ready'):
                    roles['prepare'] = 'completed'; roles['open_cleaned'] = 'completed'; roles['approve_text'] = 'completed'; roles['preview'] = 'next'
                elif not snapshot.get('preview_approved'):
                    roles['prepare'] = 'completed'; roles['open_cleaned'] = 'completed'; roles['approve_text'] = 'completed'; roles['preview'] = 'completed'; roles['reject_preview'] = 'reject'; roles['approve_preview'] = 'approve'
                elif snapshot.get('failed_parts'):
                    roles['prepare'] = 'completed'; roles['open_cleaned'] = 'completed'; roles['approve_text'] = 'completed'; roles['preview'] = 'completed'; roles['approve_preview'] = 'completed'; roles['retry_failed'] = 'next'
                elif not snapshot.get('all_parts_ready'):
                    roles['prepare'] = 'completed'; roles['open_cleaned'] = 'completed'; roles['approve_text'] = 'completed'; roles['preview'] = 'completed'; roles['approve_preview'] = 'completed'; roles['synthesize'] = 'next'
                elif not snapshot.get('export_verified'):
                    roles['prepare'] = 'completed'; roles['open_cleaned'] = 'completed'; roles['approve_text'] = 'completed'; roles['preview'] = 'completed'; roles['approve_preview'] = 'completed'; roles['synthesize'] = 'completed'; roles['merge'] = 'next'
                else:
                    roles['prepare'] = 'completed'; roles['open_cleaned'] = 'completed'; roles['approve_text'] = 'completed'; roles['preview'] = 'completed'; roles['approve_preview'] = 'completed'; roles['synthesize'] = 'completed'; roles['merge'] = 'completed'; roles['open_export'] = 'next'
        if running:
            label = str(self.busy.label or '').lower()
            for key, token in [('prepare','prepare'),('preview','preview part 1'),('synthesize','synthesize'),('retry_failed','retry'),('merge','merge'),('open_export','export')]:
                if token in label and key in roles:
                    roles[key] = 'running'
        for key, button in self.workflow_buttons.items():
            self._paint_button(button, roles.get(key, 'blocked'), text=self.workflow_base_labels[key])
        self._render_cleanup_action_state(); self._render_reload_button()
        self._apply_speech_settings_lock(); self._render_ocr_ui_state(); self._render_audio_playback_state()

    def _apply_speech_settings_lock(self) -> None:
        if not hasattr(self, 'speech_setting_widgets'):
            return
        locked = bool(self.speech_settings_locked)
        for widget, unlocked_state in self.speech_setting_widgets:
            try:
                widget.config(state='disabled' if locked or not self.ui_actions_enabled else unlocked_state)
            except tk.TclError:
                pass
        if hasattr(self, 'speech_lock_hint'):
            self.speech_lock_hint.config(text='Locked after Preview Part 1. Reload or reject the preview to change speech settings.' if locked else '')

    def _paint_button(self, button: tk.Button, role: str, *, text: str | None = None) -> None:
        base = text if text is not None else str(button.cget('text')).split('] ', 1)[-1]
        styles = {
            'blocked': ('SystemButtonFace', 'SystemGrayText', 'disabled', ''),
            'normal': ('SystemButtonFace', 'SystemButtonText', 'normal', ''),
            'optional': ('SystemButtonFace', 'SystemButtonText', 'normal', '[OPTIONAL] '),
            'next': ('SystemHighlight', 'SystemHighlightText', 'normal', '[NEXT] '),
            'approve': ('SystemHighlight', 'SystemHighlightText', 'normal', '[NEXT] '),
            'reject': ('#F6D6D6', '#7A1F1F', 'normal', '[REJECT] '),
            'running': ('SystemHighlight', 'SystemHighlightText', 'disabled', '[RUNNING] '),
            'completed': ('SystemButtonFace', 'SystemGrayText', 'disabled', '[DONE] '),
            'skipped': ('SystemButtonFace', 'SystemGrayText', 'disabled', '[SKIPPED] '),
        }
        bg, fg, state, prefix = styles.get(role, styles['blocked'])
        button.config(text=prefix + base, bg=bg, fg=fg, activebackground=bg, activeforeground=fg, state=state if self.ui_actions_enabled else 'disabled', disabledforeground=fg, font=('TkDefaultFont', 9, 'bold') if role in {'next','approve','reject','running'} else ('TkDefaultFont', 9))

    def _audio_manifest_snapshot(self) -> dict[str, object]:
        if not self.job:
            return {'job_ready': False, 'proofread_approved': False, 'parts_total': 0, 'part1_ready': False, 'preview_approved': False, 'all_parts_ready': False, 'failed_parts': False, 'export_verified': False}
        try:
            manifest = load_manifest(self.job)
        except Exception:
            return {'job_ready': False, 'proofread_approved': False, 'parts_total': 0, 'part1_ready': False, 'preview_approved': False, 'all_parts_ready': False, 'failed_parts': False, 'export_verified': False}
        parts = manifest.get('parts', []) or []
        completed = manifest.get('audio', {}).get('completed', {}) or {}
        completed_indexes = {int(key) for key in completed if str(key).isdigit()}
        gates = manifest.get('gates', {}) or {}
        preview = gates.get('preview', {}) or {}
        proofread = gates.get('proofread', {}) or {}
        failures = manifest.get('audio', {}).get('failures', {}) or {}
        total = len(parts)
        return {
            'job_ready': bool(total),
            'proofread_approved': bool(proofread.get('approved_sha256')),
            'parts_total': total,
            'part1_ready': 1 in completed_indexes,
            'preview_approved': bool(preview.get('approved_audio_signature') and preview.get('approved_part_sha256')),
            'all_parts_ready': bool(total and len(completed_indexes) == total),
            'failed_parts': bool(failures),
            'export_verified': bool(export_is_verified(self.job)),
        }

    def _render_audio_completion_state(self) -> None:
        if not hasattr(self, 'workflow_buttons'):
            return
        snapshot = self._audio_manifest_snapshot()
        plan = derive_audio_action_plan(
            source_selected=bool(self.source.get().strip()),
            running=bool(self.busy.label),
            settings_locked=bool(self.speech_settings_locked),
            **snapshot,
        )
        self.speech_settings_locked = bool(plan.settings_locked or self.speech_settings_locked)
        for key, role in plan.roles.items():
            button = self.workflow_buttons.get(key)
            if button:
                self._paint_button(button, role, text=self.workflow_base_labels[key])
        if hasattr(self, 'export_status'):
            self.export_status.config(text=plan.banner)

    def _render_reload_button(self) -> None:
        button = getattr(self, 'reload_button', None)
        if button is None:
            return
        selected = bool(self.source.get().strip())
        blocked = selected and self._reload_blocked_by_active_external_work()
        if blocked:
            button.config(text='Reload book', bg='SystemButtonFace', fg='SystemGrayText', state='disabled', disabledforeground='SystemGrayText', font=('TkDefaultFont', 9))
        elif selected:
            button.config(text='[RELOAD] Reload book', bg='SystemHighlight', fg='SystemHighlightText', activebackground='SystemHighlight', activeforeground='SystemHighlightText', state='normal', disabledforeground='SystemHighlightText', font=('TkDefaultFont', 9, 'bold'))
        else:
            button.config(text='Reload book', bg='SystemButtonFace', fg='SystemGrayText', state='disabled', disabledforeground='SystemGrayText', font=('TkDefaultFont', 9))

    def _render_cleanup_action_state(self) -> None:
        if not hasattr(self, 'workflow_buttons'):
            return
        job = getattr(self, 'job', None)
        analysis = job_status(job).get('cleanup_analysis', {}) if job else {}
        junk_ready = analysis.get('repeated_headers_and_junk', {}).get('status') == 'recommended'
        datetime_ready = analysis.get('metadata_datetime_tags', {}).get('status') == 'recommended'
        for button, ready in ((getattr(self, 'cleanup_junk_button', None), junk_ready), (getattr(self, 'cleanup_datetime_button', None), datetime_ready)):
            if button is not None:
                self._paint_button(button, 'normal' if ready else 'blocked', text='Apply cleanup')
        apply_all = self.workflow_buttons.get('cleanup_all')
        if apply_all is not None:
            self._paint_button(apply_all, 'normal' if (junk_ready or datetime_ready) else 'blocked', text='Apply all recommended cleanup')

    def _log_event(self, text: str) -> None:
        log = getattr(self, 'log', None)
        if log is None:
            return
        stamp = datetime.now().strftime('%H:%M:%S')
        lines = str(text).splitlines() or ['']
        for line in lines:
            log.insert('end', f'[{stamp}] {line}\n')
        log.see('end')

    def _append(self, text: str) -> None:
        self._log_event(text)

    def _reset_part_view(self) -> None:
        self.part_states.clear()
        for iid in self.parts.get_children():
            self.parts.delete(iid)
        self._set_project_overall_percent(0)
        self._set_status_item_percent(0)
        self.overall_label.config(text='0 / 0 parts completed - 0%')
        self.current_label.config(text='No active part')
        self._set_status_message('0%', percent=0)

    def _render_cleanup(self, analysis: dict) -> None:
        self.cleanup_analysis = dict(analysis or {})
        junk = analysis.get('repeated_headers_and_junk', {})
        dates = analysis.get('metadata_datetime_tags', {})
        self.cleanup_junk.config(text=f"Repeated headers and junk: {junk.get('status', 'not-analyzed')} · {junk.get('count', 0)} high-confidence")
        self.cleanup_datetime.config(text=f"Metadata-like date/time tags: {dates.get('status', 'not-analyzed')} · {dates.get('count', 0)} high-confidence")
        self._render_cleanup_action_state()

    def _refresh_job_view(self) -> None:
        if not self.job:
            return
        status = job_status(self.job)
        total = int(status['parts'])
        completed = int(status['completed_audio_parts'])
        failed = set(status['failed_audio_parts'])
        completed_indexes = {int(index) for index in manifest_completed(self.job)}
        for index in range(1, total + 1):
            state = 'failed' if index in failed else ('done' if index in completed_indexes else self.part_states.get(index, 'queued'))
            highlight = 'running' if state.startswith('RUNNING') or state.startswith('RETRYING') else ('validating' if state.startswith('VALIDATING') else None)
            self._set_part_state(index, state, highlight=highlight)
        pct = (completed / total * 100.0) if total else 0.0
        self._set_project_overall_percent(pct)
        self.overall_label.config(text=f'{completed} / {total} parts completed - {pct:.0f}%')
        self._render_cleanup(status.get('cleanup_analysis', {}))
        if hasattr(self, 'export_status'):
            export_state = status.get('export', {}).get('status', 'not-finalized')
            self.export_status.config(text=f'Final export: {export_state}. Export finalization and verification are automatic.')
        self._render_workflow_state()

    def _set_part_state(self, index: int, state: str, *, highlight: str | None = None) -> None:
        self.part_states[index] = state
        iid = str(index)
        percent = self._status_percent_from_state(state)
        values = (f'{index:04d}', f'{percent}%')
        tags = (highlight,) if highlight else ()
        if self.parts.exists(iid):
            self.parts.item(iid, values=values, tags=tags)
        else:
            self.parts.insert('', 'end', iid=iid, values=values, tags=tags)

    def _center_part_status(self, index: int) -> None:
        parts = getattr(self, 'parts', None)
        if parts is None:
            return
        iid = str(index)
        if not parts.exists(iid):
            return
        children = list(parts.get_children())
        if not children:
            return
        try:
            position = children.index(iid)
        except ValueError:
            return
        visible_rows = max(3, int(parts.cget('height') or 19))
        target = max(0.0, min(1.0, (position - visible_rows // 2) / max(1, len(children))))
        parts.yview_moveto(target)
        parts.see(iid)
        parts.selection_set(iid)
        parts.focus(iid)

    def _maybe_center_part_status(self, index: int, state: str) -> None:
        if str(state) not in {'running', 'retrying'}:
            return
        try:
            part_index = int(index)
        except (TypeError, ValueError):
            return
        if getattr(self, '_last_centered_part_status_index', None) == part_index:
            return
        self._last_centered_part_status_index = part_index
        self._center_part_status(part_index)

    def _expected_seconds(self, text_chars: int) -> float:
        if self.runtime_seconds_per_char:
            rate = sum(self.runtime_seconds_per_char[-8:]) / len(self.runtime_seconds_per_char[-8:])
            return max(4.0, min(300.0, rate * max(1, text_chars)))
        return max(12.0, min(120.0, max(1, text_chars) / 180.0))

    def _log_progress_bucket(self, index: int, state: str, percent: int) -> None:
        bucket = min(100, max(0, percent)) // 10 * 10
        previous = self.logged_progress_buckets.get(index, -10)
        if state in {'running', 'retrying'} and bucket <= previous:
            return
        self.logged_progress_buckets[index] = bucket
        if state == 'running':
            self._log_event(f'Part {index:04d}: synthesizing · {percent}% estimated')
        elif state == 'retrying':
            self._log_event(f'Part {index:04d}: retrying · {percent}% estimated')
        elif state == 'validating':
            self._log_event(f'Part {index:04d}: validating MP3')
        elif state == 'done':
            self._log_event(f'Part {index:04d}: completed and checkpoint saved')
        elif state == 'failed':
            self._log_event(f'Part {index:04d}: failed')

    @staticmethod
    def _format_seconds(value: float) -> str:
        total = max(0, int(value))
        minutes, seconds = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        return f'{hours:02d}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes:02d}:{seconds:02d}'

    @staticmethod
    def _format_bytes(value: int) -> str:
        amount = float(max(0, int(value)))
        for unit in ('B', 'KB', 'MB', 'GB'):
            if amount < 1024.0 or unit == 'GB':
                return f'{amount:.1f} {unit}'
            amount /= 1024.0
        return f'{amount:.1f} GB'

    def _provider_runtime_text(self, elapsed: float) -> str:
        telemetry = self.provider_runtime
        stage = str(telemetry.get('stage') or 'synthesizing-audio').replace('-', ' ')
        provider_id = str(telemetry.get('provider_id') or self._tts_engine_id())
        bytes_received = int(telemetry.get('bytes_received') or 0)
        last_audio = float(telemetry.get('last_audio_seconds_ago') or 0.0)
        telemetry_seen = float(telemetry.get('_ui_received_monotonic') or time.monotonic())
        last_audio += max(0.0, time.monotonic() - telemetry_seen)
        attempt = int(telemetry.get('attempt') or 1)
        return (
            f'{provider_id} · {stage} · elapsed {self._format_seconds(elapsed)} · '
            f'audio {self._format_bytes(bytes_received)} · last audio {int(last_audio)} sec ago · attempt {attempt}'
        )

    def _ui_audio_estimate_percent(self, elapsed: float, expected: float, current: int) -> int:
        expected = max(1.0, float(expected or 1.0))
        elapsed = max(0.0, float(elapsed or 0.0))
        current = max(0, min(100, int(current or 0)))
        if elapsed <= expected:
            target = int(elapsed / expected * 90.0)
        else:
            overtime_ratio = min(1.0, (elapsed - expected) / max(1.0, expected * 4.0))
            target = 90 + int(overtime_ratio * 8.0)
        return max(current, min(98, target))

    def _should_log_provider_telemetry(self, index: int, runtime: dict[str, object]) -> bool:
        now = time.monotonic()
        try:
            bytes_received = int(runtime.get('bytes_received') or 0)
        except (TypeError, ValueError):
            bytes_received = 0
        bytes_bucket = bytes_received // max(1, 512 * 1024)
        signature = f"{index}|{runtime.get('provider_id')}|{runtime.get('stage')}|{runtime.get('attempt')}"
        if signature != getattr(self, '_last_provider_log_signature', ''):
            self._last_provider_log_signature = signature
            self._last_provider_log_bytes_bucket = bytes_bucket
            self._last_provider_log_at = now
            return True
        if bytes_bucket > int(getattr(self, '_last_provider_log_bytes_bucket', -1)):
            self._last_provider_log_bytes_bucket = bytes_bucket
            self._last_provider_log_at = now
            return True
        if now - float(getattr(self, '_last_provider_log_at', 0.0) or 0.0) >= 30.0:
            self._last_provider_log_at = now
            return True
        return False

    def _estimate_tick(self, token: int) -> None:
        if token != int(getattr(self, 'estimate_token', 0) or 0):
            return
        if not self._audio_status_active():
            return
        started = float(getattr(self, 'current_started_monotonic', time.monotonic()) or time.monotonic())
        expected = max(1.0, float(getattr(self, 'current_expected_seconds', 1.0) or 1.0))
        elapsed = max(0.0, time.monotonic() - started)
        estimate = self._ui_audio_estimate_percent(elapsed, expected, int(getattr(self, 'current_estimate', 0) or 0))
        self.current_estimate = estimate
        index = max(1, int(getattr(self, 'current_index', 1) or 1))
        self._set_status_item_percent(estimate)
        self._set_project_overall_percent(self._project_tts_overall_percent(index, estimate))
        self._render_audio_status_summary(index=index, percent=estimate)
        self.root.after(700, lambda: self._estimate_tick(token))

    def _update_export_progress(self, payload: dict) -> None:
        state = str(payload.get('state') or '')
        index = int(payload.get('index') or 0)
        total = int(payload.get('total') or 0)
        filename = str(payload.get('file') or '')
        if state == 'finalization-started':
            self.status.config(text='Finalizing export...')
            self._log_event(f'Export finalization started. Preparing {total} validated Part MP3 files.')
        elif state == 'copying-part':
            self.status.config(text=f'Finalizing export: copying {index} / {total}')
            self._log_event(f'Export copy: {filename} · {index} / {total}')
        elif state == 'copy-reused':
            self.status.config(text=f'Finalizing export: verified existing {index} / {total}')
        elif state == 'writing-cleaned-text':
            self.status.config(text=f'Finalizing export: writing cleaned text {filename}')
        elif state == 'verification-started':
            self.status.config(text='Verifying exported files...')
            self._log_event(f'Export verification started. Expected Parts: {total}.')
        elif state == 'verification-part':
            self.status.config(text=f'Verifying export: {index} / {total}')
        elif state == 'verification-pass':
            self.status.config(text=f'Export verification PASS: {total} Parts')
            self._log_event(f'Export verification PASS. Exported Parts: {total}.')
        elif state == 'finalization-completed':
            self.status.config(text=f'Export completed: {total} Parts')
            self._log_event(f'Export completed. Verified Parts written to export root: {total}.')
        elif state in {'verification-failed', 'finalization-failed'}:
            error = str(payload.get('error') or 'unknown error')
            self.status.config(text='Export verification FAILED')
            self._log_event(f'Export verification FAILED: {error}')

    def _update_provider_telemetry(self, payload: dict) -> None:
        normalized = dict(payload or {})
        index = max(1, int(normalized.get('index') or getattr(self, 'current_index', 1) or 1))
        runtime = dict(getattr(self, 'provider_runtime', {}) or {})
        runtime.update({
            'provider_id': normalized.get('provider_id') or runtime.get('provider_id') or self._tts_engine_id(),
            'stage': normalized.get('stage') or normalized.get('state') or runtime.get('stage') or 'provider-status',
            'attempt': int(normalized.get('attempt') or runtime.get('attempt') or 1),
            'bytes_received': int(normalized.get('bytes_received') or runtime.get('bytes_received') or 0),
            'last_audio_seconds_ago': float(normalized.get('last_audio_seconds_ago') or runtime.get('last_audio_seconds_ago') or 0.0),
        })
        self.provider_runtime = runtime
        try:
            estimate = int(normalized.get('estimated_percent') or normalized.get('percent') or getattr(self, 'current_estimate', 0) or 0)
        except (TypeError, ValueError):
            estimate = int(getattr(self, 'current_estimate', 0) or 0)
        self.current_index = index
        self.current_estimate = max(0, min(98, max(int(getattr(self, 'current_estimate', 0) or 0), estimate)))
        self._set_status_item_percent(self.current_estimate)
        self._set_project_overall_percent(self._project_tts_overall_percent(index, self.current_estimate))
        self._render_audio_status_summary(index=index, percent=self.current_estimate)
        if self._should_log_provider_telemetry(index, runtime):
            detail = (
                f"TTS telemetry | Part {index:03d} | stage={runtime['stage']} | "
                f"attempt={runtime['attempt']} | audio={self._format_bytes(int(runtime['bytes_received']))} | "
                f"last_audio={int(float(runtime.get('last_audio_seconds_ago') or 0.0))}s"
            )
            self._log_event(detail)

    def _update_part_progress(self, payload: dict) -> None:
        if int(payload.get('_operation_generation', self._current_operation_generation()) or 0) != self._current_operation_generation() or self._cancel_event().is_set():
            return
        if payload.get('event') == 'export':
            self._update_export_progress(payload)
            return
        index = int(payload['index']); state = str(payload['state'])
        declared_total = int(payload.get('total_parts') or payload.get('total') or 0)
        if declared_total > 0:
            self._audio_total_parts_cache = max(1, declared_total)
        elif int(getattr(self, '_audio_total_parts_cache', 0) or 0) <= 0:
            self._audio_total_parts_cache = max(1, index)
        estimate = int(payload.get('estimated_percent', 0)); text_chars = int(payload.get('text_chars', 0) or 0)
        current_percent = 0; row_state = state; highlight = None
        if state in {'running', 'retrying'}:
            self.current_index = index; self.current_estimate = max(5, estimate); current_percent = self.current_estimate
            self.current_started_monotonic = time.monotonic(); self.current_expected_seconds = self._expected_seconds(text_chars)
            self.provider_runtime = {'provider_id': self._tts_engine_id(), 'stage': state, 'attempt': int(payload.get('attempt') or 1), 'bytes_received': 0, 'last_audio_seconds_ago': 0.0}
            self.estimate_token += 1; token = self.estimate_token; row_state = f'{state.upper()} - {current_percent}%'; highlight = 'running'
            self.root.after(700, lambda: self._estimate_tick(token))
        elif state == 'provider-status':
            self._update_provider_telemetry(payload); return
        elif state == 'retry-wait':
            delay = float(payload.get('retry_delay_seconds') or 0.0); row_state = f'RETRYING - wait {int(delay)} sec'; highlight = 'running'
        elif state == 'validating':
            self.estimate_token += 1; current_percent = 95; row_state = 'VALIDATING MP3'; highlight = 'validating'
        elif state == 'done':
            self.estimate_token += 1; current_percent = 100; row_state = 'done'
            self._audio_completed_parts_cache = max(int(getattr(self, '_audio_completed_parts_cache', 0) or 0), index)
            elapsed = float(payload.get('elapsed_seconds', 0) or 0)
            if elapsed > 0 and text_chars > 0: self.runtime_seconds_per_char.append(elapsed / text_chars)
        elif state == 'failed':
            self.estimate_token += 1; current_percent = 0; row_state = 'failed'
            self._log_event(f'Part {index:04d}: {payload.get("switch_recommendation") or payload.get("error") or "unknown provider failure"}')
        self.current_index = index; self.current_estimate = current_percent
        self._set_status_item_percent(current_percent); self._set_project_overall_percent(self._project_tts_overall_percent(index, current_percent))
        self._set_part_state(index, row_state, highlight=highlight); self._maybe_center_part_status(index, state); self._log_progress_bucket(index, state, current_percent)
        self._render_audio_status_summary(index=index, percent=current_percent)
        self._refresh_job_view()

    def _ocr_progress_event(self, payload: dict[str, object]) -> None:
        normalized = dict(payload or {})
        thread_local = getattr(self, '_v23_thread_local', None)
        generation = int(getattr(thread_local, 'generation', self._current_operation_generation()) or 0)
        normalized['_operation_generation'] = generation
        if generation != self._current_operation_generation() or self._cancel_event().is_set():
            return
        self.events.put(('ocr-progress', 'OCR', normalized, None))

    def _set_ocr_operation(self, kind: str | None) -> None:
        self.ocr_operation_kind = kind
        self.ocr_operation_started_monotonic = time.monotonic() if kind else None
        self.ocr_progress_snapshot = {}
        self.ocr_progress_token += 1
        token = self.ocr_progress_token
        if kind is None:
            self.ocr_paused = False
        else:
            self.root.after(1000, lambda: self._ocr_progress_tick(token))
        self._render_ocr_ui_state()

    def _ocr_progress_tick(self, token: int) -> None:
        if token != self.ocr_progress_token or self.ocr_operation_kind is None:
            return
        if self.ocr_progress_snapshot:
            payload = dict(self.ocr_progress_snapshot)
            if self.ocr_operation_started_monotonic is not None:
                payload['elapsed_seconds'] = time.monotonic() - self.ocr_operation_started_monotonic
            self._update_ocr_progress(payload, from_tick=True)
        self.root.after(1000, lambda: self._ocr_progress_tick(token))

    def _update_ocr_progress(self, payload: dict[str, object], *, from_tick: bool = False) -> None:
        if int(payload.get('_operation_generation', self._current_operation_generation()) or 0) != self._current_operation_generation() or self._cancel_event().is_set():
            return
        if not from_tick:
            self.ocr_progress_snapshot = dict(payload)
        snapshot = self.ocr_v295_snapshot.update(payload, mode=self.ocr_operation_kind or 'full')
        state = str(payload.get('state') or 'ocr-running')
        mode = str(self.ocr_operation_kind or 'full')
        source_total = self._source_pdf_total_pages(payload, snapshot)
        source_page = int(payload.get('source_pdf_page') or payload.get('current_pdf_page') or payload.get('page') or payload.get('current_page') or getattr(snapshot, 'current_pdf_page', 0) or 0)
        completed = int(payload.get('completed_pdf_pages') or payload.get('completed_pages') or getattr(snapshot, 'completed_pdf_pages', 0) or 0)
        current_pct = 100 if state in {'ocr-page-completed', 'ocr-page-recognized', 'ocr-page-reused'} else int(payload.get('page_percent') or 35)
        current_pct = max(0, min(100, current_pct))
        if mode == 'preview':
            sample_index, sample_total = self._preview_sample_position(source_page)
            preview_task_pct = max(0.0, min(100.0, (max(0, sample_index - 1) + current_pct / 100.0) / max(1, sample_total) * 100.0))
            # Preview OCR samples do not represent completed whole-book OCR output.
            # Keep the Run-log overall book bar at zero until full OCR actually begins.
            overall_pct = 0.0
            overall_text = f'Full-book OCR not started | Preview sample {sample_index} / {sample_total}'
            current_text = f'Source PDF page | {source_page} / {source_total} | {current_pct}%'
            log_text = f'Preview OCR | sample {sample_index} / {sample_total} | source PDF page {source_page} / {source_total} | current page {current_pct}% | preview task {preview_task_pct:.1f}% | whole book OCR 0.0% | {state}'
        else:
            processed = max(float(completed), max(0.0, float(source_page - 1)) + current_pct / 100.0)
            overall_pct = max(0.0, min(100.0, processed / max(1, source_total) * 100.0))
            overall_text = f'Full-book OCR | {completed} / {source_total} pages | {overall_pct:.1f}%'
            current_text = f'Current PDF page | {source_page} / {source_total} | {current_pct}%'
            log_text = f'Full OCR | page {source_page} / {source_total} | current page {current_pct}% | whole book {overall_pct:.1f}% | {state}'
        self._set_project_overall_percent(overall_pct)
        self._set_status_item_percent(current_pct)
        self.overall_label.config(text=overall_text)
        self.current_label.config(text=current_text)
        self._set_status_message(f'OCR page {source_page} / {source_total}', percent=current_pct)
        if hasattr(self, 'parts') and source_page > 0:
            iid = f'ocr-page-{source_page:04d}'
            values = (f'{source_page} / {source_total}', f'{current_pct}%')
            if self.parts.exists(iid):
                self.parts.item(iid, values=values, tags=('running',))
            else:
                self.parts.insert('', 'end', iid=iid, values=values, tags=('running',))
        now = time.monotonic()
        page_changed = source_page != int(getattr(self, '_last_ocr_log_page', 0) or 0)
        stage_changed = state != getattr(self, '_last_ocr_log_state', '')
        heartbeat_due = from_tick and (now - float(getattr(self, '_last_ocr_heartbeat_at', 0.0) or 0.0) >= float(os.environ.get('KR_B2A_OCR_HEARTBEAT_SECONDS', '10')))
        if page_changed or stage_changed or heartbeat_due:
            self._last_ocr_log_page = source_page
            self._last_ocr_log_state = state
            self._last_ocr_heartbeat_at = now
            self._log_event(log_text)

    def install_or_repair_ocr(self) -> None:
        def done(report: dict[str, object]) -> None:
            self.ocr_reason.config(text='Local OCR foundation verified. Re-analyzing the selected source.')
            if self.source.get().strip():
                self.analyze_ocr()
        self._run('Install / repair local OCR foundation', install_or_repair_foundation, done)

    def open_ocr_resource_folder(self) -> None:
        try:
            open_in_file_manager(local_ocr_foundation().resource_root)
        except Exception as exc:
            messagebox.showerror('Open OCR resource folder', str(exc))

    def open_ocr_output_folder(self) -> None:
        path = self.ocr_last_output_dir
        if not path or not Path(path).is_dir():
            messagebox.showinfo('OCR results folder', 'OCR results are not available yet. Run the 3-page preview or full OCR first.')
            return
        try:
            open_in_file_manager(Path(path))
        except Exception as exc:
            messagebox.showerror('Open OCR results folder', str(exc))

    def _set_ocr_provider_options(self, analysis: OCRAnalysis) -> None:
        labels = {provider_id: spec.label for provider_id, spec in OCR_PROVIDER_SPECS.items()}
        self.ocr_provider_by_label.clear()
        ordered = []
        for provider_id, data in analysis.capabilities.items():
            if provider_id not in OCR_PROVIDER_SPECS or not data.get('available') or provider_id == 'native-text':
                continue
            label = provider_display_label(provider_id, recommended_provider=analysis.recommended_provider, labels=labels)
            ordered.append(label)
            self.ocr_provider_by_label[label] = provider_id
        self.ocr_override_combo['values'] = ordered
        recommended = next((label for label, provider_id in self.ocr_provider_by_label.items() if provider_id == analysis.recommended_provider), '')
        self.ocr_override.set(recommended or (ordered[0] if ordered else 'No local OCR engine available'))

    def analyze_ocr(self) -> None:
        value = self.source.get().strip()
        if not value:
            messagebox.showerror('No book', 'Select a book first.')
            return
        source = Path(value)
        self.ocr_source_before_output = source
        def done(analysis: OCRAnalysis):
            self.ocr_analysis = analysis
            self.ocr_preview_report = None
            self.ocr_last_output_dir = None
            recommended = analysis.recommended_provider or 'none'
            self.ocr_status.config(text=f'Status: {analysis.status} · language: {analysis.language} · recommended: {recommended}')
            self.ocr_reason.config(text=analysis.reason)
            self._set_ocr_provider_options(analysis)
            self._render_ocr_ui_state()
        self._run('Analyze OCR requirements', lambda: analyze_source(source), done)

    def toggle_ocr_advanced(self) -> None:
        self.advanced_ocr_visible = not self.advanced_ocr_visible
        if self.advanced_ocr_visible:
            self.ocr_advanced.grid(row=6, column=0, columnspan=6, sticky='ew', padx=6, pady=(0, 5))
            self.ocr_advanced_button.config(text='Advanced ▲')
        else:
            self.ocr_advanced.grid_forget()
            self.ocr_advanced_button.config(text='Advanced')

    def _selected_ocr_provider(self) -> str | None:
        return self.ocr_provider_by_label.get(self.ocr_override.get()) or (self.ocr_analysis.recommended_provider if self.ocr_analysis else None)

    def _preview_work_dir(self, source: Path) -> Path:
        from .utils import sanitize_filename
        return Path(self.work_root.get()) / '_ocr_work' / sanitize_filename(source.stem, 'book') / 'preview'

    def _full_work_dir(self, source: Path) -> Path:
        from .utils import sanitize_filename
        return Path(self.work_root.get()) / '_ocr_work' / sanitize_filename(source.stem, 'book') / 'full'

    def _show_ocr_sample_review(self, report: dict[str, object]) -> None:
        window = tk.Toplevel(self.root)
        window.title('Preview OCR sample')
        self._place_child_dialog_at_main_window_top_left(window)
        ttk.Label(window, text='Preview OCR sample completed. Review the extracted sample text before running full OCR.', wraplength=720).pack(fill='x', padx=10, pady=(10, 5))
        text = tk.Text(window, wrap='word', height=24)
        text.insert('1.0', str(report.get('preview_text') or ''))
        text.config(state='disabled')
        text.pack(fill='both', expand=True, padx=10, pady=6)
        actions = ttk.Frame(window); actions.pack(fill='x', padx=10, pady=(0, 10))
        def run_full() -> None:
            window.destroy(); self.root.after(10, self.run_ocr)
        ttk.Button(actions, text='Run full OCR', command=run_full).pack(side='left', padx=(0, 6))
        ttk.Button(actions, text='Preview again', command=window.destroy).pack(side='left', padx=6)
        ttk.Button(actions, text='Close', command=window.destroy).pack(side='right')
        window.grab_set()

    def preview_ocr(self) -> None:
        if not self.ocr_analysis:
            messagebox.showerror('OCR not analyzed', 'Run Analyze book source first.'); return
        provider = self._selected_ocr_provider()
        if not provider or provider == 'native-text':
            messagebox.showerror('OCR provider unavailable', 'No local OCR provider is available. Open Advanced and run Install / repair local OCR foundation.'); return
        source = self.ocr_source_before_output or Path(self.source.get())
        output_dir = self._preview_work_dir(source)
        self._set_ocr_operation('preview')
        def done(report: dict[str, object]) -> None:
            self._set_ocr_operation(None)
            self.ocr_preview_report = report
            self.ocr_last_output_dir = Path(str(report.get('output_dir') or output_dir))
            self._finalize_ocr_progress('Preview OCR sample completed', project_percent=0)
            self._render_ocr_ui_state()
            self._render_workflow_state()
            self._show_ocr_sample_review(report)
        self._run('Preview OCR sample', lambda: preview_sample_ocr(source, self.ocr_analysis, provider_id=provider, progress=self._cancellable_ocr_progress_event, output_dir=output_dir), done)

    def pause_ocr(self) -> None:
        if self.ocr_operation_kind != 'full' or not self.ocr_control:
            return
        self.ocr_control.pause()
        self.ocr_paused = True
        self._log_event('OCR pause requested. The current page will finish, then processing will pause at the next durable checkpoint.')
        self._render_ocr_ui_state()

    def resume_ocr(self) -> None:
        if self.ocr_operation_kind != 'full' or not self.ocr_control:
            return
        self.ocr_control.resume()
        self.ocr_paused = False
        self._log_event('OCR resume requested.')
        self._render_ocr_ui_state()

    def cancel_ocr(self) -> None:
        if not self.ocr_control:
            return
        self.ocr_control.cancel()
        self._log_event('OCR cancel requested. Completed page checkpoints will be preserved.')

    def run_ocr(self) -> None:
        if not self.ocr_analysis:
            messagebox.showerror('OCR not analyzed', 'Run Analyze book source first.'); return
        provider = self._selected_ocr_provider()
        if self.ocr_analysis.status in {'not-needed', 'not-applicable'} or provider in {None, 'native-text'}:
            messagebox.showinfo('OCR not required', 'OCR is not required for this source. The usable native text layer will be preserved.')
            self._log_event('OCR not required. Native text layer preserved.'); return
        source = self.ocr_source_before_output or Path(self.source.get())
        work_output_dir = self._full_work_dir(source)
        export_output_dir = ocr_results_dir(Path(self.export_root.get()), source)
        keep_awake = bool(self.keep_awake.get())
        analysis = self.ocr_analysis
        self.ocr_control = OCRControl()
        self._set_ocr_operation('full')
        def done(path: Path):
            self._set_ocr_operation(None)
            self.ocr_last_output_dir = Path(path).parent
            self.ocr_analysis = OCRAnalysis('completed', analysis.source_format, analysis.language, provider, 'OCR completed. Final review text was exported under Export root.', analysis.sample_pages, analysis.capabilities, analysis.embedded_text_score)
            self._suppress_source_trace = True
            try:
                self.source.set(str(path))
            finally:
                self._suppress_source_trace = False
            self._finalize_ocr_progress('Full OCR completed', project_percent=100)
            self.ocr_status.config(text='Status: OCR output ready - next step: Prepare text')
            self.ocr_reason.config(text=f'Final OCR review text exported under Export root: {path}')
            self._render_ocr_ui_state(); self._render_workflow_state()
            self._show_ocr_completion_dialog(path)
        self._run('Run full OCR', lambda: run_recommended_ocr(source, analysis, output_dir=work_output_dir, export_dir=export_output_dir, provider_id=provider, keep_awake=keep_awake, progress=self._cancellable_ocr_progress_event, control=self.ocr_control), done)

    def prepare(self, layout_mode: str | None = None) -> None:
        value = self.source.get().strip()
        if not value:
            messagebox.showerror('No book', 'Select a book first.'); return
        if Path(value).suffix.lower() == '.pdf' and self.ocr_analysis is None:
            messagebox.showerror('Analyze source first', 'Analyze the selected PDF before preparing text.'); return
        if self.ocr_analysis and self.ocr_analysis.status == 'required':
            messagebox.showerror('OCR required', 'This image-only PDF requires OCR first. Run the 3-page preview and then Run full OCR.'); return
        layout_mode = layout_mode or self._prepare_layout_mode()
        self.cleaned_text_opened = False
        self._save_runtime_cfg(); self._reset_part_view()
        work_root = Path(self.work_root.get()); export_root = Path(self.export_root.get())
        processing_profile = self._profile_id(); dictionary_path = self._dict()
        self._prepare_watchdog_token = int(getattr(self, '_prepare_watchdog_token', 0) or 0) + 1
        token = self._prepare_watchdog_token
        self._prepare_started_at = time.monotonic()
        self._append_prepare_trace('started', f'source={value}; layout_mode={layout_mode}')
        def work():
            try:
                self.job = prepare_job(Path(value), work_root=work_root, export_root=export_root, processing_profile=processing_profile, dictionary_path=dictionary_path, layout_mode=layout_mode)
                result = job_status(self.job)
                self._append_prepare_trace('completed', f'job={self.job.root}')
                return result
            except Exception as exc:
                self._append_prepare_trace('error', f'{type(exc).__name__}: {exc}')
                raise
        def done(_report: dict) -> None:
            self._append_prepare_trace('ui-completed', 'Prepare text completed and workflow state refreshed.')
            self._render_workflow_state()
        label = f"Prepare text · {PREPARE_MODE_BY_ID.get(layout_mode, 'Auto smart cleanup')}"
        self._run(label, work, done)
        if str(getattr(self.busy, 'label', '') or '').startswith('Prepare text'):
            self.root.after(5000, lambda: self._prepare_watchdog_tick(token))

    def open_proofread(self) -> None:
        job = self._job_required()
        if job: os.startfile(job.proofread) if os.name == 'nt' else subprocess.Popen(['xdg-open', str(job.proofread)])

    def approve_proofread(self) -> None:
        job = self._job_required()
        if job:
            dictionary_path = self._dict()
            self._run('Approve reviewed text & rebuild', lambda: approve_proofread_and_rebuild(job, dictionary_path=dictionary_path))

    def apply_cleanup(self, kind: str) -> None:
        job = self._job_required()
        if job:
            dictionary_path = self._dict()
            self._run(f'Apply cleanup: {kind}', lambda: apply_cleanup_and_rebuild(job, kind=kind, dictionary_path=dictionary_path))

    def apply_all_cleanup(self) -> None:
        job = self._job_required()
        if not job: return
        analysis = job_status(job).get('cleanup_analysis', {})
        kinds=[]
        if analysis.get('repeated_headers_and_junk', {}).get('status') == 'recommended': kinds.append('repeated-headers-and-junk')
        if analysis.get('metadata_datetime_tags', {}).get('status') == 'recommended': kinds.append('metadata-date-time-tags')
        if not kinds: messagebox.showinfo('Cleanup', 'No high-confidence cleanup is recommended.'); return
        dictionary_path = self._dict()
        def work():
            reports=[]
            for kind in kinds: reports.append(apply_cleanup_and_rebuild(job, kind=kind, dictionary_path=dictionary_path))
            return reports
        self._run('Apply all recommended cleanup', work)

    def _audition_request_snapshot(self) -> dict[str, str]:
        return dict(self._current_speech_controls())

    def _edge_sample_cache(self) -> EdgeSampleCache:
        # New cache root invalidates stale English-preview MP3 files from earlier builds.
        return EdgeSampleCache(Path(self.work_root.get()) / '_tts_samples' / 'edge-online-native-locale-v17')

    def _voice_sample_progress_event(self, payload: dict) -> None:
        normalized = dict(payload or {})
        thread_local = getattr(self, '_v23_thread_local', None)
        generation = int(getattr(thread_local, 'generation', self._current_operation_generation()) or 0)
        normalized['_operation_generation'] = generation
        if generation != self._current_operation_generation() or self._cancel_event().is_set():
            return
        normalized['event'] = 'voice-sample-progress'
        normalized['state'] = 'voice-sample-progress'
        self.events.put(('voice-sample-progress', 'Play voice sample', normalized, None))

    def _update_voice_sample_progress(self, payload: dict) -> None:
        stage = str(payload.get('stage') or payload.get('state') or 'working')
        elapsed = float(payload.get('elapsed_seconds') or 0.0)
        bytes_received = int(payload.get('bytes_received') or 0)
        index = int(payload.get('index') or 0)
        total = int(payload.get('total') or 0)
        percent = (index / total * 100.0) if total else (100.0 if stage in {'done','completed'} else 10.0)
        self._set_visible_progress(percent)
        text = f'Voice samples: {stage} | {index} / {total}' if total else f'Voice sample: {stage} | elapsed {int(elapsed)} sec | {bytes_received} bytes'
        self.status.config(text=text)
        key = (stage, index, total, int(elapsed) // 10, bytes_received // 65536)
        if getattr(self, '_voice_sample_progress_log_key', None) != key:
            self._voice_sample_progress_log_key = key
            self._log_event(text)

    def _block_root_window_wheel(_event: object) -> str:
        return 'break'

    def _voice_preview_volume_0_to_1000(self) -> int:
        percent = self._percent_text_to_int(self.volume.get())
        return max(0, min(1000, 1000 + percent * 10))

    def _stop_local_voice_sample_in_app(self) -> None:
        if os.name != 'nt':
            return
        try:
            import ctypes
            ctypes.windll.winmm.mciSendStringW('close kr_b2a_voice_sample', None, 0, None)
        except Exception:
            pass

    def _play_local_voice_sample_in_app(self, path) -> None:
        if os.name != 'nt':
            return
        import ctypes
        alias = 'kr_b2a_voice_sample'
        self._stop_local_voice_sample_in_app()
        target = str(path).replace('"', '')
        mci = ctypes.windll.winmm.mciSendStringW
        error = mci(f'open "{target}" type mpegvideo alias {alias}', None, 0, None)
        if error:
            raise RuntimeError(f'Windows in-app sample player could not open the local sample: MCI {error}')
        mci(f'setaudio {alias} volume to {self._voice_preview_volume_0_to_1000()}', None, 0, None)
        error = mci(f'play {alias}', None, 0, None)
        if error:
            self._stop_local_voice_sample_in_app()
            raise RuntimeError(f'Windows in-app sample player could not play the local sample: MCI {error}')

    def _invalidate_analysis_after_reload(self) -> None:
        for name in (
            'analysis', 'analysis_result', 'book_analysis', 'source_analysis',
            'current_analysis', 'prepared_text', 'cleaned_text', 'current_job',
        ):
            if hasattr(self, name):
                try:
                    setattr(self, name, None)
                except Exception:
                    pass
        for name in ('analysis_ready', 'text_analyzed', 'prepare_ready'):
            if hasattr(self, name):
                try:
                    setattr(self, name, False)
                except Exception:
                    pass
        for name in ('analyze_button', 'analyze_book_button', 'analyze_text_button'):
            button = getattr(self, name, None)
            if button is not None:
                try:
                    button.config(state='normal')
                except Exception:
                    pass
        for name in ('prepare_button', 'prepare_text_button'):
            button = getattr(self, name, None)
            if button is not None:
                try:
                    button.config(state='disabled')
                except Exception:
                    pass

    def _sync_recommended_cleanup_buttons(self) -> None:
        self._render_cleanup_action_state()

    def _apply_owner_ui_runtime_contract(self) -> None:
        if not getattr(self, '_owner_ui_runtime_contract_applied', False):
            self._owner_ui_runtime_contract_applied = True
            self.operation_generation = int(getattr(self, 'operation_generation', 0) or 0)
            self._restore_window_state()
            root = self.root
            binder = getattr(root, 'bind', None)
            if callable(binder):
                binder('<MouseWheel>', self._block_root_window_wheel, add='+')
                binder('<Button-4>', self._block_root_window_wheel, add='+')
                binder('<Button-5>', self._block_root_window_wheel, add='+')
                binder('<Configure>', self._schedule_window_state_save, add='+')
        self._sync_recommended_cleanup_buttons()
        self._render_reload_button()

    def _percent_text_to_int(self, raw: object) -> int:
        try:
            return int(str(raw or '0').strip().replace('%', '').replace('+', '') or '0')
        except ValueError:
            return 0

    def _rate_slider_changed(self, value: object) -> None:
        self.rate.set(f'{int(float(value)):+d}%')

    def _volume_slider_changed(self, value: object) -> None:
        self.volume.set(f'{int(float(value)):+d}%')

    def _set_visible_progress(self, value: object) -> None:
        try:
            percent = max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            percent = 0.0
        for name in ('status_overall_progress', 'log_progress', 'overall_progress'):
            widget = getattr(self, name, None)
            if widget is not None:
                try:
                    widget['value'] = percent
                except Exception:
                    pass

    def _audio_playback_volume_0_to_1000(self) -> int:
        variable = getattr(self, 'audio_playback_volume', None)
        try:
            return max(0, min(1000, int(variable.get()) * 10)) if variable is not None else 1000
        except Exception:
            return 1000

    def _audio_playback_volume_changed(self, _value: object = None) -> None:
        if os.name != 'nt':
            return
        try:
            import ctypes
            ctypes.windll.winmm.mciSendStringW(f'setaudio kr_b2a_voice_sample volume to {self._audio_playback_volume_0_to_1000()}', None, 0, None)
        except Exception:
            pass

    def _part_one_audio_path(self) -> Path | None:
        if not self.job:
            return None
        path = self.job.parts_audio / 'part-0001.mp3'
        return path if path.is_file() else None

    def play_part_one_audio(self) -> None:
        path = self._part_one_audio_path()
        if path is None:
            messagebox.showinfo('Part 1 playback', 'Preview Part 1 first.')
            return
        self._play_local_voice_sample_in_app(path)
        self._audio_playback_volume_changed()
        self._render_audio_playback_state()

    def pause_audio_playback(self) -> None:
        if os.name == 'nt':
            try:
                import ctypes
                ctypes.windll.winmm.mciSendStringW('pause kr_b2a_voice_sample', None, 0, None)
            except Exception:
                pass

    def stop_audio_playback(self) -> None:
        self._stop_local_voice_sample_in_app()
        self._render_audio_playback_state()

    def _render_audio_playback_state(self) -> None:
        ready = self._part_one_audio_path() is not None
        for name in ('audio_play_button', 'audio_pause_button', 'audio_stop_button'):
            button = getattr(self, name, None)
            if button is not None:
                try:
                    button.config(state='normal' if ready else 'disabled')
                except Exception:
                    pass

    def _set_project_overall_percent(self, value: object) -> None:
        try:
            percent = max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            percent = 0.0
        widget = getattr(self, 'log_progress', None)
        if widget is not None:
            try:
                widget['value'] = percent
            except Exception:
                pass

    def _set_status_item_percent(self, value: object) -> None:
        try:
            percent = max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            percent = 0.0
        widget = getattr(self, 'status_current_progress', None)
        if widget is not None:
            try:
                widget['value'] = percent
            except Exception:
                pass
        if self._audio_status_active():
            self._sync_current_part_status_percent(getattr(self, 'current_index', None), percent)

    def _sync_current_part_status_percent(self, index: object, value: object) -> None:
        parts = getattr(self, 'parts', None)
        if parts is None:
            return
        try:
            part_index = int(index)
        except (TypeError, ValueError):
            return
        if part_index <= 0:
            return
        try:
            percent = max(0, min(100, int(float(value))))
        except (TypeError, ValueError):
            return
        highlight = 'running' if percent < 100 else None
        try:
            self._set_part_state(part_index, f'{percent}%', highlight=highlight)
        except Exception:
            return

    def _set_status_message(self, text: object, *, percent: object | None = None) -> None:
        if self._audio_status_active():
            if percent is not None:
                try:
                    self.current_estimate = max(0, min(100, int(float(percent))))
                except (TypeError, ValueError):
                    pass
            self._render_audio_status_summary()
            return
        message = str(text or '')
        if percent is not None:
            try:
                prefix = f'{max(0.0, min(100.0, float(percent))):.1f}%'
            except (TypeError, ValueError):
                prefix = '0.0%'
            message = prefix if not message else f'{prefix} | {message}'
        self._status_message = message or '0%'
        self._status_marquee_offset = 0
        self._render_status_marquee()

    def _render_status_marquee(self) -> None:
        if self._audio_status_active():
            self._render_audio_status_summary()
            return
        label = getattr(self, 'status', None)
        if label is None:
            return
        message = str(getattr(self, '_status_message', '') or '0%')
        width = 52
        if len(message) <= width:
            visible = message
        else:
            padded = message + '     '
            offset = int(getattr(self, '_status_marquee_offset', 0) or 0) % len(padded)
            visible = (padded + padded)[offset:offset + width]
        try:
            label.config(text=visible, width=width)
        except Exception:
            pass

    def _status_marquee_tick(self) -> None:
        if self._audio_status_active():
            self._render_audio_status_summary()
            self.root.after(350, self._status_marquee_tick)
            return
        message = str(getattr(self, '_status_message', '') or '')
        if len(message) > 52:
            self._status_marquee_offset = int(getattr(self, '_status_marquee_offset', 0) or 0) + 1
        self._render_status_marquee()
        self.root.after(350, self._status_marquee_tick)

    def _status_percent_from_state(self, state: object) -> int:
        text = str(state or '')
        match = re.search(r'(\d{1,3})(?:\.\d+)?%', text)
        if match:
            return max(0, min(100, int(match.group(1))))
        lowered = text.lower()
        if 'done' in lowered or 'completed' in lowered or 'recognized' in lowered or 'reused' in lowered:
            return 100
        if 'validating' in lowered:
            return 95
        return 0

    def _project_tts_overall_percent(self, index: int, current_percent: float) -> float:
        total = max(1, int(getattr(self, '_audio_total_parts_cache', 0) or 0), int(index or 1))
        completed = max(0, min(total, int(getattr(self, '_audio_completed_parts_cache', 0) or 0)))
        fractional = float(completed)
        if int(index or 1) > completed:
            fractional += max(0.0, min(100.0, float(current_percent))) / 100.0
        return max(0.0, min(100.0, fractional / float(total) * 100.0))

    def open_cleaned_text_and_advance(self) -> None:
        job = self._job_required()
        if not job:
            return
        self.open_proofread()
        self.cleaned_text_opened = True
        self._render_workflow_state()

    def _checkpoint_interrupted_before_reload(self) -> None:
        label = str(self.busy.label or '')
        if getattr(self, 'ocr_control', None) is not None:
            try:
                self.ocr_control.cancel()
            except Exception:
                pass
        if self.job:
            try:
                append_job_log(self.job, 'manual-reload-interrupted', operation=label, state='interrupted-or-incomplete')
            except Exception:
                pass
        self._log_event(f'Reload requested. Preserving interrupted or incomplete task evidence: {label or "idle"}.')

    def _window_state_path(self) -> Path:
        root = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local')) / 'KRBookToAudio'
        root.mkdir(parents=True, exist_ok=True)
        return root / 'window_state_v3.json'

    def _save_window_state_now(self) -> None:
        root = getattr(self, 'root', None)
        geometry = getattr(root, 'geometry', None)
        if not callable(geometry):
            return
        try:
            import json
            value = str(geometry() or '')
            if not re.match(r'^\\d+x\\d+[+-]\\d+[+-]\\d+$', value):
                return
            path = self._window_state_path()
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps({'geometry': value}, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')
            replace_with_retry(temp, path)
        except Exception:
            pass

    def _schedule_window_state_save(self, event: object = None) -> None:
        root = getattr(self, 'root', None)
        if event is not None and getattr(event, 'widget', root) is not root:
            return
        after_cancel = getattr(root, 'after_cancel', None)
        token = getattr(self, '_window_state_after_id', None)
        if token is not None and callable(after_cancel):
            try:
                after_cancel(token)
            except Exception:
                pass
        after = getattr(root, 'after', None)
        if callable(after):
            try:
                self._window_state_after_id = after(450, self._save_window_state_now)
            except Exception:
                self._window_state_after_id = None

    def _restore_window_state(self) -> None:
        root = getattr(self, 'root', None)
        geometry = getattr(root, 'geometry', None)
        minsize = getattr(root, 'minsize', None)
        title = getattr(root, 'title', None)
        if callable(title):
            title('KR Book To Audio 3.3')
        if callable(minsize):
            minsize(1480, 1260)
        target = '1580x1260'
        try:
            import json
            path = self._window_state_path()
            payload = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
            saved = str(payload.get('geometry') or '')
            match = re.match(r'^(\\d+)x(\\d+)([+-]\\d+)([+-]\\d+)$', saved)
            if match:
                width = max(1480, int(match.group(1)))
                height = max(1260, int(match.group(2)))
                target = f'{width}x{height}{match.group(3)}{match.group(4)}'
        except Exception:
            target = '1580x1260'
        if callable(geometry):
            geometry(target)

    def _current_operation_generation(self) -> int:
        return int(getattr(self, 'operation_generation', 0) or 0)

    def _cancel_event(self):
        event = getattr(self, '_v23_cancel_event', None)
        if event is None:
            event = threading.Event()
            self._v23_cancel_event = event
        return event

    def _stop_mci_alias(self, alias: str) -> None:
        if os.name != 'nt':
            return
        try:
            import ctypes
            ctypes.windll.winmm.mciSendStringW(f'stop {alias}', None, 0, None)
            ctypes.windll.winmm.mciSendStringW(f'close {alias}', None, 0, None)
        except Exception:
            pass

    def _stop_all_activity_now(self, *, reason: str, preserve_incomplete: bool) -> None:
        old_label = str(getattr(self.busy, 'label', '') or '')
        self.operation_generation = self._current_operation_generation() + 1
        self.reload_generation = int(getattr(self, 'reload_generation', 0) or 0) + 1
        self._cancel_event().set()
        self._log_event(f'{reason}: stopping all active work immediately.')
        self._stop_mci_alias('kr_b2a_voice_sample')
        try:
            self._stop_local_voice_sample_in_app()
        except Exception:
            pass
        control = getattr(self, 'ocr_control', None)
        if control is not None:
            try:
                control.cancel()
                self._log_event(f'{reason}: requested OCR cancellation at the next durable page checkpoint.')
            except Exception:
                pass
        for name in ('_active_subprocess', 'active_process', 'provider_process', '_ocr_process', '_tts_process'):
            process = getattr(self, name, None)
            if process is None:
                continue
            try:
                if hasattr(process, 'poll') and process.poll() is not None:
                    continue
                if hasattr(process, 'terminate'):
                    process.terminate()
                if hasattr(process, 'kill') and hasattr(process, 'poll') and process.poll() is None:
                    process.kill()
                self._log_event(f'{reason}: terminated tracked child process {name}.')
            except Exception:
                pass
        self._interrupt_active_worker_threads(reason=reason)
        if preserve_incomplete and self.job:
            try:
                append_job_log(self.job, 'manual-reload-interrupted', operation=old_label, state='interrupted-or-incomplete')
                self._log_event(f'{reason}: preserved the current task as interrupted or incomplete.')
            except Exception:
                pass
        try:
            with self.events.mutex:
                self.events.queue.clear()
        except Exception:
            pass
        try:
            self.telemetry_mailbox = LatestTelemetryMailbox()
        except Exception:
            pass
        self.ocr_progress_snapshot = {}
        self.ocr_progress_token = int(getattr(self, 'ocr_progress_token', 0) or 0) + 1
        try:
            self.busy.finish()
        except Exception:
            pass
        self._set_actions_enabled(True)
        self._render_reload_button()
        self._set_project_overall_percent(0)
        self._set_status_item_percent(0)
        self._set_status_message(f'{reason}: stopped.', percent=0)
        self._render_audio_playback_state()

    def _ocr_truthful_total_pages(self, payload: dict[str, object], snapshot: object) -> int:
        candidates = [getattr(snapshot, 'total_pdf_pages', 0)]
        for key in ('total_pdf_pages', 'total_pages', 'page_count', 'pages', 'pdf_pages'):
            candidates.append(payload.get(key, 0))
        analysis = getattr(self, 'ocr_analysis', None)
        for key in ('total_pdf_pages', 'total_pages', 'page_count', 'pages'):
            candidates.append(getattr(analysis, key, 0) if analysis is not None else 0)
        values = []
        for item in candidates:
            try:
                values.append(int(item or 0))
            except (TypeError, ValueError):
                pass
        return max([1, *values])

    def approve_part_one(self) -> None:
        self._stop_all_activity_now(reason='Approve Part 1', preserve_incomplete=False)
        return self._v23_legacy_approve_part_one()

    def reject_part_one(self) -> None:
        if not self.job:
            return
        if not messagebox.askyesno('Reject Part 1', 'Reject the current Part 1 preview and return to Preview Part 1?\n\nOCR, prepared text and reviewed-text approval will remain preserved.'):
            return
        self._stop_mci_alias('kr_b2a_voice_sample')
        try:
            self._stop_local_voice_sample_in_app()
        except Exception:
            pass
        self._rollback_part_one_preview_only()

    def _interrupt_active_worker_threads(self, *, reason: str) -> None:
        workers = dict(getattr(self, '_active_worker_threads', {}) or {})
        current = threading.current_thread()
        for generation, thread in workers.items():
            if thread is current or not getattr(thread, 'is_alive', lambda: False)():
                continue
            ident = getattr(thread, 'ident', None)
            if not ident:
                continue
            try:
                import ctypes
                result = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(ident), ctypes.py_object(SystemExit))
                if result > 1:
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(ident), None)
                    self._log_event(f'{reason}: worker-thread interrupt rollback requested for generation {generation}.')
                elif result == 1:
                    self._log_event(f'{reason}: worker-thread interrupt requested for generation {generation}.')
            except Exception:
                pass

    def _raise_if_cancelled(self) -> None:
        if self._cancel_event().is_set():
            raise RuntimeError('Operation cancelled by Owner request.')

    def _cancellable_progress_event(self, payload: dict) -> None:
        self._raise_if_cancelled()
        self._progress_event(payload)

    def _cancellable_ocr_progress_event(self, payload: dict[str, object]) -> None:
        self._raise_if_cancelled()
        self._ocr_progress_event(payload)

    def _source_pdf_total_pages(self, payload: dict[str, object] | None = None, snapshot: object = None) -> int:
        cache = getattr(self, '_source_pdf_total_pages_cache', None)
        source = str((getattr(self, 'ocr_source_before_output', None) or Path(self.source.get())).resolve()) if self.source.get().strip() else ''
        if cache and cache.get('source') == source and int(cache.get('pages') or 0) > 0:
            return int(cache['pages'])
        candidates = []
        payload = dict(payload or {})
        for key in ('source_total_pages', 'pdf_total_pages', 'total_pdf_pages', 'total_pages', 'page_count', 'pages', 'pdf_pages'):
            candidates.append(payload.get(key, 0))
        analysis = getattr(self, 'ocr_analysis', None)
        for key in ('source_total_pages', 'pdf_total_pages', 'total_pdf_pages', 'total_pages', 'page_count', 'pages'):
            candidates.append(getattr(analysis, key, 0) if analysis is not None else 0)
        if source:
            try:
                from .extractors import diagnose
                candidates.append(diagnose(Path(source)).get('pages', 0))
            except Exception:
                pass
        values = []
        for item in candidates:
            try:
                value = int(item or 0)
                if value > 0:
                    values.append(value)
            except (TypeError, ValueError):
                pass
        pages = max(values or [1])
        self._source_pdf_total_pages_cache = {'source': source, 'pages': pages}
        return pages

    def _preview_sample_position(self, source_page: int) -> tuple[int, int]:
        analysis = getattr(self, 'ocr_analysis', None)
        pages = [int(item) for item in (getattr(analysis, 'sample_pages', None) or []) if str(item).isdigit()]
        if pages and source_page in pages:
            return pages.index(source_page) + 1, len(pages)
        snapshot = dict(getattr(self, 'ocr_progress_snapshot', {}) or {})
        index = int(snapshot.get('sample_index') or snapshot.get('preview_index') or 0)
        total = int(snapshot.get('sample_count') or snapshot.get('preview_total') or len(pages) or 3)
        return max(1, index or 1), max(1, total)

    def _finalize_ocr_progress(self, label: str, *, project_percent: float | None = None) -> None:
        self.ocr_progress_snapshot = {}
        self.ocr_progress_token = int(getattr(self, 'ocr_progress_token', 0) or 0) + 1
        if project_percent is not None:
            self._set_project_overall_percent(project_percent)
        self._set_status_item_percent(100)
        self._set_status_message(label, percent=100)
        self.current_label.config(text=label)

    def _rollback_part_one_preview_only(self) -> None:
        import json
        job = self._job_required()
        if not job:
            return
        try:
            manifest = load_manifest(job)
            audio = manifest.setdefault('audio', {})
            completed = audio.setdefault('completed', {})
            failures = audio.setdefault('failures', {})
            for key in ('1', '0001', 'part-0001', 'part-0001.mp3'):
                completed.pop(key, None); failures.pop(key, None)
            preview = manifest.setdefault('gates', {}).setdefault('preview', {})
            for key in list(preview):
                if 'approved' in str(key).lower() or 'signature' in str(key).lower():
                    preview.pop(key, None)
            temp = job.manifest.with_suffix('.tmp')
            temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            replace_with_retry(temp, job.manifest)
        except Exception as exc:
            self._log_event(f'Reject Part 1: manifest rollback warning: {type(exc).__name__}: {exc}')
        try:
            (job.parts_audio / 'part-0001.mp3').unlink(missing_ok=True)
        except Exception:
            pass
        self._part_one_rejected_pending_preview = True
        self.speech_settings_locked = False
        self._apply_speech_settings_lock()
        self._reset_part_view(); self._refresh_job_view()
        self._set_status_message('Part 1 rejected. Adjust speech settings and preview again.', percent=0)
        self._log_event('Part 1 rejected. Reviewed text remains approved. Next step: Preview Part 1 again.')
        self._render_workflow_state()

    def _reload_blocked_by_active_external_work(self) -> bool:
        label = str(getattr(self.busy, 'label', '') or '').lower()
        if getattr(self, 'ocr_operation_kind', None) in {'preview', 'full'}:
            return True
        external_tokens = (
            'preview part 1',
            'synthesize all',
            'retry failed',
            'resume synthesis',
            'preview ocr',
            'run full ocr',
            'play voice sample',
            'download / refresh edge voice samples',
        )
        return any(token in label for token in external_tokens)

    def _prepare_trace_path(self) -> Path:
        root = Path(self.work_root.get() or local_work_root()) / '_diagnostics'
        root.mkdir(parents=True, exist_ok=True)
        return root / 'prepare-text-heartbeat.log'

    def _append_prepare_trace(self, state: str, detail: str = '') -> None:
        try:
            stamp = time.strftime('%Y-%m-%dT%H:%M:%S')
            self._prepare_trace_path().open('a', encoding='utf-8').write(f'{stamp} | {state} | {detail}\n')
        except Exception:
            pass

    def _prepare_watchdog_tick(self, token: int) -> None:
        if token != int(getattr(self, '_prepare_watchdog_token', 0) or 0):
            return
        if not str(getattr(self.busy, 'label', '') or '').startswith('Prepare text'):
            return
        started = float(getattr(self, '_prepare_started_at', time.monotonic()) or time.monotonic())
        elapsed = max(0, int(time.monotonic() - started))
        text = f'Prepare text is running | elapsed {elapsed} sec'
        self._set_status_message(text)
        if elapsed == 0 or elapsed % 15 < 5:
            self._log_event(text)
            self._append_prepare_trace('heartbeat', text)
        self.root.after(5000, lambda: self._prepare_watchdog_tick(token))

    def _place_child_dialog_at_main_window_top_left(self, window) -> None:
        try:
            window.transient(self.root)
            self.root.update_idletasks(); window.update_idletasks()
            x = int(self.root.winfo_rootx()); y = int(self.root.winfo_rooty())
            window.geometry(f'+{x}+{y}')
            window.lift()
        except Exception:
            pass

    def _show_ocr_completion_dialog(self, path: Path) -> None:
        window = tk.Toplevel(self.root)
        window.title('OCR completed')
        self._place_child_dialog_at_main_window_top_left(window)
        ttk.Label(window, text=f'OCR completed successfully.\n\nFinal review text:\n{path}\n\nNext step: Prepare text.', wraplength=720, justify='left').pack(fill='x', padx=12, pady=12)
        ttk.Button(window, text='OK', command=window.destroy).pack(pady=(0, 12))
        window.grab_set()

    def _audio_status_mode(self) -> str:
        label = str(getattr(self.busy, 'label', '') or '').lower()
        if 'preview part 1' in label:
            return 'Audio preview'
        if 'retry' in label:
            return 'Audio retry'
        return 'Audio synthesis'

    def _audio_status_total_parts(self, mode: str) -> int:
        if mode == 'Audio preview':
            return 1
        try:
            return max(1, int(job_status(self.job).get('parts') or 1)) if self.job else 1
        except Exception:
            return max(1, int(getattr(self, 'current_index', 1) or 1))

    def _set_audio_status_line(self, *, index: int, total: int, percent: int, mode: str = '') -> None:
        self._render_audio_status_summary(index=index, total=total, percent=percent)

    def _audio_status_active(self) -> bool:
        busy = getattr(self, 'busy', None)
        label = str(getattr(busy, 'label', '') or '').lower()
        return any(token in label for token in ('preview part 1', 'synthesize all', 'retry failed', 'resume synthesis'))

    def _audio_status_total_parts_v31(self) -> int:
        busy = getattr(self, 'busy', None)
        label = str(getattr(busy, 'label', '') or '').lower()
        if 'preview part 1' in label:
            return 1
        cached = int(getattr(self, '_audio_total_parts_cache', 0) or 0)
        if cached > 0:
            return cached
        return max(1, int(getattr(self, 'current_index', 1) or 1))

    def _render_audio_status_summary(self, *, index: int | None = None, total: int | None = None, percent: int | None = None) -> None:
        index = max(1, int(index if index is not None else (getattr(self, 'current_index', 1) or 1)))
        total = max(index, int(total if total is not None else self._audio_status_total_parts_v31()))
        percent = max(0, min(100, int(percent if percent is not None else (getattr(self, 'current_estimate', 0) or 0))))
        line = f'Part {index:03d} / {total:03d} | {percent:03d}%'
        self._status_message = line
        self._status_marquee_offset = 0
        try:
            self.status.config(text=line, width=28, anchor='w')
        except Exception:
            pass
        try:
            self.current_label.config(text=line, width=28, anchor='w')
        except Exception:
            pass

    # V31_REMOVE_SAVE_SINGLE_AUTHORITY_AUDIO_STATUS_RUNTIME
    def _seed_audio_progress_cache(self, *, preview: bool = False) -> None:
        total = 1
        completed = 0
        job = getattr(self, 'job', None)
        if not preview and job is not None:
            try:
                status = job_status(job)
                total = max(1, int(status.get('parts') or 1))
                completed = max(0, min(total, int(status.get('completed_audio_parts') or 0)))
            except Exception:
                total = max(1, int(getattr(self, '_audio_total_parts_cache', 1) or 1))
                completed = max(0, int(getattr(self, '_audio_completed_parts_cache', 0) or 0))
        self._audio_total_parts_cache = max(1, total)
        self._audio_completed_parts_cache = max(0, min(self._audio_total_parts_cache, completed))

    # V32_FULL_GRAPH_IDEMPOTENCE_LIGHTWEIGHT_TELEMETRY_RUNTIME
    def refresh_edge_voice_samples(self) -> None:
        if self._tts_engine_id() != 'edge-tts':
            messagebox.showinfo('Edge voice samples', 'Select Microsoft Edge Online TTS first.')
            return
        def work():
            provider = get_tts_provider('edge-tts')
            voices = provider.list_voices()
            return self._edge_sample_cache().refresh_all(provider, voices, progress=self._voice_sample_progress_event)
        self._run('Download / refresh Edge voice samples', work)

    def audition(self) -> None:
        self._save_runtime_cfg()
        output_dir = Path(self.work_root.get()) / '_audition'
        request = self._audition_request_snapshot()
        def work() -> Path:
            if request.get('provider_id') == 'edge-tts':
                locale = next((str(item.get('locale') or '') for item in self.voice_records if str(item.get('short_name') or '') == request.get('voice')), '')
                path = self._edge_sample_cache().generate(get_tts_provider('edge-tts'), voice=request['voice'], locale=locale, rate=request['rate'], pitch=request['pitch'], volume=request['volume'], progress=self._voice_sample_progress_event)
            else:
                path = Path(audition_sample(output_dir=output_dir, **request))
            if not Path(path).is_file() or Path(path).stat().st_size <= 0:
                raise RuntimeError('Voice preview audio was not generated.')
            return Path(path)
        def done(path: Path) -> None:
            self._play(Path(path))
        self._run('Play voice sample', work, done)

    def _play(self, path: Path) -> str:
        self._play_local_voice_sample_in_app(path) if os.name == 'nt' else subprocess.Popen(['xdg-open', str(path)])
        return str(path)

    def preview(self) -> None:
        job = self._job_required()
        if not job:
            return
        self._seed_audio_progress_cache(preview=True)
        request = self._speech_request_snapshot()
        self.speech_settings_locked = True
        self._apply_speech_settings_lock()
        self.preview_playback_token += 1
        playback_token = self.preview_playback_token
        def work():
            return synthesize_parts(job, start=1, end=1, require_preview_approval=False, progress=self._cancellable_progress_event, **request)
        def done(result: dict) -> None:
            if result.get('failures') or playback_token == self.last_played_preview_token or self._cancel_event().is_set():
                return
            self._part_one_rejected_pending_preview = False
            self.last_played_preview_token = playback_token
            self._render_workflow_state()
            self._play(job.parts_audio / 'part-0001.mp3')
        self._run('Preview Part 1', work, done)

    def _restart_current_book(self, *, reason: str) -> None:
        value = self.source.get().strip()
        if not value:
            messagebox.showerror('No book', 'Select a book first.'); return
        self.job = None
        self.speech_settings_locked = False
        self.cleanup_analysis = {}
        self.cleaned_text_opened = False
        self.ocr_analysis = None; self.ocr_preview_report = None; self.ocr_last_output_dir = None
        self.ocr_operation_kind = None; self.ocr_control = None; self.ocr_paused = False
        self._reset_part_view(); self._apply_speech_settings_lock(); self._render_cleanup({})
        self._invalidate_analysis_after_reload()
        self.ocr_status.config(text='Status: Not analyzed')
        self.ocr_reason.config(text='Next step: Analyze text from the selected book source.')
        self._log_event(f'Reloaded current book: {reason}. Analyze text is required before Prepare text.')
        self._set_status_message('Reloaded. Next step: Analyze text.', percent=0)
        self.refresh_recent_jobs(); self._render_workflow_state()

    def reload_current_book(self) -> None:
        if not self.source.get().strip():
            messagebox.showerror('No book', 'Select a book first.'); return
        if self._reload_blocked_by_active_external_work():
            self._log_event('Reload book is unavailable while OCR or audio work is active. Wait for the current durable step to finish, then reload.')
            messagebox.showinfo('Reload unavailable', 'Reload book is disabled while OCR or audio work is active. Wait for the current durable step to finish, then reload.')
            self._render_reload_button()
            return
        self._stop_all_activity_now(reason='Reload book', preserve_incomplete=True)
        self._restart_current_book(reason='manual reload')

    def _v23_legacy_reject_part_one(self) -> None:
        if not self.job:
            return
        if not messagebox.askyesno('Reject Part 1', 'Reject the current Part 1 preview and restart this book?\n\nThe current source and completed OCR text will be preserved. Text-processing and audio-generation state will reset. Previous task files remain archived for diagnostics.'):
            return
        self._log_event('Part 1 rejected. Reloading the current book and unlocking speech settings.')
        self._restart_current_book(reason='Part 1 rejected')

    def _v23_legacy_approve_part_one(self) -> None:
        job = self._job_required()
        if not job:
            return
        controls = self._current_speech_controls()
        def work():
            approval = approve_preview(job, **controls)
            manifest = load_manifest(job)
            parts_total = len(manifest.get('parts', []) or [])
            receipt = single_part_export_receipt(parts_total=parts_total)
            if receipt['single_part_direct_export']:
                merged = str(merge_parts(job))
                append_job_log(job, 'single-part-direct-export', **receipt)
                return {'approval': approval, 'merged': merged, **receipt}
            return {'approval': approval, **receipt}
        def done(report: dict) -> None:
            if report.get('single_part_direct_export'):
                self._log_event('Part 1 approved. Single-Part book detected. Synthesize all skipped. Merge MP3 UI skipped. Final export completed.')
                self.status.config(text='Single-Part export completed. Open final export folder.')
            else:
                self._log_event('Part 1 approved. Next step: Synthesize all remaining Parts.')
        self._run('Approve Part 1', work, done)

    def synthesize(self) -> None:
        job = self._job_required()
        if not job:
            return
        self._seed_audio_progress_cache(preview=False)
        request = self._speech_request_snapshot()
        self._run('Synthesize all parts', lambda: synthesize_parts(job, progress=self._cancellable_progress_event, **request))

    def retry_failed(self) -> None:
        job = self._job_required()
        if job:
            self._seed_audio_progress_cache(preview=False)
            request = self._speech_request_snapshot()
            self._run('Retry failed parts', lambda: retry_failed_parts(job, progress=self._cancellable_progress_event, **request))

    def merge(self) -> None:
        job=self._job_required()
        if job: self._run('Merge MP3', lambda: str(merge_parts(job)))

    def verify_export_action(self) -> None:
        job = self._job_required()
        if job:
            self._run('Verify export', lambda: finalize_export(job, progress=self._progress_event))

    def _load_job(self, job: JobPaths) -> dict | None:
        if not job.manifest.exists():
            messagebox.showerror('Invalid job', 'No _work/job_manifest.json found.')
            return None
        report = recover_job(job)
        self.job = job
        self._reset_part_view()
        manifest = load_manifest(job)
        profile_id = manifest.get('text', {}).get('processing_profile', manifest.get('options', {}).get('processing_profile', DEFAULT_PROCESSING_PROFILE))
        self.profile.set(PROFILE_BY_ID.get(str(profile_id), 'Auto detect · recommended'))
        controls_rehydrated = self._rehydrate_job_speech_controls(job, manifest)
        completed = manifest.get('audio', {}).get('completed', {}) or {}
        preview_gate = manifest.get('gates', {}).get('preview', {}) or {}
        self.speech_settings_locked = bool(completed or preview_gate.get('approved_audio_signature'))
        self._apply_speech_settings_lock()
        self.dictionary.set(manifest.get('text', {}).get('dictionary_path_runtime_only') or '')
        self._refresh_job_view()
        self.refresh_recent_jobs()
        next_part = report.get('next_part')
        if report.get('interrupted') or report.get('stale_lock_removed'):
            self.status.config(text=f'Interrupted task recovered. Resume from Part {next_part or "complete"}.')
        report['speech_controls_rehydrated'] = controls_rehydrated
        if self._job_audio_complete(job) and not export_is_verified(job):
            self.root.after(20, lambda current=job: self._schedule_legacy_export_repair(current))
        self._render_workflow_state()
        return report

    def advanced_recovery(self) -> None:
        proceed = messagebox.askyesno(
            'Advanced recovery',
            'Use this only when a task is missing from Recent jobs. Recover a known job folder manually?',
        )
        if not proceed:
            return
        value = filedialog.askdirectory(title='Recover job from folder', initialdir=self.work_root.get() or str(local_work_root()))
        if value:
            self._load_job(JobPaths.from_root(Path(value)))

    def _job_audio_complete(self, job: JobPaths) -> bool:
        try:
            manifest = load_manifest(job)
        except (FileNotFoundError, RuntimeError, ValueError):
            return False
        expected = len(manifest.get('parts', []))
        completed = len(manifest.get('audio', {}).get('completed', {}))
        failures = bool(manifest.get('audio', {}).get('failures'))
        return bool(expected and completed == expected and not failures)

    def _schedule_legacy_export_repair(self, job: JobPaths, *, open_after: bool = False) -> None:
        if export_is_verified(job):
            if open_after:
                open_in_file_manager(job.export)
            return
        if not self._job_audio_complete(job):
            return
        def done(_report: dict) -> None:
            self._log_event('Legacy export repaired automatically and verified.')
            if open_after:
                open_in_file_manager(job.export)
        self._run('Automatic legacy export finalization', lambda: finalize_export(job, progress=self._progress_event), done)

    def refresh_recent_jobs(self) -> None:
        rebuild_history(Path(self.work_root.get() or local_work_root()))
        self.recent_by_iid.clear()
        for iid in self.recent_jobs.get_children():
            self.recent_jobs.delete(iid)
        rows = list(list_resumable_jobs(include_older_attempts=self.show_older_attempts.get()))
        for idx, item in enumerate(rows):
            iid = f'recent-{idx}'
            self.recent_by_iid[iid] = item
            progress = f"{item.get('completed_parts', 0)} / {item.get('total_parts', 0)}"
            status = display_status(item)
            title = item.get('title')
            self.recent_jobs.insert('', 'end', iid=iid, values=(title, status, progress, format_last_active(item.get('updated_utc'))))

    def _selected_recent(self) -> dict | None:
        selected = self.recent_jobs.selection()
        if not selected:
            messagebox.showinfo('Recent jobs', 'Select a recent job first.')
            return None
        return self.recent_by_iid.get(selected[0])

    def _resume_from_part(self, next_part: int) -> None:
        if not self.job:
            return
        self._seed_audio_progress_cache(preview=False)
        self._log_event(f'Resume requested. Validating checkpoint and continuing from Part {next_part}.')
        job = self.job
        request = self._speech_request_snapshot()
        self._run(f'Resume synthesis from Part {next_part}', lambda: synthesize_parts(job, start=next_part, progress=self._cancellable_progress_event, **request))

    def _start_guided_voice_check(self, next_part: int) -> None:
        if not self.job:
            return
        job = self.job
        controls = self._current_speech_controls()
        def prepared(report: dict) -> None:
            self._log_event(f'Guided voice check ready. Preserved audio remains unchanged. Compare original and candidate Part 1 before approval.')
            self._play(Path(report['existing_part_one']))
            self._play(Path(report['candidate_part_one']))
            approved = messagebox.askyesno(
                'Approve voice and resume?',
                f'Existing audio remains preserved: {len(load_manifest(job).get("audio", {}).get("completed", {}))} parts.\n\n'
                f'Next part: {next_part}\n\n'
                'The preserved Part 1 and a candidate Part 1 preview were opened. Listen to both.\n\n'
                'Do they match closely enough to continue this legacy task with the selected voice controls?',
            )
            if not approved:
                self.status.config(text='Voice check paused. Adjust Voice, Rate, Pitch or Volume, then click Resume selected to compare again. Existing MP3 files remain preserved.')
                return
            def rebound(_report: dict) -> None:
                self._log_event(f'Guided voice verification approved. Resume start: Part {next_part}.')
                self.status.config(text=f'Voice approved. Resuming automatically from Part {next_part}.')
                self._resume_from_part(next_part)
            self._run(
                'Approve legacy voice and resume',
                lambda: approve_legacy_resume_controls(job, **controls),
                rebound,
            )
        self._run(
            'Generate resume voice check',
            lambda: generate_resume_voice_check(job, **controls),
            prepared,
        )

    def resume_selected(self) -> None:
        item = self._selected_recent()
        if not item:
            return
        report = self._load_job(JobPaths.from_root(Path(item['job_root'])))
        if not report or not report.get('next_part') or not self.job:
            messagebox.showinfo('Resume checkpoint', 'This task has no incomplete Part to resume.'); return
        status = job_status(self.job)
        next_part = int(report['next_part'])
        completed = int(status.get('completed_audio_parts') or 0); total = int(status.get('parts') or 0)
        if not status.get('proofread_approved'):
            messagebox.showinfo('Text review required before resume', f'Existing audio preserved: {completed} / {total} parts.\n\nNext part: {next_part}\n\nRequired action:\nOpen cleaned text.\nApprove reviewed text.\n3. Click Resume selected again.')
            self.status.config(text=f'Text review required before resume from Part {next_part}. Existing MP3 files remain preserved.'); return
        if report.get('speech_controls_rehydrated') and status.get('preview_approved') and self._resume_controls_are_approved(self.job):
            if messagebox.askyesno('Resume ready', f'Existing audio verified: {completed} / {total} parts.\n\nResume now from Part {next_part}?'):
                self._resume_from_part(next_part)
            return
        proceed = messagebox.askyesno('Voice check required before resume', f'Existing audio preserved: {completed} / {total} parts.\n\nNext part: {next_part}\n\nThis legacy task does not contain a complete speech-control snapshot.\n\nStart the guided voice check now?')
        if proceed:
            self._start_guided_voice_check(next_part)
        else:
            self.status.config(text=f'Voice check required before resume from Part {next_part}. Existing MP3 files remain preserved.')

    def _open_job_export_or_repair(self, job: JobPaths) -> None:
        if export_is_verified(job) and job.export.exists():
            try:
                open_in_file_manager(job.export)
                self._log_event(f'Opened final export folder: {job.export}')
            except RuntimeError as exc:
                messagebox.showerror('Open output folder', str(exc))
            return
        if self._job_audio_complete(job):
            self.job = job
            self._log_event('Legacy completed task detected. Finalizing export automatically before opening the folder.')
            self._schedule_legacy_export_repair(job, open_after=True)
            return
        proceed = messagebox.askyesno(
            'Final export not ready',
            'Final export has not been created because the task is incomplete. Open the working audio folder instead?',
        )
        if proceed:
            try:
                open_in_file_manager(job.parts_audio)
                self._log_event(f'Opened working audio folder: {job.parts_audio}')
            except RuntimeError as exc:
                messagebox.showerror('Open output folder', str(exc))

    def export_diagnostics_action(self) -> None:
        try:
            if self.job:
                path = export_diagnostic_zip(self.job)
            else:
                path = export_prejob_ocr_diagnostic_zip(Path(self.work_root.get() or local_work_root()))
            self._log_event(f'Exported diagnostic ZIP: {path}')
            messagebox.showinfo('Diagnostic ZIP exported', f'Sanitized diagnostic ZIP written to:\n\n{path}')
        except Exception as exc:
            messagebox.showerror('Export diagnostic ZIP', f'{type(exc).__name__}: {exc}')

    def open_diagnostics_folder(self) -> None:
        folder = diagnostics_root()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            open_in_file_manager(folder)
        except RuntimeError as exc:
            messagebox.showerror('Open diagnostics folder', str(exc))

    def open_selected_output(self) -> None:
        item = self._selected_recent()
        if item:
            self._open_job_export_or_repair(JobPaths.from_root(Path(item['job_root'])))

    def open_current_export(self) -> None:
        job = self._job_required()
        if job:
            self._open_job_export_or_repair(job)

    def remove_selected_history(self) -> None:
        item = self._selected_recent()
        if item and messagebox.askyesno('Remove from history', 'Hide this task from Recent jobs? Task files will not be deleted.'):
            remove_from_history(str(item['job_id']))
            self.refresh_recent_jobs()

    def _startup_recovery(self) -> None:
        reports = scan_and_recover_jobs(Path(self.work_root.get() or local_work_root()))
        self.refresh_recent_jobs()
        interrupted = [item for item in reports if item.get('recovered')]
        if interrupted:
            self.status.config(text=f'{len(interrupted)} interrupted task(s) detected. Select one under Recent jobs to resume.')


def main() -> None:
    set_windows_app_id()
    root=tk.Tk(); App(root); root.mainloop()

if __name__ == '__main__': main()
