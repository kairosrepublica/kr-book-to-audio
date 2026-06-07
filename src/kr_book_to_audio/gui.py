from __future__ import annotations
from pathlib import Path
import json
import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from .audio import approve_preview, audition_sample, merge_parts, retry_failed_parts, synthesize_parts
from .config import DEFAULT_RATE, DEFAULT_VOICE, default_export_root, load_config, local_work_root, save_config
from .manifest import load_manifest
from .models import JobPaths
from .pipeline import approve_proofread_and_rebuild, job_status, prepare_job, strip_junk_and_rebuild


def manifest_completed(job: JobPaths) -> set[str]:
    return set(load_manifest(job).get('audio', {}).get('completed', {}))


class BusyGuard:
    """Small thread-safe guard used by the GUI and covered by a headless test."""
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
    """Compact hover help so the main form remains uncluttered."""
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
        self.after_id = self.widget.after(450, self._show)

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
        label = tk.Label(
            self.window,
            text=self.text,
            justify='left',
            relief='solid',
            borderwidth=1,
            padx=7,
            pady=5,
            wraplength=430,
        )
        label.pack()

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
        self.root.geometry('1230x850')
        self.events: queue.Queue[tuple] = queue.Queue()
        self.job: JobPaths | None = None
        self.busy = BusyGuard()
        self.action_buttons: list[ttk.Button] = []
        self.part_states: dict[int, str] = {}
        cfg = load_config()
        self.source = tk.StringVar()
        self.source_folder = str(cfg.get('source_folder', Path.home()))
        self.work_root = tk.StringVar(value=cfg.get('work_root', str(local_work_root())))
        self.export_root = tk.StringVar(value=cfg.get('export_root', str(default_export_root())))
        self.dictionary = tk.StringVar(value=cfg.get('dictionary', ''))
        self.voice = tk.StringVar(value=cfg.get('voice', DEFAULT_VOICE))
        self.rate = tk.StringVar(value=cfg.get('rate', DEFAULT_RATE))
        self.strip_datetime_tags = tk.BooleanVar(value=cfg.get('strip_datetime_tags', False))
        self._build()
        self.voice.trace_add('write', self._voice_controls_changed)
        self.rate.trace_add('write', self._voice_controls_changed)
        self.root.after(100, self._drain)

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill='both', expand=True)
        rows = [
            ('Book', self.source, self._browse_source, self._set_source_folder_default,
             'Select one source book. Set folder as default stores the containing folder so the next file picker opens there.'),
            ('Local working root', self.work_root, self._browse_work, self._set_work_default,
             'Stores temporary processing files, task state and audio parts. Use a local non-cloud folder to avoid file-locking conflicts.'),
            ('Export root', self.export_root, self._browse_export, self._set_export_default,
             'Stores finished audiobook files and export-ready MP3 parts. A OneDrive folder is acceptable here.'),
            ('Pronunciation dictionary', self.dictionary, self._browse_dict, None,
             'Optional JSON replacement dictionary for names, polyphonic Chinese characters and recurring terminology.'),
        ]
        for row, (label, var, browse, set_default, tip) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', pady=3)
            ttk.Entry(frame, textvariable=var, width=90).grid(row=row, column=1, sticky='ew', pady=3)
            ttk.Button(frame, text='Browse', command=browse).grid(row=row, column=2, padx=(6, 3))
            if set_default:
                ttk.Button(frame, text='Set as default', command=set_default).grid(row=row, column=3, padx=3)
            add_help(frame, tip, row=row, column=4, padx=(4, 0), sticky='w')
        frame.columnconfigure(1, weight=1)

        opts = ttk.Frame(frame)
        opts.grid(row=4, column=0, columnspan=5, sticky='ew', pady=(8, 4))
        ttk.Label(opts, text='Voice').pack(side='left')
        ttk.Entry(opts, textvariable=self.voice, width=28).pack(side='left', padx=5)
        ttk.Label(opts, text='Rate').pack(side='left')
        ttk.Entry(opts, textvariable=self.rate, width=8).pack(side='left', padx=5)

        cleanup = ttk.Labelframe(frame, text='Optional cleanup')
        cleanup.grid(row=5, column=0, columnspan=5, sticky='ew', pady=(4, 5))
        ttk.Checkbutton(cleanup, text='Remove metadata-like date/time tags', variable=self.strip_datetime_tags).grid(row=0, column=0, sticky='w', padx=(6, 3), pady=4)
        add_help(
            cleanup,
            'Removes source-style tags such as (2019-07-30), [2024/06/18 09:30] and 2026-06-08 01:45:22. Ordinary dates and times inside prose are preserved.',
            row=0, column=1, sticky='w', padx=(0, 14),
        )
        strip_button = ttk.Button(cleanup, text='Remove repeated headers and junk', command=self.strip_junk)
        strip_button.grid(row=0, column=2, sticky='w', padx=(4, 3), pady=4)
        self.action_buttons.append(strip_button)
        add_help(
            cleanup,
            'Use after Prepare text only when the reviewed text still contains repeated headers, footers or promotional lines. A backup is created automatically.',
            row=0, column=3, sticky='w', padx=(0, 6),
        )

        actions = ttk.Frame(frame)
        actions.grid(row=6, column=0, columnspan=5, sticky='ew', pady=8)
        controls = [
            ('1. Prepare text', self.prepare),
            ('2. Open cleaned text', self.open_proofread),
            ('3. Approve reviewed text & rebuild', self.approve_proofread),
            ('4. Audition voice', self.audition),
            ('5. Preview Part 1', self.preview),
            ('6. Approve Part 1', self.approve_part_one),
            ('7. Synthesize all', self.synthesize),
            ('Retry failed', self.retry_failed),
            ('8. Merge MP3', self.merge),
            ('Resume job', self.resume),
        ]
        for index, (text, method) in enumerate(controls):
            button = ttk.Button(actions, text=text, command=method)
            button.grid(row=index // 4, column=index % 4, sticky='ew', padx=3, pady=3)
            self.action_buttons.append(button)
        for column in range(4):
            actions.columnconfigure(column, weight=1)

        self.status = ttk.Label(frame, text='Ready.')
        self.status.grid(row=7, column=0, columnspan=5, sticky='w')
        self.progress = ttk.Progressbar(frame, maximum=100)
        self.progress.grid(row=8, column=0, columnspan=5, sticky='ew', pady=(5, 5))
        body = ttk.Panedwindow(frame, orient='horizontal')
        body.grid(row=9, column=0, columnspan=5, sticky='nsew')
        log_frame = ttk.Labelframe(body, text='Run log')
        parts_frame = ttk.Labelframe(body, text='Part status')
        body.add(log_frame, weight=3)
        body.add(parts_frame, weight=2)
        self.log = tk.Text(log_frame, height=30, wrap='word')
        self.log.pack(fill='both', expand=True)
        self.parts = ttk.Treeview(parts_frame, columns=('part', 'state'), show='headings', height=24)
        self.parts.heading('part', text='Part')
        self.parts.heading('state', text='State')
        self.parts.column('part', width=90, anchor='center')
        self.parts.column('state', width=180, anchor='w')
        self.parts.pack(fill='both', expand=True)
        frame.rowconfigure(9, weight=1)

    def _browse_source(self) -> None:
        initial = self.source_folder if Path(self.source_folder).exists() else str(Path.home())
        value = filedialog.askopenfilename(initialdir=initial, filetypes=[('Books', '*.pdf *.epub *.mobi *.azw *.prc *.docx *.txt *.md'), ('All files', '*.*')])
        if value:
            self.source.set(value)

    def _browse_work(self) -> None:
        value = filedialog.askdirectory(initialdir=self.work_root.get() or str(local_work_root()))
        if value:
            self.work_root.set(value)

    def _browse_export(self) -> None:
        value = filedialog.askdirectory(initialdir=self.export_root.get() or str(default_export_root()))
        if value:
            self.export_root.set(value)

    def _browse_dict(self) -> None:
        value = filedialog.askopenfilename(filetypes=[('JSON', '*.json'), ('All files', '*.*')])
        if value:
            self.dictionary.set(value)

    def _persist_default(self, key: str, value: str, message: str) -> None:
        cfg = load_config()
        cfg[key] = value
        save_config(cfg)
        self.status.config(text=message)

    def _set_source_folder_default(self) -> None:
        value = self.source.get().strip()
        if not value:
            messagebox.showerror('No book', 'Select a book first.')
            return
        folder = str(Path(value).expanduser().resolve().parent)
        self.source_folder = folder
        self._persist_default('source_folder', folder, 'Default book folder saved.')

    def _set_work_default(self) -> None:
        self._persist_default('work_root', self.work_root.get().strip(), 'Default local working root saved.')

    def _set_export_default(self) -> None:
        self._persist_default('export_root', self.export_root.get().strip(), 'Default export root saved.')

    def _job_required(self) -> JobPaths | None:
        if not self.job:
            messagebox.showerror('No job', 'Prepare text or resume an existing job first.')
        return self.job

    def _dict(self) -> Path | None:
        return Path(self.dictionary.get()) if self.dictionary.get().strip() else None

    def _save_runtime_cfg(self) -> None:
        cfg = load_config()
        cfg.update({
            'dictionary': self.dictionary.get(),
            'voice': self.voice.get(),
            'rate': self.rate.get(),
            'strip_datetime_tags': self.strip_datetime_tags.get(),
        })
        save_config(cfg)

    def _voice_controls_changed(self, *_: object) -> None:
        if self.job:
            self.status.config(text='Voice or rate changed. Generate and approve Part 1 again before full synthesis.')

    def _set_actions_enabled(self, enabled: bool) -> None:
        state = 'normal' if enabled else 'disabled'
        for button in self.action_buttons:
            button.config(state=state)

    def _run(self, label: str, fn) -> None:
        if not self.busy.start(label):
            messagebox.showwarning('Job busy', f'Another operation is still running: {self.busy.label}')
            return
        self._set_actions_enabled(False)
        self.status.config(text=label)
        def worker() -> None:
            try:
                self.events.put(('ok', label, fn()))
            except Exception as exc:
                self.events.put(('error', label, f'{type(exc).__name__}: {exc}'))
        threading.Thread(target=worker, daemon=True).start()

    def _progress_event(self, payload: dict) -> None:
        self.events.put(('progress', 'Synthesis', payload))

    def _drain(self) -> None:
        try:
            while True:
                kind, label, payload = self.events.get_nowait()
                if kind == 'progress':
                    self._update_part_progress(payload)
                    continue
                self.busy.finish()
                self._set_actions_enabled(True)
                if kind == 'error':
                    self.status.config(text=f'Failed: {label}')
                    self._append(payload)
                    messagebox.showerror(label, payload)
                else:
                    self.status.config(text=f'Completed: {label}')
                    self._append(json.dumps(payload, ensure_ascii=False, indent=2, default=str) if not isinstance(payload, str) else payload)
                    self._refresh_job_view()
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _append(self, text: str) -> None:
        self.log.insert('end', text + '\n')
        self.log.see('end')

    def _reset_part_view(self) -> None:
        self.part_states.clear()
        for iid in self.parts.get_children():
            self.parts.delete(iid)
        self.progress['value'] = 0

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
            self._set_part_state(index, state)
        self.progress['value'] = (completed / total * 100) if total else 0
        self._append(json.dumps(status, ensure_ascii=False, indent=2))

    def _set_part_state(self, index: int, state: str) -> None:
        self.part_states[index] = state
        iid = str(index)
        values = (f'{index:04d}', state)
        if self.parts.exists(iid):
            self.parts.item(iid, values=values)
        else:
            self.parts.insert('', 'end', iid=iid, values=values)

    def _update_part_progress(self, payload: dict) -> None:
        index = int(payload['index'])
        state = str(payload['state'])
        self._set_part_state(index, state)
        if self.job:
            manifest = load_manifest(self.job)
            total = len(manifest.get('parts', []))
            completed = len(manifest.get('audio', {}).get('completed', {}))
            self.progress['value'] = (completed / total * 100) if total else 0
        self.status.config(text=f'Part {index:04d}: {state}')

    def prepare(self) -> None:
        source_value = self.source.get().strip()
        if not source_value:
            messagebox.showerror('No book', 'Select a book first.')
            return
        src = Path(source_value)
        self._save_runtime_cfg()
        work_root = Path(self.work_root.get())
        export_root = Path(self.export_root.get())
        strip_datetime_tags = self.strip_datetime_tags.get()
        dictionary = self._dict()
        self._reset_part_view()
        def work():
            self.job = prepare_job(src, work_root=work_root, export_root=export_root, strip_datetime_tags=strip_datetime_tags, dictionary_path=dictionary)
            return job_status(self.job)
        self._run('Prepare text', work)

    def open_proofread(self) -> None:
        job = self._job_required()
        if not job:
            return
        os.startfile(job.proofread) if os.name == 'nt' else subprocess.Popen(['xdg-open', str(job.proofread)])

    def approve_proofread(self) -> None:
        job = self._job_required()
        if job:
            dictionary = self._dict()
            self._run('Approve reviewed text & rebuild', lambda: approve_proofread_and_rebuild(job, dictionary_path=dictionary))

    def strip_junk(self) -> None:
        job = self._job_required()
        if job:
            dictionary = self._dict()
            self._run('Remove repeated headers and junk', lambda: strip_junk_and_rebuild(job, dictionary_path=dictionary))

    def audition(self) -> None:
        voice, rate = self.voice.get(), self.rate.get()
        output_dir = Path(self.work_root.get()) / '_audition'
        self._run('Audition voice', lambda: self._play(audition_sample(voice=voice, rate=rate, output_dir=output_dir)))

    def _play(self, path: Path) -> str:
        os.startfile(path) if os.name == 'nt' else subprocess.Popen(['xdg-open', str(path)])
        return str(path)

    def preview(self) -> None:
        job = self._job_required()
        if not job:
            return
        voice, rate = self.voice.get(), self.rate.get()
        def work():
            result = synthesize_parts(job, voice=voice, rate=rate, start=1, end=1, require_preview_approval=False, progress=self._progress_event)
            if not result['failures']:
                self._play(job.parts_audio / 'part-0001.mp3')
            return result
        self._run('Preview Part 1', work)

    def approve_part_one(self) -> None:
        job = self._job_required()
        if job:
            voice, rate = self.voice.get(), self.rate.get()
            self._run('Approve Part 1', lambda: approve_preview(job, voice=voice, rate=rate))

    def synthesize(self) -> None:
        job = self._job_required()
        if not job:
            return
        if not messagebox.askyesno('Synthesize all parts', 'Synthesize all manifest-declared parts now?'):
            return
        voice, rate = self.voice.get(), self.rate.get()
        self._run('Synthesize all parts', lambda: synthesize_parts(job, voice=voice, rate=rate, progress=self._progress_event))

    def retry_failed(self) -> None:
        job = self._job_required()
        if job:
            voice, rate = self.voice.get(), self.rate.get()
            self._run('Retry failed parts', lambda: retry_failed_parts(job, voice=voice, rate=rate, progress=self._progress_event))

    def merge(self) -> None:
        job = self._job_required()
        if job:
            self._run('Merge MP3', lambda: str(merge_parts(job)))

    def resume(self) -> None:
        value = filedialog.askdirectory(title='Select an existing job folder', initialdir=self.work_root.get() or str(local_work_root()))
        if not value:
            return
        job = JobPaths.from_root(Path(value))
        if not job.manifest.exists():
            messagebox.showerror('Invalid job', 'No _work/job_manifest.json found.')
            return
        self.job = job
        self._reset_part_view()
        manifest = load_manifest(job)
        dictionary_path = manifest.get('text', {}).get('dictionary_path_runtime_only')
        self.dictionary.set(dictionary_path or '')
        self._refresh_job_view()


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == '__main__':
    main()
