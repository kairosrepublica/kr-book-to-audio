from __future__ import annotations
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from datetime import datetime, timezone

REQUIRED_MODELS = ('hexgrad/Kokoro-82M', 'hexgrad/Kokoro-82M-v1.1-zh')
QWEN_BENCHMARK_MODELS = ('Qwen/Qwen3-TTS-Tokenizer-12Hz', 'Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice')
KOKORO_PACKAGE = 'kokoro==0.9.4'
KOKORO_REQUIREMENTS = (KOKORO_PACKAGE, 'soundfile', 'huggingface_hub', 'misaki[en]', 'misaki[zh]')
UV_PACKAGE = 'uv==0.11.19'
KOKORO_RUNTIME_REQUEST = '3.12'
KOKORO_MIN = (3, 10)
KOKORO_MAX_EXCLUSIVE = (3, 13)
OFFLINE_VARIABLES = ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_DATASETS_OFFLINE')
HF_CACHE_NO_SYMLINK_VARIABLES = ('HF_HUB_DISABLE_SYMLINKS', 'HF_HUB_DISABLE_SYMLINKS_WARNING')
MIN_RESOURCE_FREE_BYTES = 8 * 1024 * 1024 * 1024


def run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    print('+', ' '.join(args), flush=True)
    return subprocess.run(args, check=True, **kwargs)


def python_in(env: Path) -> Path:
    return env / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def uv_in(env: Path) -> Path:
    return env / ('Scripts/uv.exe' if os.name == 'nt' else 'bin/uv')


def default_resource_archive_root() -> Path:
    if os.name == 'nt':
        return Path.home() / 'OneDrive' / 'Documents' / 'KRG' / 'KRG Code' / '_Resource' / 'KR_TTS_Offline_Resources'
    return Path.home() / '.kr_tts_offline_resources'


def python_version(py: Path) -> tuple[int, int, int]:
    result = run(
        [str(py), '-c', 'import sys; print(".".join(map(str, sys.version_info[:3])))'],
        text=True,
        capture_output=True,
    )
    parts = tuple(int(item) for item in result.stdout.strip().split('.'))
    if len(parts) != 3:
        raise RuntimeError(f'Could not parse Python version from {py}: {result.stdout!r}')
    return parts


def kokoro_python_version_is_supported(version: tuple[int, int, int]) -> bool:
    return KOKORO_MIN <= tuple(version[:2]) < KOKORO_MAX_EXCLUSIVE


def uv_runtime_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env['UV_PYTHON_INSTALL_DIR'] = str(root / 'runtimes' / 'uv-python')
    env['UV_PYTHON_BIN_DIR'] = str(root / 'runtimes' / 'uv-python-bin')
    env['UV_PYTHON_INSTALL_BIN'] = '0'
    env['UV_PYTHON_INSTALL_REGISTRY'] = '0'
    env['UV_PYTHON_NO_REGISTRY'] = '1'
    env['UV_NO_MODIFY_PATH'] = '1'
    env['UV_NO_CONFIG'] = '1'
    env['UV_MANAGED_PYTHON'] = '1'
    return env


def online_acquisition_env(*, hf_home: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for key in OFFLINE_VARIABLES:
        env.pop(key, None)
        env[key] = '0'
    env['HF_HUB_DISABLE_SYMLINKS'] = '1'
    env['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
    env.pop('PIP_NO_INDEX', None)
    env.pop('PIP_FIND_LINKS', None)
    if hf_home is not None:
        env['HF_HOME'] = str(hf_home)
        env['HUGGINGFACE_HUB_CACHE'] = str(hf_home / 'hub')
    return env


def worker_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env['HF_HOME'] = str(root / 'hf_cache')
    env['HUGGINGFACE_HUB_CACHE'] = str(root / 'hf_cache' / 'hub')
    for key in OFFLINE_VARIABLES:
        env[key] = '1'
    env['HF_HUB_DISABLE_SYMLINKS'] = '1'
    env['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
    env['KR_B2A_LOCAL_TTS_ROOT'] = str(root)
    return env


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def mirror_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise RuntimeError(f'Cannot mirror missing directory: {source}')
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)


def repo_cache_name(repo_id: str) -> str:
    return 'models--' + repo_id.replace('/', '--')


def require_repo_cache(hub_root: Path, repo_id: str) -> Path:
    repo = hub_root / repo_cache_name(repo_id)
    snapshots = repo / 'snapshots'
    if not snapshots.is_dir() or not any(item.is_dir() for item in snapshots.iterdir()):
        raise RuntimeError(f'Verified snapshot cache is missing for {repo_id}: {repo}')
    return repo


def archive_repo_from_staging(*, staging_hub: Path, archive_hub: Path, repo_id: str) -> Path:
    source = require_repo_cache(staging_hub, repo_id)
    destination = archive_hub / repo_cache_name(repo_id)
    mirror_tree(source, destination)
    require_repo_cache(archive_hub, repo_id)
    print(f'ARCHIVE MODEL PASS: {repo_id} -> {destination}', flush=True)
    return destination


def deploy_repo_from_archive(*, archive_hub: Path, runtime_hub: Path, repo_id: str) -> Path:
    source = require_repo_cache(archive_hub, repo_id)
    destination = runtime_hub / repo_cache_name(repo_id)
    mirror_tree(source, destination)
    require_repo_cache(runtime_hub, repo_id)
    print(f'DEPLOY MODEL PASS: {repo_id} -> {destination}', flush=True)
    return destination


def ensure_archive_structure(resource_root: Path) -> None:
    for child in (
        'manifests', 'wheelhouse/uv', 'wheelhouse/kokoro_py312_win_amd64',
        'runtimes/uv-python', 'models/huggingface/hub', 'tools/kokoro_worker',
        'samples/zh', 'samples/en', '_staging', 'receipts',
    ):
        (resource_root / child).mkdir(parents=True, exist_ok=True)


def ensure_resource_space(resource_root: Path) -> None:
    existing = resource_root
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if not existing.exists():
        raise RuntimeError(f'No existing parent is available for resource archive: {resource_root}')
    free = shutil.disk_usage(existing).free
    print(f'RESOURCE ARCHIVE FREE BYTES: {free}', flush=True)
    if free < MIN_RESOURCE_FREE_BYTES:
        raise RuntimeError(f'Resource archive requires at least {MIN_RESOURCE_FREE_BYTES} free bytes: {resource_root}')


def ensure_uv(root: Path, resource_root: Path) -> Path:
    bootstrap = root / 'envs' / 'uv-bootstrap'
    py = python_in(bootstrap)
    if not py.exists():
        venv.EnvBuilder(with_pip=True).create(bootstrap)
    uv_wheelhouse = resource_root / 'wheelhouse' / 'uv'
    uv_wheelhouse.mkdir(parents=True, exist_ok=True)
    run([str(py), '-m', 'pip', 'download', '--dest', str(uv_wheelhouse), UV_PACKAGE], env=online_acquisition_env())
    run([str(py), '-m', 'pip', 'install', '--no-index', '--find-links', str(uv_wheelhouse), '--upgrade', UV_PACKAGE])
    uv = uv_in(bootstrap)
    if not uv.is_file():
        raise RuntimeError(f'uv executable was not created: {uv}')
    run([str(uv), '--version'])
    return uv


def find_managed_python(root: Path) -> Path:
    candidates = sorted((root / 'runtimes' / 'uv-python').rglob('python.exe' if os.name == 'nt' else 'python'))
    for candidate in candidates:
        if candidate.is_file() and kokoro_python_version_is_supported(python_version(candidate)):
            return candidate
    raise RuntimeError(f'uv-managed Python {KOKORO_RUNTIME_REQUEST} was not found under {root / "runtimes" / "uv-python"}')


def ensure_kokoro_python(root: Path, resource_root: Path, uv: Path) -> tuple[Path, str]:
    env = root / 'envs' / 'kokoro'
    py = python_in(env)
    if py.exists():
        version = python_version(py)
        if kokoro_python_version_is_supported(version) and (root / 'runtimes' / 'uv-python').is_dir():
            mirror_tree(root / 'runtimes' / 'uv-python', resource_root / 'runtimes' / 'uv-python')
            print(f'KOKORO RUNTIME REUSE PASS: {py} Python {version}', flush=True)
            return py, 'reused-compatible-runtime-and-archived-managed-python'
        if kokoro_python_version_is_supported(version):
            print(f'KOKORO RUNTIME REBUILD: compatible environment lacks governed managed-runtime source at {root / "runtimes" / "uv-python"}', flush=True)
            shutil.rmtree(env)
        else:
            print(f'KOKORO RUNTIME REBUILD: incompatible Python {version} at {py}', flush=True)
            shutil.rmtree(env)
    elif env.exists():
        print(f'KOKORO RUNTIME REBUILD: incomplete environment at {env}', flush=True)
        shutil.rmtree(env)
    managed_env = uv_runtime_env(root)
    (root / 'runtimes' / 'uv-python').mkdir(parents=True, exist_ok=True)
    (root / 'runtimes' / 'uv-python-bin').mkdir(parents=True, exist_ok=True)
    run([str(uv), 'python', 'install', KOKORO_RUNTIME_REQUEST], env=managed_env)
    managed_python = find_managed_python(root)
    mirror_tree(root / 'runtimes' / 'uv-python', resource_root / 'runtimes' / 'uv-python')
    run([str(managed_python), '-m', 'venv', str(env)])
    py = python_in(env)
    if not py.is_file():
        raise RuntimeError(f'Kokoro environment Python was not created: {py}')
    version = python_version(py)
    if not kokoro_python_version_is_supported(version):
        raise RuntimeError(f'Kokoro Python is outside supported range: {version}')
    print(f'KOKORO RUNTIME CREATE PASS: {py} Python {version}', flush=True)
    return py, 'created-isolated-uv-managed-python-3.12'


def build_kokoro_wheelhouse(py: Path, resource_root: Path) -> Path:
    wheelhouse = resource_root / 'wheelhouse' / 'kokoro_py312_win_amd64'
    wheelhouse.mkdir(parents=True, exist_ok=True)
    run([str(py), '-m', 'pip', 'wheel', '--wheel-dir', str(wheelhouse), *KOKORO_REQUIREMENTS], env=online_acquisition_env())
    if not any(wheelhouse.iterdir()):
        raise RuntimeError(f'Kokoro wheelhouse is empty: {wheelhouse}')
    print(f'WHEELHOUSE ARCHIVE PASS: {wheelhouse}', flush=True)
    return wheelhouse


def install_kokoro_from_wheelhouse(py: Path, wheelhouse: Path) -> None:
    run([str(py), '-m', 'pip', 'install', '--no-index', '--find-links', str(wheelhouse), *KOKORO_REQUIREMENTS])
    run([str(py), '-c', 'import kokoro, huggingface_hub, soundfile; print("KOKORO IMPORT PASS")'])


def download_model_to_archive(py: Path, resource_root: Path, repo_id: str) -> Path:
    archive_hub = resource_root / 'models' / 'huggingface' / 'hub'
    try:
        existing = require_repo_cache(archive_hub, repo_id)
    except RuntimeError:
        existing = None
    if existing is not None:
        print(f'ARCHIVE MODEL REUSE PASS: {repo_id} -> {existing}', flush=True)
        return existing
    safe = repo_id.replace('/', '--')
    staging_root = resource_root / '_staging' / ('hf-' + safe)
    staging_hf = staging_root / 'hf_cache'
    staging_hub = staging_hf / 'hub'
    staging_hub.mkdir(parents=True, exist_ok=True)
    downloader = """
from huggingface_hub import snapshot_download
import sys
repo_id=sys.argv[1]
cache_dir=sys.argv[2]
print('ONLINE ACQUIRE', repo_id, flush=True)
snapshot=snapshot_download(repo_id=repo_id, cache_dir=cache_dir)
print('ONLINE ACQUIRE PASS', repo_id, snapshot, flush=True)
"""
    print(f'PERSISTENT STAGING: {repo_id} -> {staging_root}', flush=True)
    run([str(py), '-c', downloader, repo_id, str(staging_hub)], env=online_acquisition_env(hf_home=staging_hf))
    archived = archive_repo_from_staging(staging_hub=staging_hub, archive_hub=archive_hub, repo_id=repo_id)
    shutil.rmtree(staging_root, ignore_errors=True)
    return archived


def deploy_required_models(resource_root: Path, root: Path) -> None:
    archive_hub = resource_root / 'models' / 'huggingface' / 'hub'
    runtime_hub = root / 'hf_cache' / 'hub'
    runtime_hub.mkdir(parents=True, exist_ok=True)
    for repo_id in REQUIRED_MODELS:
        deploy_repo_from_archive(archive_hub=archive_hub, runtime_hub=runtime_hub, repo_id=repo_id)


def generate_sample(py: Path, worker: Path, root: Path, *, text: str, voice: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='kr-b2a-kokoro-sample-') as td:
        request = Path(td) / 'request.json'
        request.write_text(json.dumps({'text': text, 'voice': voice, 'speed': 1.0, 'output': str(destination)}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        run([str(py), str(worker), '--request', str(request)], env=worker_env(root))
    if not destination.exists() or destination.stat().st_size <= 0:
        raise RuntimeError(f'Local sample was not created: {destination}')


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def resource_manifest(resource_root: Path, *, report: dict[str, object]) -> tuple[Path, Path, Path]:
    manifests = resource_root / 'manifests'
    manifests.mkdir(parents=True, exist_ok=True)
    receipt = resource_root / 'receipts' / 'INSTALL_RECEIPT_PRIVATE.md'
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        '# KR TTS Offline Resource Archive Install Receipt — PRIVATE\n\n'
        '```text\n'
        f'generated: {datetime.now(timezone.utc).isoformat()}\n'
        f'archive_root: {resource_root}\n'
        f'runtime_copy: {report.get("runtime_root")}\n'
        f'kokoro_python: {report.get("kokoro_python")}\n'
        f'qwen_benchmark_status: {report.get("qwen_benchmark_status")}\n'
        'resource_policy: archive first, deploy second; runtime worker offline only\n'
        '```\n',
        encoding='utf-8',
    )
    excluded = {
        'manifests/RESOURCE_MANIFEST.json',
        'manifests/SHA256SUMS.txt',
    }
    entries: dict[str, str] = {}
    for path in sorted(item for item in resource_root.rglob('*') if item.is_file()):
        rel = str(path.relative_to(resource_root)).replace('\\', '/')
        if rel.startswith('_staging/') or rel in excluded:
            continue
        entries[rel] = sha256_file(path)
    sums = manifests / 'SHA256SUMS.txt'
    sums.write_text(''.join(f'{digest}  {rel}\n' for rel, digest in sorted(entries.items())), encoding='ascii')
    manifest = manifests / 'RESOURCE_MANIFEST.json'
    payload = {
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'archive_root': str(resource_root),
        'policy': 'AUTHORITATIVE_PRIVATE_RESOURCE_ARCHIVE; ARCHIVE_FIRST_DEPLOY_SECOND',
        'runtime_copy': report.get('runtime_root'),
        'required_models': list(REQUIRED_MODELS),
        'qwen_benchmark_models': list(QWEN_BENCHMARK_MODELS),
        'qwen_benchmark_status': report.get('qwen_benchmark_status'),
        'file_count': len(entries),
        'files': entries,
    }
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'RESOURCE MANIFEST PASS: {manifest}', flush=True)
    return manifest, sums, receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Acquire TTS resources online into a governed private archive, then deploy an offline Kokoro runtime copy.')
    parser.add_argument('--root', default=os.environ.get('KR_B2A_LOCAL_TTS_ROOT') or (r'C:\dev\KR_TTS_Local' if os.name == 'nt' else str(Path.home() / '.kr_tts_local')))
    parser.add_argument('--resource-archive-root', default=os.environ.get('KR_B2A_TTS_RESOURCE_ARCHIVE_ROOT') or str(default_resource_archive_root()))
    parser.add_argument('--download-qwen-benchmark', action='store_true')
    parser.add_argument('--skip-samples', action='store_true')
    args = parser.parse_args(argv)
    root = Path(args.root)
    resource_root = Path(args.resource_archive_root)
    ensure_resource_space(resource_root)
    ensure_archive_structure(resource_root)
    for child in ('envs', 'runtimes/uv-python', 'runtimes/uv-python-bin', 'workers/kokoro_worker', 'hf_cache/hub', 'samples/zh', 'samples/en', 'reports', 'logs'):
        (root / child).mkdir(parents=True, exist_ok=True)
    uv = ensure_uv(root, resource_root)
    py, runtime_strategy = ensure_kokoro_python(root, resource_root, uv)
    wheelhouse = build_kokoro_wheelhouse(py, resource_root)
    install_kokoro_from_wheelhouse(py, wheelhouse)
    worker_source = Path(__file__).with_name('kokoro_worker.py')
    worker_target = root / 'workers' / 'kokoro_worker' / 'kokoro_worker.py'
    copy_file(worker_source, worker_target)
    copy_file(worker_source, resource_root / 'tools' / 'kokoro_worker' / 'kokoro_worker.py')
    for repo_id in REQUIRED_MODELS:
        download_model_to_archive(py, resource_root, repo_id)
    deploy_required_models(resource_root, root)
    qwen_status = 'not-requested'
    qwen_error = None
    if args.download_qwen_benchmark:
        try:
            for repo_id in QWEN_BENCHMARK_MODELS:
                download_model_to_archive(py, resource_root, repo_id)
            qwen_status = 'archived'
        except Exception as exc:
            qwen_status = 'deferred-after-download-error'
            qwen_error = f'{type(exc).__name__}: {exc}'
            print('WARNING: Qwen3-TTS benchmark archive did not complete. Kokoro Local remains operational.', flush=True)
            print(qwen_error, flush=True)
    samples = []
    if not args.skip_samples:
        zh = root / 'samples' / 'zh' / 'kokoro-zf_001.wav'
        en = root / 'samples' / 'en' / 'kokoro-af_heart.wav'
        generate_sample(py, worker_target, root, text='这是离线中文语音测试。长期任务不再依赖网络连接。', voice='zf_001', destination=zh)
        generate_sample(py, worker_target, root, text='This is an offline English voice test. Long jobs no longer depend on a network connection.', voice='af_heart', destination=en)
        samples = [str(zh), str(en)]
        copy_file(zh, resource_root / 'samples' / 'zh' / zh.name)
        copy_file(en, resource_root / 'samples' / 'en' / en.name)
    report = {
        'runtime_root': str(root),
        'resource_archive_root': str(resource_root),
        'owner_python': sys.version,
        'kokoro_python': str(py),
        'kokoro_python_version': '.'.join(map(str, python_version(py))),
        'kokoro_runtime_strategy': runtime_strategy,
        'kokoro_package': KOKORO_PACKAGE,
        'uv_package': UV_PACKAGE,
        'owner_global_python_changed': False,
        'owner_path_changed': False,
        'owner_registry_changed': False,
        'online_acquisition_environment': {key: online_acquisition_env().get(key) for key in OFFLINE_VARIABLES},
        'offline_worker_environment': {key: worker_env(root).get(key) for key in OFFLINE_VARIABLES},
        'kokoro_worker': str(worker_target),
        'required_models_archived': list(REQUIRED_MODELS),
        'required_models_deployed': list(REQUIRED_MODELS),
        'qwen_benchmark_models_requested': list(QWEN_BENCHMARK_MODELS) if args.download_qwen_benchmark else [],
        'qwen_benchmark_status': qwen_status,
        'qwen_benchmark_error': qwen_error,
        'samples': samples,
    }
    manifest, sums, receipt = resource_manifest(resource_root, report=report)
    report['resource_manifest'] = str(manifest)
    report['resource_sha256sums'] = str(sums)
    report['resource_install_receipt'] = str(receipt)
    report_path = root / 'reports' / 'local_tts_foundation.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    copy_file(report_path, resource_root / 'receipts' / report_path.name)
    resource_manifest(resource_root, report=report)
    print('LOCAL TTS FOUNDATION PASS', flush=True)
    print(report_path, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
