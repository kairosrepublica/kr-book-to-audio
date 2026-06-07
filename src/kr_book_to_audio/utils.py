from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json
import os
import re
import shutil
import tempfile

_ILLEGAL = re.compile(r'[\\/:*?"<>|\t\r\n]+')


def sha256_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def sanitize_filename(name: str | None, fallback: str = "book") -> str:
    value = _ILLEGAL.sub("", name or "").strip(" ._-")
    return (value[:96] or fallback)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".partial")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: object) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def clear_files(directory: Path, pattern: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob(pattern):
        if path.is_file():
            path.unlink()


def require_command(name: str, hint: str | None = None) -> str:
    found = shutil.which(name)
    if found:
        return found
    suffix = f" ({hint})" if hint else ""
    raise RuntimeError(f"Required command not found: {name}{suffix}")


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    import zipfile
    destination = destination.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for member in z.infolist():
            target = (destination / member.filename).resolve()
            if destination != target and destination not in target.parents:
                raise ValueError(f"Unsafe ZIP member: {member.filename}")
        z.extractall(destination)
