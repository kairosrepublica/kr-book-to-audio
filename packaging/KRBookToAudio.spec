# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from pathlib import Path
import sys

# PyInstaller provides SPECPATH as the directory containing this spec file.
# Resolve the frozen public-payload root from that directory exactly once.
SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parent
SRC = ROOT / 'src'
ENTRY = SRC / 'kr_book_to_audio_gui.py'
ICON = SRC / 'kr_book_to_audio' / 'assets' / 'branding' / 'kr_book_to_audio.ico'

# Hook utilities execute before Analysis applies pathex, so make the src-layout
# package importable before collecting package data and provider submodules.
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

datas = collect_data_files('kr_book_to_audio')
hiddenimports = collect_submodules('edge_tts') + ['kr_book_to_audio.gui_runtime_probe']

a = Analysis(
    [str(ENTRY)],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KRBookToAudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='KRBookToAudio',
)
