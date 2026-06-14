from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid
import zipfile

from .durable_io import write_json as durable_write_json
from .local_ocr import LocalOCRFoundation, local_ocr_foundation
from .paddleocr_worker_script import PADDLEOCR_WORKER_SCRIPT

UV_PACKAGE = 'uv==0.11.19'
OCR_RUNTIME_REQUEST = '3.12'
PADDLE_PACKAGE = 'paddlepaddle==3.2.2'
PADDLEOCR_PACKAGE = 'paddleocr==3.6.0'
PADDLE_CPU_INDEX = 'https://www.paddlepaddle.org.cn/packages/stable/cpu/'
MIN_RESOURCE_FREE_BYTES = 8 * 1024 * 1024 * 1024
POPPLER_URL = 'https://github.com/oschwartz10612/poppler-windows/releases/download/v26.02.0-0/Release-26.02.0-0.zip'
TESSERACT_SOURCES = (
    ('github-release-5.5.0', 'https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe'),
    ('sourceforge-direct-5.5.0', 'https://downloads.sourceforge.net/project/tesseract-ocr.mirror/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe'),
    ('sourceforge-page-5.5.0', 'https://sourceforge.net/projects/tesseract-ocr.mirror/files/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe/download'),
    ('ub-mannheim-5.5.0', 'https://digi.bib.uni-mannheim.de/tesseract/tesseract-ocr-w64-setup-5.5.0.20241111.exe'),
)
PADDLE_MODELS = {
    'PP-OCRv5_server_det': 'https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_server_det_infer.tar',
    'PP-OCRv5_server_rec': 'https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_server_rec_infer.tar',
    'PP-OCRv5_mobile_det': 'https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_mobile_det_infer.tar',
    'PP-OCRv5_mobile_rec': 'https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_mobile_rec_infer.tar',
}
TESSDATA_REPOS = {
    'fast': 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main',
    'best': 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main',
}
TESSDATA_FILES = ('eng.traineddata', 'chi_sim.traineddata', 'chi_tra.traineddata', 'osd.traineddata')
SEED_TREES = (
    'wheelhouse/uv',
    'wheelhouse/paddleocr_py312_win_amd64',
    'runtimes/uv-python',
    'tools/poppler',
    'tools/tesseract',
    'tools/paddleocr_worker',
    'models/paddleocr',
    'tessdata/fast',
    'tessdata/best',
)


def stage(label: str) -> None:
    print(f'=== OCR FOUNDATION STAGE: {label} ===', flush=True)


def run(args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, check: bool = True, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    print('RUN:', ' '.join(str(item) for item in args), flush=True)
    result = subprocess.run(args, cwd=str(cwd) if cwd else None, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if result.stdout:
        print(result.stdout, end='' if result.stdout.endswith('\n') else '\n', flush=True)
    if check and result.returncode != 0:
        raise RuntimeError(f'Command failed with exit code {result.returncode}: {args}')
    return result


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def copytree_new(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise RuntimeError(f'Required directory is missing: {source}')
    if destination.exists():
        raise RuntimeError(f'Append-only destination already exists: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)


def copyfile_new(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise RuntimeError(f'Required file is missing: {source}')
    if destination.exists():
        raise RuntimeError(f'Append-only destination already exists: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copyfile_if_missing(source: Path, destination: Path) -> None:
    if destination.is_file():
        return
    copyfile_new(source, destination)


def online_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_DATASETS_OFFLINE'):
        env.pop(name, None)
    env.update({'HF_HUB_DISABLE_SYMLINKS': '1', 'HF_HUB_DISABLE_SYMLINKS_WARNING': '1', 'PIP_DISABLE_PIP_VERSION_CHECK': '1'})
    return env


def uv_env(foundation: LocalOCRFoundation) -> dict[str, str]:
    env = online_env()
    env.update({
        'UV_PYTHON_INSTALL_DIR': str(foundation.root / 'runtimes' / 'uv-python'),
        'UV_PYTHON_BIN_DIR': str(foundation.root / 'runtimes' / 'uv-python-bin'),
        'UV_PYTHON_INSTALL_BIN': '1',
        'UV_PYTHON_INSTALL_REGISTRY': '0',
        'UV_PYTHON_NO_REGISTRY': '1',
        'UV_NO_MODIFY_PATH': '1',
        'UV_NO_CONFIG': '1',
        'UV_MANAGED_PYTHON': '1',
    })
    return env


def python_in(env: Path) -> Path:
    return env / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def uv_in(env: Path) -> Path:
    return env / ('Scripts/uv.exe' if os.name == 'nt' else 'bin/uv')


def python_version(python: Path) -> tuple[int, int, int]:
    result = run([str(python), '-c', 'import sys; print(".".join(map(str, sys.version_info[:3])))'])
    return tuple(int(item) for item in result.stdout.strip().split('.')[-3:])  # type: ignore[return-value]


def _persistent_download_target(url: str, destination: Path) -> Path:
    destination = Path(destination)
    parts = destination.parts
    for index, part in enumerate(parts):
        if part == 'bundles' and index + 1 < len(parts):
            base = Path(*parts[:index])
            token = sha256(url.encode('utf-8')).hexdigest()[:16]
            return base / 'downloads' / f'{token}_{destination.name}'
    return destination


def _download_receipt(path: Path) -> Path:
    return path.with_name(path.name + '.complete.json')


def _download_cache_verified(url: str, path: Path) -> bool:
    receipt = _download_receipt(path)
    if not path.is_file() or not receipt.is_file() or path.stat().st_size <= 0:
        return False
    try:
        payload = json.loads(receipt.read_text(encoding='utf-8'))
        return (
            payload.get('url') == url
            and int(payload.get('bytes', -1)) == path.stat().st_size
            and payload.get('sha256') == sha256_file(path)
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def _write_download_receipt(url: str, path: Path) -> None:
    payload = {'url': url, 'bytes': path.stat().st_size, 'sha256': sha256_file(path)}
    _download_receipt(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _reject_unverified_download(path: Path) -> None:
    if not path.exists():
        return
    rejected = path.parent / 'rejected' / f'{path.name}.{uuid.uuid4().hex[:8]}'
    rejected.parent.mkdir(parents=True, exist_ok=True)
    path.replace(rejected)
    receipt = _download_receipt(path)
    if receipt.exists():
        receipt.replace(rejected.with_name(rejected.name + '.complete.json'))


def _expected_download_size(status: int, existing: int, headers) -> int | None:
    length_raw = headers.get('Content-Length')
    length = int(length_raw) if length_raw and str(length_raw).isdigit() else None
    if status == 200:
        return length
    if status != 206:
        raise RuntimeError(f'Unexpected HTTP download status: {status}')
    content_range = str(headers.get('Content-Range') or '')
    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+|\*)', content_range)
    if not match:
        raise RuntimeError(f'Resumed download returned invalid Content-Range: {content_range!r}')
    start, end = int(match.group(1)), int(match.group(2))
    if start != existing or end < start:
        raise RuntimeError(f'Resumed download range mismatch: expected start {existing}, got {content_range!r}')
    chunk = end - start + 1
    if length is not None and length != chunk:
        raise RuntimeError(f'Resumed download Content-Length mismatch: expected {chunk}, got {length}')
    total = match.group(3)
    if total != '*':
        total_size = int(total)
        if end + 1 != total_size:
            raise RuntimeError(f'Resumed response did not reach declared final byte: {content_range!r}')
        return total_size
    return existing + chunk


def _acquire_persistent_download(url: str, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + '.part')
    if _download_cache_verified(url, target):
        print(f'DOWNLOAD REUSE PASS: {target}', flush=True)
        return target
    if target.exists() or _download_receipt(target).exists():
        _reject_unverified_download(target)
    existing = partial.stat().st_size if partial.exists() else 0
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) KR-Book-To-Audio-OCR-Foundation/2.5.0',
        'Accept': '*/*',
    }
    if existing:
        headers['Range'] = f'bytes={existing}-'
    print(f'DOWNLOAD START: {url}', flush=True)
    print(f'DOWNLOAD STAGING TARGET: {target}', flush=True)
    request = Request(url, headers=headers)
    with urlopen(request, timeout=90) as response:
        status = int(getattr(response, 'status', 200) or 200)
        mode = 'ab' if existing and status == 206 else 'wb'
        if mode == 'wb':
            existing = 0
        expected = _expected_download_size(status, existing, response.headers)
        written = existing
        next_report = written + 32 * 1024 * 1024
        with partial.open(mode) as handle:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                handle.write(block)
                written += len(block)
                if written >= next_report:
                    suffix = f' / {expected / (1024 * 1024):.1f} MB' if expected else ''
                    print(f'DOWNLOAD PROGRESS: {target.name}: {written / (1024 * 1024):.1f} MB{suffix}', flush=True)
                    next_report = written + 32 * 1024 * 1024
    actual = partial.stat().st_size if partial.exists() else 0
    if actual <= 0:
        raise RuntimeError(f'Download produced no bytes: {url}')
    if expected is not None and actual != expected:
        raise RuntimeError(f'Download truncated: expected {expected} bytes, got {actual}: {url}')
    partial.replace(target)
    _write_download_receipt(url, target)
    print(f'DOWNLOAD PASS: {target} SHA-256 {sha256_file(target)}', flush=True)
    return target


def online_download_with_resume(url: str, destination: Path) -> Path:
    destination = Path(destination)
    staged = _acquire_persistent_download(url, _persistent_download_target(url, destination))
    if staged == destination:
        return destination
    if destination.is_file():
        if sha256_file(destination) != sha256_file(staged):
            raise RuntimeError(f'Append-only candidate download mismatch: {destination}')
        return destination
    copyfile_new(staged, destination)
    return destination


# Backward-compatible name retained for tests and product-local adapters.
download_with_resume = online_download_with_resume


def validate_windows_pe_download(path: Path, *, label: str) -> None:
    if not path.is_file():
        raise RuntimeError(f'{label} download is missing: {path}')
    if path.stat().st_size < 1024 * 1024:
        raise RuntimeError(f'{label} download is unexpectedly small: {path} ({path.stat().st_size} bytes)')
    with path.open('rb') as handle:
        signature = handle.read(2)
    if signature != b'MZ':
        raise RuntimeError(f'{label} download is not a Windows PE executable: {path}')


def download_from_sources_with_resume(sources: tuple[tuple[str, str], ...], destination: Path, *, validator=None) -> Path:
    failures: list[str] = []
    for source_name, url in sources:
        try:
            path = download_with_resume(url, destination)
            if validator is not None:
                validator(path)
            print(f'DOWNLOAD SOURCE PASS: {source_name}', flush=True)
            return path
        except Exception as exc:
            failures.append(f'{source_name}: {type(exc).__name__}: {exc}')
            print(f'DOWNLOAD SOURCE FAIL: {source_name}: {type(exc).__name__}: {exc}', flush=True)
            if destination.is_file():
                rejected = destination.parent / 'rejected' / f'{destination.name}.{source_name}.{uuid.uuid4().hex[:8]}'
                rejected.parent.mkdir(parents=True, exist_ok=True)
                destination.replace(rejected)
    raise RuntimeError('All download sources failed for ' + destination.name + ':\n' + '\n'.join(failures))


def safe_extract_zip(source: Path, destination: Path) -> None:
    if destination.exists():
        raise RuntimeError(f'Extraction destination must be new: {destination}')
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f'Unsafe ZIP member: {member.filename}')
        archive.extractall(destination)


def safe_extract_tar(source: Path, destination: Path) -> None:
    if destination.exists():
        raise RuntimeError(f'Extraction destination must be new: {destination}')
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    with tarfile.open(source) as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f'Unsafe TAR member: {member.name}')
        archive.extractall(destination, filter='data')


def locate_one(root: Path, filename: str) -> Path:
    matches = sorted(path for path in root.rglob(filename) if path.is_file())
    if not matches:
        raise RuntimeError(f'{filename} was not found below {root}')
    return matches[0]


def _manifest_entries(foundation: LocalOCRFoundation) -> dict[str, str]:
    if not foundation.manifest.is_file():
        return {}
    try:
        payload = json.loads(foundation.manifest.read_text(encoding='utf-8'))
        entries = payload.get('entries', {}) if isinstance(payload, dict) else {}
        return {str(key): str(value) for key, value in entries.items()} if isinstance(entries, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _archive_relative(foundation: LocalOCRFoundation, path: Path) -> str:
    return str(Path(path).resolve().relative_to(foundation.archive_root.resolve())).replace('\\', '/')


def archived_file_verified(foundation: LocalOCRFoundation, path: Path) -> bool:
    path = Path(path)
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    expected = _manifest_entries(foundation).get(_archive_relative(foundation, path))
    return bool(expected) and sha256_file(path) == expected


def archived_tree_verified(foundation: LocalOCRFoundation, root: Path) -> bool:
    root = Path(root)
    files = sorted(path for path in root.rglob('*') if path.is_file()) if root.is_dir() else []
    return bool(files) and all(archived_file_verified(foundation, path) for path in files)


def tree_nonempty(root: Path) -> bool:
    return root.is_dir() and any(path.is_file() for path in root.rglob('*'))


def bootstrap_python_command() -> list[str]:
    if not bool(getattr(sys, 'frozen', False)):
        return [str(Path(sys.executable))]
    python = shutil.which('python.exe') or shutil.which('python')
    if python:
        return [str(python)]
    launcher = shutil.which('py.exe') or shutil.which('py')
    if launcher:
        return [str(launcher), '-3']
    raise RuntimeError('A system Python interpreter is required to bootstrap the isolated OCR runtime. Install Python or run the Owner publisher first.')


@dataclass(frozen=True)
class DeploymentContext:
    base: LocalOCRFoundation
    candidate: LocalOCRFoundation
    bundle_id: str


def new_bundle_id() -> str:
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    return f'ocr_{stamp}_{uuid.uuid4().hex[:8]}'


def create_context(base: LocalOCRFoundation, *, bundle_id: str | None = None) -> DeploymentContext:
    selected = bundle_id or new_bundle_id()
    deployment = base.root / 'deployments' / selected
    bundle = base.resource_root / 'bundles' / selected
    if deployment.exists() or bundle.exists():
        raise RuntimeError(f'Append-only bundle already exists: {selected}')
    deployment.mkdir(parents=True, exist_ok=False)
    bundle.mkdir(parents=True, exist_ok=False)
    return DeploymentContext(base=base, candidate=LocalOCRFoundation(deployment, bundle), bundle_id=selected)


def ensure_base_structure(base: LocalOCRFoundation) -> None:
    for relative in ('deployments', 'active', 'reports'):
        (base.root / relative).mkdir(parents=True, exist_ok=True)
    for relative in ('bundles', 'active', 'downloads', 'reports'):
        (base.resource_root / relative).mkdir(parents=True, exist_ok=True)


def ensure_candidate_structure(foundation: LocalOCRFoundation) -> None:
    # Create container directories only. Artifact leaf directories remain absent
    # until the stage that owns each immutable append-only write creates them.
    # Pre-creating a leaf such as runtimes/uv-python would make copytree_new()
    # reject the candidate's own first write.
    for relative in (
        'manifests', 'receipts', 'downloads', 'wheelhouse', 'runtimes',
        'tools', 'models/paddleocr', 'tessdata', 'samples/zh', 'samples/en',
    ):
        (foundation.resource_root / relative).mkdir(parents=True, exist_ok=True)
    for relative in ('envs', 'runtimes', 'tools', 'models/paddleocr', 'tessdata', 'workers', 'reports', 'logs', 'samples/zh', 'samples/en'):
        (foundation.root / relative).mkdir(parents=True, exist_ok=True)


def ensure_space(base: LocalOCRFoundation) -> None:
    existing = base.resource_root
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if not existing.exists():
        raise RuntimeError(f'No existing parent is available for OCR resource archive: {base.resource_root}')
    free = shutil.disk_usage(existing).free
    print(f'OCR RESOURCE ARCHIVE FREE BYTES: {free}', flush=True)
    if free < MIN_RESOURCE_FREE_BYTES:
        raise RuntimeError(f'OCR archive requires at least {MIN_RESOURCE_FREE_BYTES} free bytes: {base.resource_root}')


def seed_candidate_archive(context: DeploymentContext) -> list[str]:
    seeded: list[str] = []
    source_root = context.base.archive_root
    source_foundation = context.base
    for relative in SEED_TREES:
        source = source_root / relative
        destination = context.candidate.resource_root / relative
        try:
            if archived_tree_verified(source_foundation, source):
                copytree_new(source, destination)
                seeded.append(relative)
                print(f'OCR APPEND-ONLY SEED PASS: {relative}', flush=True)
        except Exception as exc:
            print(f'OCR APPEND-ONLY SEED SKIP: {relative}: {type(exc).__name__}: {exc}', flush=True)
    return seeded


def _uv_path(uv: Path, foundation: LocalOCRFoundation, *args: str) -> Path | None:
    result = run([str(uv), *args], env=uv_env(foundation), check=False)
    if result.returncode != 0:
        return None
    lines = [line.strip() for line in (result.stdout or '').splitlines() if line.strip()]
    return Path(lines[-1]) if lines else None


def _is_internal_venv_template(path: Path) -> bool:
    normalized = tuple(part.lower() for part in path.parts)
    marker = ('lib', 'venv', 'scripts', 'nt', 'python.exe')
    return len(normalized) >= len(marker) and normalized[-len(marker):] == marker


def deterministic_managed_python_candidates(
    foundation: LocalOCRFoundation,
    *,
    uv_bin_dir: Path | None = None,
    uv_install_dir: Path | None = None,
    uv_find: Path | None = None,
    platform_name: str | None = None,
) -> list[Path]:
    install_dir = uv_install_dir or (foundation.root / 'runtimes' / 'uv-python')
    bin_dir = uv_bin_dir or (foundation.root / 'runtimes' / 'uv-python-bin')
    platform = platform_name or os.name
    candidates: list[Path] = []
    if uv_find is not None:
        candidates.append(uv_find)
    if platform == 'nt':
        candidates.extend(bin_dir / name for name in ('python3.12.exe', 'python.exe', 'python3.exe'))
        if install_dir.is_dir():
            candidates.extend(path / 'python.exe' for path in sorted(install_dir.iterdir()) if path.is_dir())
    else:
        candidates.extend(bin_dir / name for name in ('python3.12', 'python3', 'python'))
        if install_dir.is_dir():
            for path in sorted(install_dir.iterdir()):
                if path.is_dir():
                    candidates.extend((path / 'bin' / 'python3.12', path / 'bin' / 'python3', path / 'bin' / 'python'))
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(str(candidate)))
        if key not in seen and not _is_internal_venv_template(candidate):
            seen.add(key)
            unique.append(candidate)
    return unique


def select_compatible_python(candidates: list[Path], *, version_reader=python_version) -> Path:
    failures: list[str] = []
    for candidate in candidates:
        if not candidate.is_file():
            failures.append(f'{candidate}: missing')
            continue
        if _is_internal_venv_template(candidate):
            failures.append(f'{candidate}: rejected internal venv template')
            continue
        try:
            version = version_reader(candidate)
        except Exception as exc:
            failures.append(f'{candidate}: rejected {type(exc).__name__}: {exc}')
            continue
        if version[:2] != (3, 12):
            failures.append(f'{candidate}: rejected Python {version}')
            continue
        print(f'OCR MANAGED PYTHON SELECT PASS: {candidate} Python {version}', flush=True)
        return candidate
    raise RuntimeError('uv-managed Python 3.12 was not found. Candidate diagnostics:\n' + '\n'.join(failures or ['<no deterministic candidates>']))


def locate_managed_python(foundation: LocalOCRFoundation, uv: Path) -> Path:
    return select_compatible_python(deterministic_managed_python_candidates(
        foundation,
        uv_bin_dir=_uv_path(uv, foundation, 'python', 'dir', '--bin'),
        uv_install_dir=_uv_path(uv, foundation, 'python', 'dir'),
        uv_find=_uv_path(uv, foundation, 'python', 'find', OCR_RUNTIME_REQUEST),
    ))


def ensure_uv(foundation: LocalOCRFoundation) -> Path:
    bootstrap = foundation.root / 'envs' / 'uv-bootstrap'
    py = python_in(bootstrap)
    if not py.exists():
        run([*bootstrap_python_command(), '-m', 'venv', str(bootstrap)])
    wheelhouse = foundation.resource_root / 'wheelhouse' / 'uv'
    wheelhouse.mkdir(parents=True, exist_ok=True)
    if not tree_nonempty(wheelhouse):
        run([str(py), '-m', 'pip', 'download', '--dest', str(wheelhouse), UV_PACKAGE], env=online_env())
    run([str(py), '-m', 'pip', 'install', '--no-index', '--find-links', str(wheelhouse), '--upgrade', UV_PACKAGE])
    uv = uv_in(bootstrap)
    if not uv.is_file():
        raise RuntimeError(f'uv executable was not created: {uv}')
    run([str(uv), '--version'])
    return uv


def ensure_python(foundation: LocalOCRFoundation, uv: Path) -> Path:
    env_root = foundation.root / 'envs' / 'paddleocr'
    py = python_in(env_root)
    archive_runtime = foundation.resource_root / 'runtimes' / 'uv-python'
    runtime = foundation.root / 'runtimes' / 'uv-python'
    if tree_nonempty(archive_runtime) and not tree_nonempty(runtime):
        copytree_new(archive_runtime, runtime)
        print(f'OCR PYTHON ARCHIVE RESTORE PASS: {runtime}', flush=True)
    try:
        managed = locate_managed_python(foundation, uv)
    except RuntimeError:
        run([str(uv), 'python', 'install', '--force', OCR_RUNTIME_REQUEST], env=uv_env(foundation))
        managed = locate_managed_python(foundation, uv)
    if not tree_nonempty(archive_runtime):
        copytree_new(runtime, archive_runtime)
        print(f'OCR PYTHON ARCHIVE PASS: {archive_runtime}', flush=True)
    if not py.exists():
        run([str(managed), '-m', 'venv', str(env_root)])
    if python_version(py)[:2] != (3, 12):
        raise RuntimeError(f'OCR environment did not use Python 3.12: {py}')
    print(f'OCR PYTHON CREATE PASS: {py}', flush=True)
    return py


def wheelhouse_has_distribution(wheelhouse: Path, project: str, version: str) -> bool:
    normalized_project = re.sub(r'[-_.]+', '-', project).lower()
    for path in wheelhouse.glob('*.whl'):
        parts = path.name.split('-')
        if len(parts) >= 2 and re.sub(r'[-_.]+', '-', parts[0]).lower() == normalized_project and parts[1].lower() == version.lower():
            return True
    return False


def ensure_wheelhouse(foundation: LocalOCRFoundation, py: Path) -> Path:
    wheelhouse = foundation.resource_root / 'wheelhouse' / 'paddleocr_py312_win_amd64'
    wheelhouse.mkdir(parents=True, exist_ok=True)
    required = (('paddlepaddle', '3.2.2'), ('paddleocr', '3.6.0'))
    if not all(wheelhouse_has_distribution(wheelhouse, project, version) for project, version in required):
        run([str(py), '-m', 'pip', 'download', '--dest', str(wheelhouse), '--extra-index-url', PADDLE_CPU_INDEX, PADDLE_PACKAGE, PADDLEOCR_PACKAGE], env=online_env())
    if not all(wheelhouse_has_distribution(wheelhouse, project, version) for project, version in required):
        raise RuntimeError('Pinned PaddleOCR wheelhouse remains incomplete after acquisition.')
    run([str(py), '-m', 'pip', 'install', '--no-index', '--find-links', str(wheelhouse), PADDLE_PACKAGE, PADDLEOCR_PACKAGE])
    run([str(py), '-c', 'import paddle, paddleocr; print("PADDLEOCR IMPORT PASS", paddle.__version__)'])
    return wheelhouse


def ensure_paddle_models(foundation: LocalOCRFoundation) -> None:
    downloads = foundation.resource_root / 'downloads'
    archive_models = foundation.resource_root / 'models' / 'paddleocr'
    for name, url in PADDLE_MODELS.items():
        formal = archive_models / name
        if not tree_nonempty(formal):
            tar_path = download_with_resume(url, downloads / f'{name}.tar')
            with tempfile.TemporaryDirectory(prefix=f'kr-ocr-paddle-{name}-extract-') as temp_dir:
                target = Path(temp_dir) / 'extract'
                safe_extract_tar(tar_path, target)
                candidates = [path for path in target.iterdir() if path.is_dir()]
                source = candidates[0] if len(candidates) == 1 else target
                copytree_new(source, formal)
            if not tree_nonempty(formal):
                raise RuntimeError(f'Extracted PaddleOCR model is empty: {formal}')
            print(f'PADDLE MODEL ARCHIVE PASS: {formal}', flush=True)
        else:
            print(f'PADDLE MODEL ARCHIVE VERIFIED REUSE PASS: {formal}', flush=True)
        runtime = foundation.root / 'models' / 'paddleocr' / name
        if not tree_nonempty(runtime):
            copytree_new(formal, runtime)


def ensure_poppler(foundation: LocalOCRFoundation) -> None:
    archive = foundation.resource_root / 'tools' / 'poppler' / 'bin'
    if not tree_nonempty(archive):
        zip_path = download_with_resume(POPPLER_URL, foundation.resource_root / 'downloads' / 'poppler.zip')
        with tempfile.TemporaryDirectory(prefix='kr-ocr-poppler-extract-') as temp_dir:
            extracted = Path(temp_dir) / 'extract'
            safe_extract_zip(zip_path, extracted)
            copytree_new(locate_one(extracted, 'pdftoppm.exe').parent, archive)
    runtime = foundation.root / 'tools' / 'poppler' / 'bin'
    if not tree_nonempty(runtime):
        copytree_new(archive, runtime)
    for name in ('pdftoppm.exe', 'pdftotext.exe', 'pdfinfo.exe', 'pdffonts.exe'):
        if not (runtime / name).is_file():
            raise RuntimeError(f'Poppler runtime is missing: {runtime / name}')
    print(f'POPPLER DEPLOY PASS: {runtime}', flush=True)


def find_7z() -> str:
    found = shutil.which('7z') or shutil.which('7z.exe')
    if not found:
        raise RuntimeError('7-Zip CLI is required to extract the archived Tesseract installer. Install 7-Zip or make 7z.exe discoverable.')
    return found


def ensure_tesseract(foundation: LocalOCRFoundation) -> None:
    archive = foundation.resource_root / 'tools' / 'tesseract'
    if not tree_nonempty(archive):
        installer = download_from_sources_with_resume(
            TESSERACT_SOURCES,
            foundation.resource_root / 'downloads' / 'tesseract-w64-setup.exe',
            validator=lambda path: validate_windows_pe_download(path, label='Tesseract installer'),
        )
        with tempfile.TemporaryDirectory(prefix='kr-ocr-tesseract-extract-') as temp_dir:
            extracted = Path(temp_dir) / 'extract'
            extracted.mkdir(parents=True, exist_ok=False)
            run([find_7z(), 'x', '-y', f'-o{extracted}', str(installer)])
            copytree_new(locate_one(extracted, 'tesseract.exe').parent, archive)
    runtime = foundation.root / 'tools' / 'tesseract'
    if not tree_nonempty(runtime):
        copytree_new(archive, runtime)
    if not foundation.tesseract.is_file():
        raise RuntimeError(f'Tesseract runtime is missing: {foundation.tesseract}')
    print(f'TESSERACT DEPLOY PASS: {runtime}', flush=True)


def ensure_tessdata(foundation: LocalOCRFoundation) -> None:
    for profile, base_url in TESSDATA_REPOS.items():
        archive = foundation.resource_root / 'tessdata' / profile
        runtime = foundation.root / 'tessdata' / profile
        archive.mkdir(parents=True, exist_ok=True)
        runtime.mkdir(parents=True, exist_ok=True)
        for filename in TESSDATA_FILES:
            formal = archive / filename
            if not formal.is_file():
                download_with_resume(f'{base_url}/{filename}', formal)
            copyfile_if_missing(formal, runtime / filename)
    print('TESSDATA DEPLOY PASS', flush=True)


def _write_worker_if_stale(path: Path, expected: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    current = path.read_text(encoding='utf-8') if path.is_file() else None
    if current != expected:
        path.write_text(expected, encoding='utf-8', newline='\n')


def ensure_worker(foundation: LocalOCRFoundation) -> None:
    archive = foundation.resource_root / 'tools' / 'paddleocr_worker' / 'paddleocr_worker.py'
    _write_worker_if_stale(archive, PADDLEOCR_WORKER_SCRIPT)
    _write_worker_if_stale(foundation.paddle_worker, PADDLEOCR_WORKER_SCRIPT)


def tesseract_probe(foundation: LocalOCRFoundation) -> None:
    foundation.assert_tesseract_ready('fast')
    run([str(foundation.tesseract), '--version'], env=foundation.tesseract_env('fast'))
    languages = run([str(foundation.tesseract), '--tessdata-dir', str(foundation.tessdata('fast')), '--list-langs'], env=foundation.tesseract_env('fast')).stdout
    for lang in ('eng', 'chi_sim', 'chi_tra', 'osd'):
        if lang not in languages:
            raise RuntimeError(f'Tesseract language probe failed: {lang}')


def paddle_import_probe(foundation: LocalOCRFoundation) -> None:
    foundation.assert_paddle_ready('server')
    run([str(foundation.paddle_python), '-c', 'import paddle, paddleocr; print("PADDLEOCR OFFLINE IMPORT PASS", paddle.__version__)'], env=foundation.offline_env())


def manifest(foundation: LocalOCRFoundation, *, report: dict[str, object]) -> None:
    manifests = foundation.resource_root / 'manifests'
    manifests.mkdir(parents=True, exist_ok=True)
    receipt = foundation.resource_root / 'receipts' / 'INSTALL_RECEIPT_PRIVATE.md'
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        '# KR OCR Offline Resource Archive Install Receipt - PRIVATE\n\n'
        '```text\n'
        f'generated: {datetime.now(timezone.utc).isoformat()}\n'
        f'archive_bundle: {foundation.resource_root}\n'
        f'runtime_candidate: {foundation.root}\n'
        'resource_policy: append-only immutable archive bundle; versioned deployment; activation by pointer only\n'
        '```\n',
        encoding='utf-8',
    )
    entries: dict[str, str] = {}
    for path in sorted(item for item in foundation.resource_root.rglob('*') if item.is_file()):
        relative = str(path.relative_to(foundation.resource_root)).replace('\\', '/')
        if relative in {'manifests/RESOURCE_MANIFEST.json', 'manifests/SHA256SUMS.txt'}:
            continue
        entries[relative] = sha256_file(path)
    payload = {'generated': datetime.now(timezone.utc).isoformat(), 'archive_bundle': str(foundation.resource_root), 'runtime_candidate': str(foundation.root), 'entries': entries, 'report': report}
    (manifests / 'RESOURCE_MANIFEST.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    (manifests / 'SHA256SUMS.txt').write_text(''.join(f'{digest}  {relative}\n' for relative, digest in sorted(entries.items())), encoding='ascii')
    print(f'OCR RESOURCE MANIFEST PASS: {manifests / "RESOURCE_MANIFEST.json"}', flush=True)


def write_foundation_report(path: Path | None, report: dict[str, object]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _write_pointer(path: Path, payload: dict[str, object]) -> None:
    durable_write_json(path, payload)


def activate_context(context: DeploymentContext) -> None:
    ready = context.candidate.ready_report()
    if not all(ready.values()):
        raise RuntimeError(f'Cannot activate incomplete OCR candidate: {ready}')
    payload = {
        'active_bundle': context.bundle_id,
        'active_archive_bundle': context.bundle_id,
        'activated_at': datetime.now(timezone.utc).isoformat(),
    }
    # ACTIVE_DEPLOYMENT.json is the single authoritative atomic commit pointer.
    # ACTIVE_BUNDLE.json remains a read-only legacy fallback and is not mutated.
    _write_pointer(context.base.active_deployment_pointer, payload)
    print(f'OCR ACTIVE DEPLOYMENT PASS: {context.bundle_id}', flush=True)


def write_manual_cleanup_report(base: LocalOCRFoundation) -> Path:
    active = None
    if base.active_deployment_pointer.is_file():
        try:
            active = json.loads(base.active_deployment_pointer.read_text(encoding='utf-8')).get('active_bundle')
        except (OSError, ValueError, json.JSONDecodeError):
            active = None
    deployments = sorted(path.name for path in (base.root / 'deployments').iterdir() if path.is_dir()) if (base.root / 'deployments').is_dir() else []
    bundles = sorted(path.name for path in (base.resource_root / 'bundles').iterdir() if path.is_dir()) if (base.resource_root / 'bundles').is_dir() else []
    payload = {
        'generated': datetime.now(timezone.utc).isoformat(),
        'policy': 'manual cleanup candidates only; no automatic deletion',
        'active_bundle': active,
        'inactive_runtime_deployments': [item for item in deployments if item != active],
        'inactive_archive_bundles': [item for item in bundles if item != active],
    }
    report = base.resource_root / 'reports' / 'MANUAL_CLEANUP_CANDIDATES_PRIVATE.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return report


def require_windows_target() -> None:
    if os.name != 'nt':
        raise RuntimeError('Local OCR foundation setup is a Windows-target operation.')


def _context_from_report(base: LocalOCRFoundation, report: dict[str, object]) -> DeploymentContext:
    bundle_id = str(report.get('bundle_id') or '')
    if not bundle_id or '/' in bundle_id or '\\' in bundle_id or '..' in bundle_id:
        raise RuntimeError('Activation report contains an invalid bundle_id.')
    deployment = base.root / 'deployments' / bundle_id
    bundle = base.resource_root / 'bundles' / bundle_id
    if not deployment.is_dir() or not bundle.is_dir():
        raise RuntimeError(f'Activation candidate is missing: {bundle_id}')
    return DeploymentContext(base=base, candidate=LocalOCRFoundation(deployment, bundle), bundle_id=bundle_id)


def activate_from_report(report_path: Path) -> dict[str, object]:
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if report.get('ok') is not True:
        raise RuntimeError('Refusing to activate a report that is not green.')
    context = _context_from_report(local_ocr_foundation(), report)
    activate_context(context)
    write_manual_cleanup_report(context.base)
    return report


def execute(*, report_path: Path | None = None, activate: bool = False) -> dict[str, object]:
    base = local_ocr_foundation()
    require_windows_target()
    ensure_base_structure(base)
    ensure_space(base)
    context = create_context(base)
    foundation = context.candidate
    seeded = seed_candidate_archive(context)
    ensure_candidate_structure(foundation)
    failures: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    stages: dict[str, str] = {}

    def collect(label: str, action):
        stage(label)
        try:
            value = action()
            stages[label] = 'PASS'
            return True, value
        except Exception as exc:
            detail = f'{type(exc).__name__}: {exc}'
            failures.append({'stage': label, 'error': detail})
            stages[label] = 'FAIL_COLLECTED'
            print(f'OCR FOUNDATION FAIL_COLLECTED: {label}: {detail}', flush=True)
            return False, None

    def skip(label: str, reason: str) -> None:
        skipped.append({'stage': label, 'reason': reason})
        stages[label] = 'SKIPPED_DEPENDENCY'
        print(f'OCR FOUNDATION SKIPPED_DEPENDENCY: {label}: {reason}', flush=True)

    uv_ok, uv = collect('Provision uv bootstrap', lambda: ensure_uv(foundation))
    if uv_ok:
        py_ok, py = collect('Provision isolated Python runtime', lambda: ensure_python(foundation, uv))
    else:
        py_ok, py = False, None
        skip('Provision isolated Python runtime', 'uv bootstrap unavailable')
    if py_ok and py:
        collect('Archive and install PaddleOCR wheelhouse', lambda: ensure_wheelhouse(foundation, py))
    else:
        skip('Archive and install PaddleOCR wheelhouse', 'isolated Python runtime unavailable')
    collect('Archive and deploy Poppler', lambda: ensure_poppler(foundation))
    collect('Archive and deploy Tesseract', lambda: ensure_tesseract(foundation))
    collect('Archive and deploy Tesseract language packs', lambda: ensure_tessdata(foundation))
    collect('Archive and deploy PaddleOCR PP-OCRv5 models', lambda: ensure_paddle_models(foundation))
    collect('Archive and deploy PaddleOCR worker', lambda: ensure_worker(foundation))
    if foundation.tesseract_ready('fast'):
        collect('Run Tesseract offline probe', lambda: tesseract_probe(foundation))
    else:
        skip('Run Tesseract offline probe', 'Tesseract runtime, Poppler or language packs unavailable')
    if foundation.paddle_ready('server'):
        collect('Run PaddleOCR offline import probe', lambda: paddle_import_probe(foundation))
    else:
        skip('Run PaddleOCR offline import probe', 'PaddleOCR runtime, Poppler, models or worker unavailable')
    report: dict[str, object] = {
        'bundle_id': context.bundle_id,
        'runtime_root': str(foundation.root),
        'resource_root': str(foundation.resource_root),
        'python': str(py) if py else None,
        'seeded': seeded,
        'ready': foundation.ready_report(),
        'stages': stages,
        'failures': failures,
        'skipped': skipped,
        'activated': False,
    }
    try:
        manifest(foundation, report=report)
        report['ready'] = foundation.ready_report()
        report['ok'] = not failures and all(report['ready'].values())  # type: ignore[union-attr]
        manifest(foundation, report=report)
    except Exception as exc:
        detail = f'{type(exc).__name__}: {exc}'
        failures.append({'stage': 'Write OCR archive manifest', 'error': detail})
        stages['Write OCR archive manifest'] = 'FAIL_COLLECTED'
        report['ready'] = foundation.ready_report()
        report['ok'] = False
        print(f'OCR FOUNDATION FAIL_COLLECTED: Write OCR archive manifest: {detail}', flush=True)
    if activate and report.get('ok'):
        activate_context(context)
        report['activated'] = True
        report['manual_cleanup_report'] = str(write_manual_cleanup_report(base))
    write_foundation_report(report_path, report)
    if report.get('ok'):
        print('OCR FOUNDATION PASS', flush=True)
    else:
        print('OCR FOUNDATION BLOCKERS COLLECTED:', flush=True)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    return report


def _runtime_locator_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix='kr-ocr-runtime-layout-fixture-') as temp_dir:
        root = Path(temp_dir) / 'runtime'
        foundation = LocalOCRFoundation(root, Path(temp_dir) / 'archive')
        bin_dir = root / 'runtimes' / 'uv-python-bin'
        install_dir = root / 'runtimes' / 'uv-python'
        broken = bin_dir / 'python3.12.exe'
        valid = install_dir / 'cpython-3.12.13-windows-x86_64-none' / 'python.exe'
        internal = install_dir / 'cpython-3.12.13-windows-x86_64-none' / 'Lib' / 'venv' / 'scripts' / 'nt' / 'python.exe'
        for path in (broken, valid, internal):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture')
        candidates = deterministic_managed_python_candidates(foundation, uv_bin_dir=bin_dir, uv_install_dir=install_dir, platform_name='nt')
        if internal in candidates:
            raise RuntimeError('Runtime locator admitted an internal venv template.')
        def fake_version(path: Path) -> tuple[int, int, int]:
            if path == broken:
                raise RuntimeError('broken shim')
            if path == valid:
                return (3, 12, 13)
            raise RuntimeError(f'unexpected candidate: {path}')
        if select_compatible_python(candidates, version_reader=fake_version) != valid:
            raise RuntimeError('Runtime locator did not continue from a broken candidate to the valid managed interpreter.')
    print('OCR MANAGED PYTHON LOCATOR SELF-TEST PASS')



def _append_only_fresh_bundle_lifecycle_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix='kr-ocr-append-only-fresh-lifecycle-fixture-') as td:
        base = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
        ensure_base_structure(base)
        context = create_context(base, bundle_id='fresh_bundle')
        foundation = context.candidate
        ensure_candidate_structure(foundation)
        archive_runtime = foundation.resource_root / 'runtimes' / 'uv-python'
        runtime = foundation.root / 'runtimes' / 'uv-python'
        if archive_runtime.exists():
            raise RuntimeError('Fresh append-only structure pre-created the immutable runtime artifact leaf.')
        managed = runtime / 'cpython-3.12.13-windows-x86_64-none' / 'python.exe'
        managed.parent.mkdir(parents=True, exist_ok=True)
        managed.write_bytes(b'fixture-python')
        copytree_new(runtime, archive_runtime)
        if not (archive_runtime / 'cpython-3.12.13-windows-x86_64-none' / 'python.exe').is_file():
            raise RuntimeError('Fresh append-only runtime archive lifecycle did not persist the managed interpreter.')
        # A second immutable write to the same leaf must still be rejected.
        try:
            copytree_new(runtime, archive_runtime)
        except RuntimeError as exc:
            if 'Append-only destination already exists' not in str(exc):
                raise
        else:
            raise RuntimeError('Fresh append-only lifecycle admitted an overwrite of an immutable artifact leaf.')
    print('OCR APPEND-ONLY FRESH BUNDLE LIFECYCLE SELF-TEST PASS')



def _append_only_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix='kr-ocr-append-only-fixture-') as td:
        root = Path(td) / 'runtime'
        archive = Path(td) / 'archive'
        base = LocalOCRFoundation(root, archive)
        ensure_base_structure(base)
        legacy = root / 'legacy-locked-do-not-touch'
        legacy.mkdir(parents=True)
        (legacy / 'sentinel.txt').write_text('KEEP', encoding='utf-8')
        context = create_context(base, bundle_id='fixture_bundle')
        ensure_candidate_structure(context.candidate)
        if not (legacy / 'sentinel.txt').is_file():
            raise RuntimeError('Append-only context touched a legacy Owner-local directory.')
        # Activation is pointer-only and must not move or delete the candidate.
        for path in (
            context.candidate.paddle_python,
            context.candidate.paddle_worker,
            context.candidate.pdftoppm,
            context.candidate.pdftotext,
            context.candidate.pdfinfo,
            context.candidate.pdffonts,
            context.candidate.tesseract,
            context.candidate.root / 'models/paddleocr/PP-OCRv5_server_det/model.pdmodel',
            context.candidate.root / 'models/paddleocr/PP-OCRv5_server_rec/model.pdmodel',
            context.candidate.root / 'models/paddleocr/PP-OCRv5_mobile_det/model.pdmodel',
            context.candidate.root / 'models/paddleocr/PP-OCRv5_mobile_rec/model.pdmodel',
            context.candidate.root / 'tessdata/fast/eng.traineddata',
            context.candidate.root / 'tessdata/fast/chi_sim.traineddata',
            context.candidate.root / 'tessdata/fast/chi_tra.traineddata',
            context.candidate.root / 'tessdata/fast/osd.traineddata',
            context.candidate.root / 'tessdata/best/eng.traineddata',
            context.candidate.root / 'tessdata/best/chi_sim.traineddata',
            context.candidate.root / 'tessdata/best/chi_tra.traineddata',
            context.candidate.root / 'tessdata/best/osd.traineddata',
            context.candidate.resource_root / 'manifests/RESOURCE_MANIFEST.json',
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'x')
        activate_context(context)
        if base.runtime_root != context.candidate.root:
            raise RuntimeError('Active pointer did not resolve the versioned deployment.')
        if base.archive_root != context.candidate.resource_root:
            raise RuntimeError('Active pointer did not resolve the immutable archive bundle.')
        if not (legacy / 'sentinel.txt').is_file():
            raise RuntimeError('Activation touched a legacy Owner-local directory.')
    print('OCR APPEND-ONLY DEPLOYMENT SELF-TEST PASS')


def self_test() -> int:
    foundation = LocalOCRFoundation(Path('C:/dev/KR_OCR_Local'), Path.home() / 'OneDrive/Documents/KRG/KRG Code/_Resource/KR_OCR_Offline_Resources')
    env = online_env()
    for name in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_DATASETS_OFFLINE'):
        if name in env:
            raise RuntimeError(f'Online environment leaked offline-only variable: {name}')
    if env.get('HF_HUB_DISABLE_SYMLINKS') != '1':
        raise RuntimeError('Windows-safe no-symlink mode missing.')
    if len(TESSERACT_SOURCES) < 2:
        raise RuntimeError('Tesseract acquisition requires multiple mirrors.')
    if foundation.root == foundation.resource_root:
        raise RuntimeError('Runtime copy and archive root must remain separate.')
    if 'KR_OCR_Offline_Resources' not in str(foundation.resource_root):
        raise RuntimeError('Governed OCR archive path contract missing.')
    _runtime_locator_self_test()
    _append_only_fresh_bundle_lifecycle_self_test()
    _append_only_self_test()
    print('OCR FOUNDATION SELF-TEST PASS')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test-only', action='store_true')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--activate', action='store_true')
    parser.add_argument('--activate-report', type=Path)
    args = parser.parse_args(argv)
    if args.self_test_only:
        result = self_test()
        if args.report:
            write_foundation_report(args.report, {'ok': result == 0, 'mode': 'self-test-only', 'entrypoint': True})
        return result
    if args.activate_report:
        activate_from_report(args.activate_report)
        return 0
    report = execute(report_path=args.report, activate=args.activate)
    return 0 if report.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
