from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JobPaths:
    root: Path
    work: Path
    state_dir: Path
    state_db: Path
    manifest: Path
    legacy_manifest: Path
    parts_text: Path
    parts_audio: Path
    export: Path
    extracted: Path
    cleaned: Path
    proofread: Path
    tts_text: Path
    pronunciation_preview: Path
    run_log: Path

    @classmethod
    def from_root(cls, root: Path, export_root: Path | None = None) -> "JobPaths":
        root = Path(root)
        work = root / "_work"
        state_dir = work / "state"
        state_db = state_dir / "job_state.sqlite3"
        manifest = work / "job_manifest.json"
        if export_root is None:
            export_root = cls._discover_export_root(state_db, manifest)
        export = Path(export_root) if export_root else root / "export"
        return cls(
            root=root,
            work=work,
            state_dir=state_dir,
            state_db=state_db,
            manifest=manifest,
            legacy_manifest=work / "job_manifest.legacy.json",
            parts_text=work / "parts_text",
            parts_audio=work / "parts_audio",
            export=export,
            extracted=work / "extracted.txt",
            cleaned=work / "cleaned.txt",
            proofread=work / "proofread.txt",
            tts_text=work / "tts_text.txt",
            pronunciation_preview=work / "pronunciation_preview.json",
            run_log=work / "run.log",
        )

    @staticmethod
    def _discover_export_root(state_db: Path, manifest: Path) -> str | None:
        import json
        import sqlite3
        if state_db.exists():
            try:
                connection = sqlite3.connect(str(state_db), timeout=1)
                try:
                    row = connection.execute('SELECT payload_json FROM state_document WHERE singleton = 1').fetchone()
                finally:
                    connection.close()
                if row:
                    return json.loads(row[0]).get('paths', {}).get('export_runtime_only')
            except (OSError, ValueError, sqlite3.Error, TypeError):
                pass
        if manifest.exists():
            try:
                return json.loads(manifest.read_text(encoding="utf-8")).get("paths", {}).get("export_runtime_only")
            except (OSError, ValueError, TypeError):
                pass
        return None

    def ensure(self) -> None:
        # The external export folder is created only after verified finalization.
        # Creating it during job setup produced misleading empty output folders.
        for path in (self.root, self.work, self.state_dir, self.parts_text, self.parts_audio):
            path.mkdir(parents=True, exist_ok=True)
