from __future__ import annotations
from pathlib import Path
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from .audio import audition_sample, merge_parts, synthesize_parts
from .config import DEFAULT_RATE, DEFAULT_VOICE, default_export_root, load_config, local_work_root, save_config
from .models import JobPaths
from .pipeline import job_status, prepare_job, rebuild_parts, strip_junk_and_rebuild

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title('KR Book To Audio')
        self.root.geometry('980x720')
        self.events: queue.Queue[tuple] = queue.Queue()
        self.job: JobPaths | None = None
        cfg = load_config()
        self.source = tk.StringVar()
        self.work_root = tk.StringVar(value=cfg.get('work_root', str(local_work_root())))
        self.export_root = tk.StringVar(value=cfg.get('export_root', str(default_export_root())))
        self.dictionary = tk.StringVar(value=cfg.get('dictionary', ''))
        self.voice = tk.StringVar(value=cfg.get('voice', DEFAULT_VOICE))
        self.rate = tk.StringVar(value=cfg.get('rate', DEFAULT_RATE))
        self.t2s = tk.BooleanVar(value=cfg.get('t2s', False))
        self.strip_dates = tk.BooleanVar(value=cfg.get('strip_dates', False))
        self._build()
        self.root.after(100, self._drain)

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=12); frame.pack(fill='both', expand=True)
        rows = [('Book', self.source, self._browse_source), ('Local working root', self.work_root, self._browse_work), ('Export root', self.export_root, self._browse_export), ('Pronunciation dictionary (optional JSON)', self.dictionary, self._browse_dict)]
        for row, (label, var, command) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', pady=3)
            ttk.Entry(frame, textvariable=var, width=95).grid(row=row, column=1, sticky='ew', pady=3)
            ttk.Button(frame, text='Browse', command=command).grid(row=row, column=2, padx=6)
        frame.columnconfigure(1, weight=1)
        opts = ttk.Frame(frame); opts.grid(row=4, column=0, columnspan=3, sticky='ew', pady=(8,4))
        ttk.Label(opts, text='Voice').pack(side='left'); ttk.Entry(opts, textvariable=self.voice, width=28).pack(side='left', padx=5)
        ttk.Label(opts, text='Rate').pack(side='left'); ttk.Entry(opts, textvariable=self.rate, width=8).pack(side='left', padx=5)
        ttk.Checkbutton(opts, text='Traditional to Simplified', variable=self.t2s).pack(side='left', padx=10)
        ttk.Checkbutton(opts, text='Strip date tags', variable=self.strip_dates).pack(side='left', padx=10)
        actions = ttk.Frame(frame); actions.grid(row=5, column=0, columnspan=3, sticky='ew', pady=8)
        for text, method in [
            ('1. Prepare text', self.prepare), ('2. Open proofread file', self.open_proofread), ('3. Rebuild parts', self.rebuild),
            ('Optional: Strip repeated junk', self.strip_junk), ('4. Audition voice', self.audition), ('5. Preview Part 1', self.preview), ('6. Synthesize all parts', self.synthesize), ('7. Merge MP3', self.merge), ('Resume existing job', self.resume),
        ]:
            ttk.Button(actions, text=text, command=method).pack(side='left', padx=3, pady=3)
        self.status = ttk.Label(frame, text='Ready. Work files default to a local non-cloud-synced directory.')
        self.status.grid(row=6, column=0, columnspan=3, sticky='w')
        self.log = tk.Text(frame, height=31, wrap='word'); self.log.grid(row=7, column=0, columnspan=3, sticky='nsew', pady=(8,0))
        frame.rowconfigure(7, weight=1)

    def _browse_source(self):
        value = filedialog.askopenfilename(filetypes=[('Books', '*.pdf *.epub *.mobi *.azw *.prc *.docx *.txt *.md'), ('All files', '*.*')])
        if value: self.source.set(value)
    def _browse_work(self):
        value = filedialog.askdirectory();
        if value: self.work_root.set(value)
    def _browse_export(self):
        value = filedialog.askdirectory();
        if value: self.export_root.set(value)
    def _browse_dict(self):
        value = filedialog.askopenfilename(filetypes=[('JSON', '*.json'), ('All files', '*.*')]);
        if value: self.dictionary.set(value)
    def _job_required(self) -> JobPaths | None:
        if not self.job: messagebox.showerror('No job', 'Prepare text or resume an existing job first.')
        return self.job
    def _dict(self):
        return Path(self.dictionary.get()) if self.dictionary.get().strip() else None
    def _save_cfg(self):
        save_config({'work_root': self.work_root.get(), 'export_root': self.export_root.get(), 'dictionary': self.dictionary.get(), 'voice': self.voice.get(), 'rate': self.rate.get(), 't2s': self.t2s.get(), 'strip_dates': self.strip_dates.get()})
    def _run(self, label, fn):
        self.status.config(text=label)
        def worker():
            try: self.events.put(('ok', label, fn()))
            except Exception as exc: self.events.put(('error', label, f'{type(exc).__name__}: {exc}'))
        threading.Thread(target=worker, daemon=True).start()
    def _drain(self):
        try:
            while True:
                kind, label, payload = self.events.get_nowait()
                if kind == 'error':
                    self.status.config(text=f'Failed: {label}'); self._append(payload); messagebox.showerror(label, payload)
                else:
                    self.status.config(text=f'Completed: {label}'); self._append(json.dumps(payload, ensure_ascii=False, indent=2, default=str) if not isinstance(payload, str) else payload)
        except queue.Empty:
            pass
        self.root.after(100, self._drain)
    def _append(self, text):
        self.log.insert('end', text + '\n'); self.log.see('end')
    def prepare(self):
        src = Path(self.source.get())
        self._save_cfg()
        def work():
            self.job = prepare_job(src, work_root=Path(self.work_root.get()), export_root=Path(self.export_root.get()), strip_dates=self.strip_dates.get(), convert_config='t2s' if self.t2s.get() else None, dictionary_path=self._dict())
            return job_status(self.job)
        self._run('Prepare text', work)
    def open_proofread(self):
        job = self._job_required()
        if not job: return
        os.startfile(job.proofread) if os.name == 'nt' else subprocess.Popen(['xdg-open', str(job.proofread)])
    def rebuild(self):
        job = self._job_required()
        if job: self._run('Rebuild parts', lambda: rebuild_parts(job, dictionary_path=self._dict()))
    def strip_junk(self):
        job = self._job_required()
        if job: self._run('Strip repeated junk', lambda: strip_junk_and_rebuild(job, dictionary_path=self._dict()))
    def audition(self):
        self._run('Audition voice', lambda: self._play(audition_sample(voice=self.voice.get(), rate=self.rate.get(), output_dir=Path(self.work_root.get()) / '_audition')))
    def _play(self, path: Path):
        os.startfile(path) if os.name == 'nt' else subprocess.Popen(['xdg-open', str(path)])
        return str(path)
    def preview(self):
        job = self._job_required()
        def work():
            result = synthesize_parts(job, voice=self.voice.get(), rate=self.rate.get(), start=1, end=1)
            if not result['failures']:
                self._play(job.parts_audio / 'part-0001.mp3')
            return result
        if job: self._run('Preview Part 1', work)
    def synthesize(self):
        job = self._job_required()
        if not job: return
        if not messagebox.askyesno('Synthesize all parts', 'Continue only after listening to Part 1. Synthesize all remaining parts now?'): return
        self._run('Synthesize all parts', lambda: synthesize_parts(job, voice=self.voice.get(), rate=self.rate.get()))
    def merge(self):
        job = self._job_required()
        if job: self._run('Merge MP3', lambda: str(merge_parts(job)))
    def resume(self):
        value = filedialog.askdirectory(title='Select an existing job folder')
        if value:
            job = JobPaths.from_root(Path(value))
            if not job.manifest.exists(): messagebox.showerror('Invalid job', 'No _work/job_manifest.json found.'); return
            self.job = job; self._append(json.dumps(job_status(job), ensure_ascii=False, indent=2))

def main() -> None:
    root = tk.Tk(); App(root); root.mainloop()

if __name__ == '__main__':
    main()
