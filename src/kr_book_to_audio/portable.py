from __future__ import annotations
from pathlib import Path
import argparse
import json
import os
import sys
from .config import app_root, execution_history_path, local_work_root
from .gui import BRANDING_ICO, BRANDING_PNG, branding_asset_path
from .providers import registry_snapshot
from .utils import atomic_write_json


def portable_smoke_report() -> dict:
    """Return a relocation-safe, no-network portable runtime report."""
    frozen = bool(getattr(sys, 'frozen', False))
    meipass = getattr(sys, '_MEIPASS', None)
    ico = branding_asset_path(BRANDING_ICO)
    png = branding_asset_path(BRANDING_PNG)
    report = {
        'ok': bool(ico and png),
        'frozen': frozen,
        'meipass': str(meipass) if meipass else None,
        'executable': str(Path(sys.executable).resolve()),
        'cwd': str(Path.cwd().resolve()),
        'branding_ico': str(ico.resolve()) if ico else None,
        'branding_png': str(png.resolve()) if png else None,
        'app_root': str(app_root().resolve()),
        'jobs_root': str(local_work_root().resolve()),
        'execution_history': str(execution_history_path().resolve()),
        'provider_registry': registry_snapshot(),
        'console_attached': bool(sys.stdout or sys.stderr),
        'kr_b2a_app_root_override': os.environ.get('KR_B2A_APP_ROOT'),
    }
    if not report['ok']:
        raise RuntimeError('Portable smoke test could not resolve required branding assets.')
    return report


def write_portable_smoke_report(path: Path) -> dict:
    report = portable_smoke_report()
    atomic_write_json(path, report)
    return report


def portable_main(argv: list[str] | None = None) -> int | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--portable-smoke-test', type=Path)
    args, _unknown = parser.parse_known_args(argv)
    if not args.portable_smoke_test:
        return None
    write_portable_smoke_report(args.portable_smoke_test)
    return 0
