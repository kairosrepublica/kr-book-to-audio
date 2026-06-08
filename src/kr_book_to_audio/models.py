from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class JobPaths:
    root: Path
    work: Path
    parts_text: Path
    parts_audio: Path
    export: Path
    manifest: Path
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
        if export_root is None:
            manifest = work / "job_manifest.json"
            if manifest.exists():
                try:
                    import json
                    export_root = json.loads(manifest.read_text(encoding="utf-8")).get("paths", {}).get("export_runtime_only")
                except (OSError, ValueError):
                    export_root = None
        export = Path(export_root) if export_root else root / "export"
        return cls(
            root=root,
            work=work,
            parts_text=work / "parts_text",
            parts_audio=work / "parts_audio",
            export=export,
            manifest=work / "job_manifest.json",
            extracted=work / "extracted.txt",
            cleaned=work / "cleaned.txt",
            proofread=work / "proofread.txt",
            tts_text=work / "tts_text.txt",
            pronunciation_preview=work / "pronunciation_preview.json",
            run_log=work / "run.log",
        )

    def ensure(self) -> None:
        # The external export folder is created only after verified finalization.
        # Creating it during job setup produced misleading empty output folders.
        for path in (self.root, self.work, self.parts_text, self.parts_audio):
            path.mkdir(parents=True, exist_ok=True)
