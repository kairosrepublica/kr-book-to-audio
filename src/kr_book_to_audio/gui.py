from __future__ import annotations
from pathlib import Path
import json
import os
import queue
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
from .recovery import recover_job, scan_and_recover_jobs
from .models import JobPaths
from .ocr import OCRAnalysis, analyze_source, preview_sample_ocr, run_recommended_ocr
from .pipeline import approve_proofread_and_rebuild, apply_cleanup_and_rebuild, job_status, prepare_job
from .providers import OCR_PROVIDER_SPECS, enabled_tts_specs
from .subprocess_utils import process_trace
from .workflow_state import derive_workflow_state
from .voices import filter_voices, load_voice_cache, refresh_voice_cache

PROFILE_LABELS = {
    'Auto detect · recommended': 'auto',
    'Chinese optimized': 'chinese',
    'English optimized': 'english',
    'Mixed Chinese-English': 'mixed',
    'General prose': 'general-prose',
}
PROFILE_BY_ID = {value: key for key, value in PROFILE_LABELS.items()}


BRANDING_DIR_PARTS = ('assets', 'branding')
BRANDING_ICO = 'kr_book_to_audio.ico'
BRANDING_PNG = 'ba_round_corner_small_square_fill-800.png'
WINDOWS_APP_ID = 'KairosRepublica.KRBookToAudio'


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


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title('KR Book To Audio')
        apply_window_icon(self.root)
        self.root.geometry('1320x1060')
        self.events: queue.Queue[tuple] = queue.Queue()
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
        self.ocr_analysis: OCRAnalysis | None = None
        cfg = load_config()
        self.source = tk.StringVar()
        self.source_folder = str(cfg.get('source_folder', Path.home()))
        self.work_root = tk.StringVar(value=cfg.get('work_root', str(local_work_root())))
        self.export_root = tk.StringVar(value=cfg.get('export_root', str(default_export_root())))
        self.dictionary = tk.StringVar(value=cfg.get('dictionary', ''))
        self.profile = tk.StringVar(value=PROFILE_BY_ID.get(str(cfg.get('processing_profile', DEFAULT_PROCESSING_PROFILE)), 'Auto detect · recommended'))
        specs = enabled_tts_specs()
        self.tts_engine_labels = {spec.label: spec.provider_id for spec in specs}
        self.tts_engine = tk.StringVar(value=next(iter(self.tts_engine_labels), 'Microsoft Edge Online TTS · edge-tts'))
        self.voice = tk.StringVar(value=cfg.get('voice', DEFAULT_VOICE))
        self.rate = tk.StringVar(value=cfg.get('rate', DEFAULT_RATE))
        self.pitch = tk.StringVar(value=cfg.get('pitch', DEFAULT_PITCH))
        self.volume = tk.StringVar(value=cfg.get('volume', DEFAULT_VOLUME))
        self.show_all_voices = tk.BooleanVar(value=bool(cfg.get('show_all_voices', False)))
        self.show_older_attempts = tk.BooleanVar(value=False)
        self.keep_awake = tk.BooleanVar(value=bool(cfg.get('keep_awake', DEFAULT_KEEP_AWAKE)))
        self.recent_by_iid: dict[str, dict] = {}
        self.voice_records = load_voice_cache(self._tts_engine_id())
        self.advanced_ocr_visible = False
        self.ocr_override = tk.StringVar(value='Use recommended engine')
        self._build()
        self._apply_voice_filter()
        for var in (self.voice, self.rate, self.pitch, self.volume, self.tts_engine):
            var.trace_add('write', self._voice_controls_changed)
        self.profile.trace_add('write', self._profile_changed)
        self.show_all_voices.trace_add('write', self._profile_changed)
        self.show_older_attempts.trace_add('write', lambda *_: self.refresh_recent_jobs())
        self.root.after(100, self._drain)
        self.root.after(250, self._startup_recovery)
        self._refresh_voices(background=True)

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill='both', expand=True)
        rows = [
            ('Book', self.source, self._browse_source, self._open_source, self._set_source_folder_default, 'Select one source book. The default action stores its containing folder for the next file picker.'),
            ('Local working root', self.work_root, self._browse_work, self._open_work_root, self._set_work_default, 'Stores temporary processing files, task state and audio parts. Prefer a local non-cloud folder to avoid file-locking conflicts.'),
            ('Export root', self.export_root, self._browse_export, self._open_export_root, self._set_export_default, 'Stores verified audiobook exports and export-ready MP3 parts. A OneDrive folder is acceptable here.'),
            ('Pronunciation dictionary', self.dictionary, self._browse_dict, self._open_dictionary, None, 'Optional JSON replacement dictionary for names, polyphonic Chinese characters and recurring terminology.'),
        ]
        for row, (label, var, browse, open_path, set_default, tip) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', pady=3)
            ttk.Entry(frame, textvariable=var, width=92).grid(row=row, column=1, sticky='ew', pady=3)
            ttk.Button(frame, text='Browse', command=browse).grid(row=row, column=2, padx=(6, 3))
            ttk.Button(frame, text='Open', command=open_path).grid(row=row, column=3, padx=3)
            if set_default:
                ttk.Button(frame, text='Set as default', command=set_default).grid(row=row, column=4, padx=3)
            add_help(frame, tip, row=row, column=5, padx=(4, 0), sticky='w')
        frame.columnconfigure(1, weight=1)

        recent = ttk.Labelframe(frame, text='Resume interrupted or incomplete jobs')
        recent.grid(row=4, column=0, columnspan=6, sticky='ew', pady=(8, 4))
        self.recent_jobs = ttk.Treeview(recent, columns=('title', 'status', 'progress', 'last_active'), show='headings', height=3)
        self.recent_jobs.heading('title', text='Book title'); self.recent_jobs.heading('status', text='Status'); self.recent_jobs.heading('progress', text='Progress'); self.recent_jobs.heading('last_active', text='Last active')
        self.recent_jobs.column('title', width=360, anchor='w'); self.recent_jobs.column('status', width=160, anchor='w'); self.recent_jobs.column('progress', width=120, anchor='center'); self.recent_jobs.column('last_active', width=220, anchor='w')
        self.recent_jobs.grid(row=0, column=0, columnspan=6, sticky='ew', padx=5, pady=5)
        for col, (label, method) in enumerate([('Resume selected', self.resume_selected), ('Open output folder', self.open_selected_output), ('Remove from history', self.remove_selected_history), ('Refresh', self.refresh_recent_jobs), ('Advanced recovery…', self.advanced_recovery)]):
            button = ttk.Button(recent, text=label, command=method)
            button.grid(row=1, column=col, sticky='w', padx=5, pady=(0, 5))
            self.action_buttons.append(button)
        ttk.Checkbutton(recent, text='Show older attempts…', variable=self.show_older_attempts).grid(row=2, column=0, sticky='w', padx=5, pady=(0, 5))
        add_help(recent, 'Shows resumable tasks. Advanced recovery is only for a task missing from this list; it manually loads a known job folder.', row=1, column=5, sticky='w')

        opts = ttk.Labelframe(frame, text='Text and speech settings')
        opts.grid(row=5, column=0, columnspan=6, sticky='ew', pady=(4, 4))
        ttk.Label(opts, text='Processing profile').grid(row=0, column=0, sticky='w', padx=(6, 3), pady=4)
        ttk.Combobox(opts, textvariable=self.profile, values=list(PROFILE_LABELS), state='readonly', width=28).grid(row=0, column=1, sticky='w', padx=3)
        add_help(opts, 'Controls cleanup and chunking rules. Auto detect is recommended. You can override it before Prepare text.', row=0, column=2, sticky='w', padx=(0, 14))
        ttk.Label(opts, text='TTS engine').grid(row=0, column=3, sticky='w', padx=(8, 3))
        ttk.Combobox(opts, textvariable=self.tts_engine, values=list(self.tts_engine_labels), state='readonly', width=38).grid(row=0, column=4, sticky='w', padx=3)
        add_help(opts, 'Current release enables Microsoft Edge Online TTS through edge-tts. The provider registry reserves future local and external API adapters.', row=0, column=5, sticky='w', padx=(0, 14))
        ttk.Label(opts, text='Voice').grid(row=1, column=0, sticky='w', padx=(6, 3), pady=4)
        self.voice_combo = ttk.Combobox(opts, textvariable=self.voice, state='readonly', width=34)
        self.voice_combo.grid(row=1, column=1, sticky='w', padx=3)
        ttk.Button(opts, text='Refresh', command=lambda: self._refresh_voices(background=False)).grid(row=1, column=2, sticky='w', padx=3)
        ttk.Checkbutton(opts, text='Show all voices', variable=self.show_all_voices).grid(row=1, column=3, sticky='w', padx=(8, 3))
        add_help(opts, 'Voices are cached locally. Refresh queries the selected provider. Profile filtering recommends suitable locales but Show all voices keeps manual override available.', row=1, column=5, sticky='w', padx=(0, 14))
        ttk.Label(opts, text='Rate').grid(row=2, column=0, sticky='w', padx=(6, 3), pady=4)
        ttk.Entry(opts, textvariable=self.rate, width=10).grid(row=2, column=1, sticky='w', padx=3)
        ttk.Label(opts, text='Pitch').grid(row=2, column=2, sticky='e', padx=3)
        ttk.Entry(opts, textvariable=self.pitch, width=10).grid(row=2, column=3, sticky='w', padx=3)
        ttk.Label(opts, text='Volume').grid(row=2, column=4, sticky='e', padx=3)
        ttk.Entry(opts, textvariable=self.volume, width=10).grid(row=2, column=5, sticky='w', padx=3)

        ocr = ttk.Labelframe(frame, text='OCR')
        ocr.grid(row=6, column=0, columnspan=6, sticky='ew', pady=(4, 4))
        self.ocr_status = ttk.Label(ocr, text='Status: Not analyzed')
        self.ocr_status.grid(row=0, column=0, columnspan=4, sticky='w', padx=6, pady=(4, 2))
        self.ocr_reason = ttk.Label(ocr, text='Select a book, then analyze OCR requirements.', wraplength=980)
        self.ocr_reason.grid(row=1, column=0, columnspan=5, sticky='w', padx=6, pady=(0, 4))
        for col, (label, method) in enumerate([
            ('Analyze source', self.analyze_ocr),
            ('Preview OCR sample', self.preview_ocr),
            ('Run recommended OCR', self.run_ocr),
            ('Advanced override…', self.toggle_ocr_advanced),
        ]):
            btn = ttk.Button(ocr, text=label, command=method)
            btn.grid(row=2, column=col, sticky='w', padx=6, pady=(0, 5))
            self.action_buttons.append(btn)
        add_help(ocr, 'The advisor decides whether OCR is applicable or needed, discovers local engines and recommends a provider.', row=2, column=4, sticky='w')
        self.ocr_advanced = ttk.Frame(ocr)
        ttk.Label(self.ocr_advanced, text='OCR engine override').pack(side='left', padx=(6, 3))
        self.ocr_override_combo = ttk.Combobox(self.ocr_advanced, textvariable=self.ocr_override, state='readonly', width=46)
        self.ocr_override_combo.pack(side='left', padx=3)

        text_process = ttk.Labelframe(frame, text='Text process')
        text_process.grid(row=7, column=0, columnspan=6, sticky='ew', pady=(4, 5))
        self._workflow_button(text_process, 'prepare', '1. Prepare text', self.prepare, row=0, column=0)
        cleanup = ttk.Labelframe(text_process, text='2. Optional cleanup analysis')
        cleanup.grid(row=1, column=0, columnspan=4, sticky='ew', padx=5, pady=5)
        self.cleanup_junk = ttk.Label(cleanup, text='Repeated headers and junk: Not analyzed')
        self.cleanup_junk.grid(row=0, column=0, sticky='w', padx=6, pady=3)
        btn = ttk.Button(cleanup, text='Apply repeated-header cleanup', command=lambda: self.apply_cleanup('repeated-headers-and-junk'))
        btn.grid(row=0, column=1, sticky='w', padx=4); self.action_buttons.append(btn)
        add_help(cleanup, 'Removes only high-confidence repeated headers, footers, URLs and promotional lines. A backup is created first.', row=0, column=2, sticky='w')
        self.cleanup_datetime = ttk.Label(cleanup, text='Metadata-like date/time tags: Not analyzed')
        self.cleanup_datetime.grid(row=1, column=0, sticky='w', padx=6, pady=3)
        btn = ttk.Button(cleanup, text='Apply date/time cleanup', command=lambda: self.apply_cleanup('metadata-date-time-tags'))
        btn.grid(row=1, column=1, sticky='w', padx=4); self.action_buttons.append(btn)
        add_help(cleanup, 'Removes standalone metadata-style timestamps. Ordinary dates and times inside prose are preserved. A backup is created first.', row=1, column=2, sticky='w')
        self._workflow_button(cleanup, 'cleanup_all', 'Apply all recommended cleanup', self.apply_all_cleanup, row=2, column=1)
        self._workflow_button(text_process, 'open_cleaned', '3. Open cleaned text', self.open_proofread, row=2, column=0)
        self._workflow_button(text_process, 'approve_text', '4. Approve reviewed text & rebuild', self.approve_proofread, row=2, column=1)
        for column in range(4): text_process.columnconfigure(column, weight=1)

        audio_process = ttk.Labelframe(frame, text='Audio process')
        audio_process.grid(row=8, column=0, columnspan=6, sticky='ew', pady=(4, 5))
        self._workflow_button(audio_process, 'audition', '5. Audition voice', self.audition, row=0, column=0)
        self._workflow_button(audio_process, 'preview', '6. Preview Part 1', self.preview, row=0, column=1)
        self._workflow_button(audio_process, 'approve_preview', '7. Approve Part 1', self.approve_part_one, row=0, column=2)
        self._workflow_button(audio_process, 'synthesize', '8. Synthesize all', self.synthesize, row=1, column=0)
        self._workflow_button(audio_process, 'retry_failed', 'Retry failed', self.retry_failed, row=1, column=1)
        self._workflow_button(audio_process, 'merge', '9. Merge MP3', self.merge, row=1, column=2)
        self._workflow_button(audio_process, 'open_export', 'Open final export folder', self.open_current_export, row=2, column=0)
        self.export_status = ttk.Label(audio_process, text='Final export is automatic and mandatory after synthesis.')
        self.export_status.grid(row=2, column=1, columnspan=3, sticky='w', padx=6)
        for column in range(4): audio_process.columnconfigure(column, weight=1)

        runtime = ttk.Labelframe(frame, text='Long-running operations')
        runtime.grid(row=9, column=0, columnspan=6, sticky='ew', pady=(0, 5))
        ttk.Checkbutton(runtime, text='Keep computer awake during OCR or TTS', variable=self.keep_awake).grid(row=0, column=0, sticky='w', padx=6, pady=4)
        add_help(runtime, 'Prevents automatic system sleep while OCR or TTS is running. It does not block manual sleep, shutdown or lid-close actions.', row=0, column=1, sticky='w', padx=(3, 8))

        self.status = ttk.Label(frame, text='Ready.')
        self.status.grid(row=10, column=0, columnspan=6, sticky='w')
        ttk.Label(frame, text='Overall progress · exact').grid(row=11, column=0, sticky='w')
        self.overall_progress = ttk.Progressbar(frame, maximum=100)
        self.overall_progress.grid(row=11, column=1, columnspan=5, sticky='ew', pady=(5, 5))
        self.overall_label = ttk.Label(frame, text='0 / 0 parts completed · 0%')
        self.overall_label.grid(row=12, column=0, columnspan=6, sticky='w')

        body = ttk.Panedwindow(frame, orient='horizontal')
        body.grid(row=13, column=0, columnspan=6, sticky='nsew')
        log_frame = ttk.Labelframe(body, text='Run log')
        parts_frame = ttk.Labelframe(body, text='Part status')
        body.add(log_frame, weight=3); body.add(parts_frame, weight=2)
        self.log = tk.Text(log_frame, height=20, wrap='word')
        self.log.pack(fill='both', expand=True)
        self.parts = ttk.Treeview(parts_frame, columns=('part', 'state'), show='headings', height=17)
        self.parts.heading('part', text='Part'); self.parts.heading('state', text='State')
        self.parts.column('part', width=80, anchor='center'); self.parts.column('state', width=210, anchor='w')
        self.parts.tag_configure('running', background='#d9f2d9', foreground='#006400')
        self.parts.tag_configure('validating', background='#e8f5e9', foreground='#006400')
        self.parts.pack(fill='both', expand=True)
        current = ttk.Labelframe(parts_frame, text='Current part · estimated')
        current.pack(fill='x', pady=(5, 0))
        self.current_label = ttk.Label(current, text='No active part')
        self.current_label.pack(anchor='w', padx=5, pady=(3, 0))
        self.current_progress = ttk.Progressbar(current, maximum=100)
        self.current_progress.pack(fill='x', padx=5, pady=(3, 5))
        frame.rowconfigure(13, weight=1)

        ttk.Separator(frame, orient='horizontal').grid(row=14, column=0, columnspan=6, sticky='ew', pady=(6, 2))
        footer = ttk.Frame(frame)
        footer.grid(row=15, column=0, columnspan=6, sticky='ew', pady=(0, 2))
        ttk.Label(footer, text='COPYRIGHT © KENT REIS & KAIROS REPÚBLICA').pack(side='left')
        ttk.Label(footer, text='BUILT IN CONSTANTINOPLE WITH LOVE').pack(side='right')
        self._render_workflow_state()

    def _workflow_button(self, parent: tk.Widget, key: str, text: str, command, *, row: int, column: int) -> tk.Button:
        button = tk.Button(parent, text=text, command=command, relief='raised', padx=7, pady=3)
        button.grid(row=row, column=column, sticky='ew', padx=5, pady=4)
        self.workflow_buttons[key] = button
        self.workflow_base_labels[key] = text
        return button

    def _tts_engine_id(self) -> str:
        return self.tts_engine_labels.get(self.tts_engine.get(), DEFAULT_TTS_ENGINE)

    def _profile_id(self) -> str:
        return PROFILE_LABELS.get(self.profile.get(), DEFAULT_PROCESSING_PROFILE)


    def _current_speech_controls(self) -> dict[str, str]:
        return speech_controls(
            provider_id=self._tts_engine_id(),
            voice=self.voice.get(),
            rate=self.rate.get(),
            pitch=self.pitch.get(),
            volume=self.volume.get(),
        )

    def _set_speech_controls(self, controls: dict[str, str]) -> None:
        labels_by_id = {provider_id: label for label, provider_id in self.tts_engine_labels.items()}
        provider_id = controls.get('provider_id', DEFAULT_TTS_ENGINE)
        if provider_id in labels_by_id:
            self.tts_engine.set(labels_by_id[provider_id])
        self.rate.set(controls.get('rate', DEFAULT_RATE))
        self.pitch.set(controls.get('pitch', DEFAULT_PITCH))
        self.volume.set(controls.get('volume', DEFAULT_VOLUME))
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

    def _dict(self) -> Path | None:
        return Path(self.dictionary.get()) if self.dictionary.get().strip() else None

    def _save_runtime_cfg(self) -> None:
        cfg = load_config(); cfg.update({'dictionary': self.dictionary.get(), 'tts_engine': self._tts_engine_id(), 'voice': self.voice.get(), 'rate': self.rate.get(), 'pitch': self.pitch.get(), 'volume': self.volume.get(), 'processing_profile': self._profile_id(), 'show_all_voices': self.show_all_voices.get(), 'keep_awake': self.keep_awake.get()}); save_config(cfg)

    def _job_required(self) -> JobPaths | None:
        if not self.job: messagebox.showerror('No job', 'Prepare text or resume an existing job first.')
        return self.job

    def _voice_controls_changed(self, *_: object) -> None:
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
        def work(): return refresh_voice_cache(self._tts_engine_id())
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
        self._render_workflow_state()

    def _process_trace_event(self, payload: dict[str, object]) -> None:
        self.events.put(('process', 'External process', payload, None))

    def _run(self, label: str, fn, on_success=None) -> None:
        if not self.busy.start(label):
            messagebox.showwarning('Job busy', f'Another operation is still running: {self.busy.label}'); return
        self._set_actions_enabled(False); self.status.config(text=label)
        self._log_event(f'Started: {label}')
        def worker() -> None:
            try:
                with process_trace(self._process_trace_event, operation=label):
                    result = fn()
                self.events.put(('ok', label, result, on_success))
            except Exception as exc:
                self.events.put(('error', label, f'{type(exc).__name__}: {exc}', None))
        threading.Thread(target=worker, daemon=True).start()

    def _progress_event(self, payload: dict) -> None:
        self.events.put(('progress', 'Synthesis', payload, None))

    def _drain(self) -> None:
        try:
            while True:
                kind, label, payload, callback = self.events.get_nowait()
                if kind == 'progress': self._update_part_progress(payload); continue
                if kind == 'process':
                    self._handle_process_trace(payload)
                    continue
                if kind == 'silent-ok':
                    if callback: callback(payload)
                    continue
                if kind == 'silent-error':
                    self._log_event(f'{label}: {payload}')
                    continue
                self.busy.finish(); self._set_actions_enabled(True)
                if kind == 'error':
                    self.status.config(text=f'Failed: {label}')
                    self._log_event(f'Failed: {label} · {payload}')
                    messagebox.showerror(label, payload)
                else:
                    self.status.config(text=f'Completed: {label}')
                    self._log_event(f'Completed: {label}')
                    if callback: callback(payload)
                    self._refresh_job_view()
                self._render_workflow_state()
        except queue.Empty: pass
        self.root.after(100, self._drain)

    def _handle_process_trace(self, payload: dict[str, object]) -> None:
        phase = str(payload.get('phase') or '')
        tool = str(payload.get('tool') or 'unknown')
        if phase == 'start':
            self._log_event(f'External tool: {tool} · hidden-window launch')
        elif phase == 'error':
            self._log_event(f'External tool failed: {tool} · {payload.get("error")}')

    def _render_workflow_state(self) -> None:
        if not hasattr(self, 'workflow_buttons'):
            return
        states = derive_workflow_state(self.job, source_selected=bool(self.source.get().strip()), running_label=self.busy.label)
        palette = {
            'completed': {'bg': '#e6e6e6', 'fg': '#666666', 'state': 'disabled', 'prefix': '✓ '},
            'running': {'bg': '#f4a261', 'fg': '#000000', 'state': 'disabled', 'prefix': 'RUNNING · '},
            'next': {'bg': '#fff3cd', 'fg': '#000000', 'state': 'normal', 'prefix': 'NEXT · '},
            'optional': {'bg': '#f8f9fa', 'fg': '#000000', 'state': 'normal', 'prefix': 'Optional · '},
            'failed': {'bg': '#f8d7da', 'fg': '#8b0000', 'state': 'normal', 'prefix': 'FAILED · '},
            'blocked': {'bg': '#efefef', 'fg': '#999999', 'state': 'disabled', 'prefix': ''},
        }
        for key, button in self.workflow_buttons.items():
            action = states.get(key)
            state_name = action.state if action else 'blocked'
            style = palette[state_name]
            enabled_state = style['state'] if self.ui_actions_enabled else 'disabled'
            font = ('TkDefaultFont', 9, 'bold') if state_name in {'running', 'next', 'failed'} else ('TkDefaultFont', 9)
            button.config(text=style['prefix'] + self.workflow_base_labels[key], bg=style['bg'], fg=style['fg'], state=enabled_state, font=font, disabledforeground=style['fg'])

    def _log_event(self, text: str) -> None:
        stamp = datetime.now().strftime('%H:%M:%S')
        self.log.insert('end', f'[{stamp}] {text}\n')
        self.log.see('end')

    def _append(self, text: str) -> None:
        self._log_event(text)

    def _reset_part_view(self) -> None:
        self.part_states.clear()
        for iid in self.parts.get_children(): self.parts.delete(iid)
        self.overall_progress['value'] = 0; self.current_progress['value'] = 0
        self.overall_label.config(text='0 / 0 parts completed · 0%'); self.current_label.config(text='No active part')

    def _render_cleanup(self, analysis: dict) -> None:
        junk = analysis.get('repeated_headers_and_junk', {})
        dates = analysis.get('metadata_datetime_tags', {})
        self.cleanup_junk.config(text=f"Repeated headers and junk: {junk.get('status', 'not-analyzed')} · {junk.get('count', 0)} high-confidence")
        self.cleanup_datetime.config(text=f"Metadata-like date/time tags: {dates.get('status', 'not-analyzed')} · {dates.get('count', 0)} high-confidence")

    def _refresh_job_view(self) -> None:
        if not self.job: return
        status = job_status(self.job); total = int(status['parts']); completed = int(status['completed_audio_parts']); failed = set(status['failed_audio_parts']); completed_indexes = {int(index) for index in manifest_completed(self.job)}
        for index in range(1, total + 1):
            state = 'failed' if index in failed else ('done' if index in completed_indexes else self.part_states.get(index, 'queued'))
            highlight = 'running' if state.startswith('RUNNING') or state.startswith('RETRYING') else ('validating' if state.startswith('VALIDATING') else None)
            self._set_part_state(index, state, highlight=highlight)
        pct = (completed / total * 100) if total else 0
        self.overall_progress['value'] = pct; self.overall_label.config(text=f'{completed} / {total} parts completed · {pct:.0f}%')
        self._render_cleanup(status.get('cleanup_analysis', {}))
        if hasattr(self, 'export_status'):
            export_state = status.get('export', {}).get('status', 'not-finalized')
            self.export_status.config(text=f'Final export: {export_state}. Export finalization and verification are automatic.')
        self._render_workflow_state()

    def _set_part_state(self, index: int, state: str, *, highlight: str | None = None) -> None:
        self.part_states[index] = state
        iid = str(index)
        values = (f'{index:04d}', state)
        tags = (highlight,) if highlight else ()
        if self.parts.exists(iid):
            self.parts.item(iid, values=values, tags=tags)
        else:
            self.parts.insert('', 'end', iid=iid, values=values, tags=tags)

    def _center_part_status(self, index: int) -> None:
        iid = str(index)
        if not self.parts.exists(iid):
            return
        children = list(self.parts.get_children())
        if not children:
            return
        try:
            position = children.index(iid)
        except ValueError:
            return
        visible_rows = max(3, int(self.parts.cget('height') or 19))
        target = max(0.0, min(1.0, (position - visible_rows // 2) / max(1, len(children))))
        self.parts.yview_moveto(target)
        self.parts.see(iid)
        self.parts.selection_set(iid)
        self.parts.focus(iid)

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

    def _estimate_tick(self, token: int) -> None:
        if token != self.estimate_token or self.current_index is None or self.current_started_monotonic is None:
            return
        elapsed = max(0.0, time.monotonic() - self.current_started_monotonic)
        self.current_estimate = min(94, max(self.current_estimate, int(elapsed / max(1.0, self.current_expected_seconds) * 90)))
        state = self.part_states.get(self.current_index, 'RUNNING')
        if 'retrying' in state.lower():
            label_state = 'retrying'
        else:
            label_state = 'synthesizing audio'
        self.current_progress['value'] = self.current_estimate
        self.current_label.config(text=f'Part {self.current_index:04d} / current · {self.current_estimate}% estimated · {label_state}')
        self._set_part_state(self.current_index, f'RUNNING · {self.current_estimate}% estimated', highlight='running')
        self._center_part_status(self.current_index)
        self._log_progress_bucket(self.current_index, 'running', self.current_estimate)
        if self.current_estimate < 94:
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

    def _update_part_progress(self, payload: dict) -> None:
        if payload.get('event') == 'export':
            self._update_export_progress(payload)
            return
        index = int(payload['index'])
        state = str(payload['state'])
        estimate = int(payload.get('estimated_percent', 0))
        text_chars = int(payload.get('text_chars', 0) or 0)
        if state in {'running', 'retrying'}:
            self.current_index = index
            self.current_estimate = max(5, estimate)
            self.current_started_monotonic = time.monotonic()
            self.current_expected_seconds = self._expected_seconds(text_chars)
            self.estimate_token += 1
            token = self.estimate_token
            self.current_progress['value'] = self.current_estimate
            self.current_label.config(text=f'Part {index:04d} / current · {self.current_estimate}% estimated · {state}')
            self._set_part_state(index, f'{state.upper()} · {self.current_estimate}% estimated', highlight='running')
            self._center_part_status(index)
            self._log_progress_bucket(index, state, self.current_estimate)
            self.root.after(700, lambda: self._estimate_tick(token))
        elif state == 'validating':
            self.estimate_token += 1
            self.current_index = index
            self.current_estimate = 95
            self.current_progress['value'] = 95
            self.current_label.config(text=f'Part {index:04d} / current · 95% estimated · validating audio')
            self._set_part_state(index, 'VALIDATING · 95% estimated', highlight='validating')
            self._center_part_status(index)
            self._log_progress_bucket(index, 'validating', 95)
        elif state == 'done':
            self.estimate_token += 1
            elapsed = float(payload.get('elapsed_seconds', 0) or 0)
            if elapsed > 0 and text_chars > 0:
                self.runtime_seconds_per_char.append(elapsed / text_chars)
            self.current_index = index
            self.current_estimate = 100
            self.current_progress['value'] = 100
            self.current_label.config(text=f'Part {index:04d} · 100% done')
            self._set_part_state(index, 'done')
            self._center_part_status(index)
            self._log_progress_bucket(index, 'done', 100)
        elif state == 'failed':
            self.estimate_token += 1
            self.current_index = index
            self.current_estimate = 0
            self.current_progress['value'] = 0
            self.current_label.config(text=f'Part {index:04d} · failed')
            self._set_part_state(index, 'failed')
            self._center_part_status(index)
            self._log_progress_bucket(index, 'failed', 0)
        else:
            self._set_part_state(index, state)
        self._refresh_job_view()
        self.status.config(text=f'Part {index:04d}: {state}')

    def analyze_ocr(self) -> None:
        value = self.source.get().strip()
        if not value: messagebox.showerror('No book', 'Select a book first.'); return
        def done(analysis: OCRAnalysis):
            self.ocr_analysis = analysis
            recommended = analysis.recommended_provider or 'none'
            self.ocr_status.config(text=f'Status: {analysis.status} · language: {analysis.language} · recommended: {recommended}')
            self.ocr_reason.config(text=analysis.reason)
            available = ['Use recommended engine'] + [pid for pid, data in analysis.capabilities.items() if pid in OCR_PROVIDER_SPECS and data.get('available')]
            self.ocr_override_combo['values'] = available
        self._run('Analyze OCR requirements', lambda: analyze_source(Path(value)), done)

    def toggle_ocr_advanced(self) -> None:
        self.advanced_ocr_visible = not self.advanced_ocr_visible
        if self.advanced_ocr_visible: self.ocr_advanced.grid(row=3, column=0, columnspan=5, sticky='w', pady=(0, 5))
        else: self.ocr_advanced.grid_forget()

    def _selected_ocr_provider(self) -> str | None:
        value = self.ocr_override.get()
        if value and value != 'Use recommended engine': return value
        return self.ocr_analysis.recommended_provider if self.ocr_analysis else None

    def preview_ocr(self) -> None:
        if not self.ocr_analysis:
            messagebox.showerror('OCR not analyzed', 'Run Analyze source first.'); return
        provider = self._selected_ocr_provider()
        self._run('Preview OCR sample', lambda: preview_sample_ocr(Path(self.source.get()), self.ocr_analysis, provider_id=provider))

    def run_ocr(self) -> None:
        if not self.ocr_analysis:
            messagebox.showerror('OCR not analyzed', 'Run Analyze source first.'); return
        provider = self._selected_ocr_provider(); output_dir = Path(self.work_root.get()) / '_ocr_outputs'
        def done(path: Path):
            self.source.set(str(path)); self.ocr_status.config(text='Status: OCR output ready · select Prepare text')
            self.ocr_reason.config(text=f'OCR output selected as the new source: {path}')
        self._run('Run recommended OCR', lambda: run_recommended_ocr(Path(self.source.get()), self.ocr_analysis, output_dir=output_dir, provider_id=provider, keep_awake=self.keep_awake.get()), done)

    def prepare(self) -> None:
        value = self.source.get().strip()
        if not value: messagebox.showerror('No book', 'Select a book first.'); return
        self._save_runtime_cfg(); self._reset_part_view()
        def work():
            self.job = prepare_job(Path(value), work_root=Path(self.work_root.get()), export_root=Path(self.export_root.get()), processing_profile=self._profile_id(), dictionary_path=self._dict())
            return job_status(self.job)
        self._run('Prepare text', work)

    def open_proofread(self) -> None:
        job = self._job_required()
        if job: os.startfile(job.proofread) if os.name == 'nt' else subprocess.Popen(['xdg-open', str(job.proofread)])

    def approve_proofread(self) -> None:
        job = self._job_required()
        if job: self._run('Approve reviewed text & rebuild', lambda: approve_proofread_and_rebuild(job, dictionary_path=self._dict()))

    def apply_cleanup(self, kind: str) -> None:
        job = self._job_required()
        if job: self._run(f'Apply cleanup: {kind}', lambda: apply_cleanup_and_rebuild(job, kind=kind, dictionary_path=self._dict()))

    def apply_all_cleanup(self) -> None:
        job = self._job_required()
        if not job: return
        analysis = job_status(job).get('cleanup_analysis', {})
        kinds=[]
        if analysis.get('repeated_headers_and_junk', {}).get('status') == 'recommended': kinds.append('repeated-headers-and-junk')
        if analysis.get('metadata_datetime_tags', {}).get('status') == 'recommended': kinds.append('metadata-date-time-tags')
        if not kinds: messagebox.showinfo('Cleanup', 'No high-confidence cleanup is recommended.'); return
        def work():
            reports=[]
            for kind in kinds: reports.append(apply_cleanup_and_rebuild(job, kind=kind, dictionary_path=self._dict()))
            return reports
        self._run('Apply all recommended cleanup', work)

    def audition(self) -> None:
        self._save_runtime_cfg(); output_dir = Path(self.work_root.get()) / '_audition'
        self._run('Audition voice', lambda: self._play(audition_sample(provider_id=self._tts_engine_id(), voice=self.voice.get(), rate=self.rate.get(), pitch=self.pitch.get(), volume=self.volume.get(), output_dir=output_dir)))

    def _play(self, path: Path) -> str:
        os.startfile(path) if os.name == 'nt' else subprocess.Popen(['xdg-open', str(path)]); return str(path)

    def preview(self) -> None:
        job = self._job_required()
        if not job: return
        def work():
            result=synthesize_parts(job, provider_id=self._tts_engine_id(), voice=self.voice.get(), rate=self.rate.get(), pitch=self.pitch.get(), volume=self.volume.get(), start=1, end=1, require_preview_approval=False, progress=self._progress_event, keep_awake=self.keep_awake.get())
            if not result['failures']: self._play(job.parts_audio / 'part-0001.mp3')
            return result
        self._run('Preview Part 1', work)

    def approve_part_one(self) -> None:
        job=self._job_required()
        if job: self._run('Approve Part 1', lambda: approve_preview(job, provider_id=self._tts_engine_id(), voice=self.voice.get(), rate=self.rate.get(), pitch=self.pitch.get(), volume=self.volume.get()))

    def synthesize(self) -> None:
        job=self._job_required()
        if not job or not messagebox.askyesno('Synthesize all parts', 'Synthesize all manifest-declared parts now?'): return
        self._run('Synthesize all parts', lambda: synthesize_parts(job, provider_id=self._tts_engine_id(), voice=self.voice.get(), rate=self.rate.get(), pitch=self.pitch.get(), volume=self.volume.get(), progress=self._progress_event, keep_awake=self.keep_awake.get()))

    def retry_failed(self) -> None:
        job=self._job_required()
        if job: self._run('Retry failed parts', lambda: retry_failed_parts(job, provider_id=self._tts_engine_id(), voice=self.voice.get(), rate=self.rate.get(), pitch=self.pitch.get(), volume=self.volume.get(), progress=self._progress_event, keep_awake=self.keep_awake.get()))

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
        for idx, item in enumerate(list_resumable_jobs(include_older_attempts=self.show_older_attempts.get())):
            iid = f'recent-{idx}'
            self.recent_by_iid[iid] = item
            progress = f"{item.get('completed_parts', 0)} / {item.get('total_parts', 0)}"
            self.recent_jobs.insert('', 'end', iid=iid, values=(item.get('title'), display_status(item), progress, format_last_active(item.get('updated_utc'))))

    def _selected_recent(self) -> dict | None:
        selected = self.recent_jobs.selection()
        if not selected:
            messagebox.showinfo('Recent jobs', 'Select a recent job first.')
            return None
        return self.recent_by_iid.get(selected[0])

    def _resume_from_part(self, next_part: int) -> None:
        if not self.job:
            return
        self._log_event(f'Resume requested. Validating checkpoint and continuing from Part {next_part}.')
        self._run(
            f'Resume synthesis from Part {next_part}',
            lambda: synthesize_parts(
                self.job,
                provider_id=self._tts_engine_id(),
                voice=self.voice.get(),
                rate=self.rate.get(),
                pitch=self.pitch.get(),
                volume=self.volume.get(),
                start=next_part,
                progress=self._progress_event,
                keep_awake=self.keep_awake.get(),
            ),
        )

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
            messagebox.showinfo('Resume checkpoint', 'This task has no incomplete Part to resume.')
            return
        status = job_status(self.job)
        next_part = int(report['next_part'])
        completed = int(status.get('completed_audio_parts') or 0)
        total = int(status.get('parts') or 0)
        if not status.get('proofread_approved'):
            messagebox.showinfo(
                'Text review required before resume',
                f'Existing audio preserved: {completed} / {total} parts.\n\nNext part: {next_part}\n\nRequired action:\n1. Open cleaned text.\n2. Approve reviewed text & rebuild.\n3. Click Resume selected again.',
            )
            self.status.config(text=f'Text review required before resume from Part {next_part}. Existing MP3 files remain preserved.')
            return
        if report.get('speech_controls_rehydrated') and status.get('preview_approved') and self._resume_controls_are_approved(self.job):
            if messagebox.askyesno('Resume ready', f'Existing audio verified: {completed} / {total} parts.\n\nResume now from Part {next_part}?'):
                self._resume_from_part(next_part)
            return
        proceed = messagebox.askyesno(
            'Voice check required before resume',
            f'Existing audio preserved: {completed} / {total} parts.\n\nNext part: {next_part}\n\n'
            'This legacy task does not contain a complete speech-control snapshot.\n\n'
            'The app will open the preserved Part 1 and generate a candidate Part 1 preview using the currently selected voice controls. After listening, approve or cancel. Existing MP3 files will not be deleted.\n\nStart the guided voice check now?',
        )
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
