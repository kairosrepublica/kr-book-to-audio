from __future__ import annotations
from pathlib import Path
import argparse, json, subprocess, sys, tempfile, zipfile

WINDOWS_GUI_SUBSYSTEM = 2

def inspect_pe(exe: Path) -> dict:
    try:
        import pefile
    except ImportError as exc:
        raise RuntimeError('pefile is required for portable verification. Install .[portable].') from exc
    pe = pefile.PE(str(exe), fast_load=False)
    subsystem = int(pe.OPTIONAL_HEADER.Subsystem)
    has_icon = False
    if hasattr(pe, 'DIRECTORY_ENTRY_RESOURCE'):
        for resource_type in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            if int(resource_type.id or 0) in {3, 14}:
                has_icon = True
                break
    return {'subsystem': subsystem, 'windows_gui_subsystem': subsystem == WINDOWS_GUI_SUBSYSTEM, 'has_icon_resource': has_icon}

def run_smoke(exe: Path, evidence: Path) -> dict:
    evidence.unlink(missing_ok=True)
    result = subprocess.run([str(exe), '--portable-smoke-test', str(evidence)], check=False, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f'Portable smoke-test process failed: returncode={result.returncode}')
    if not evidence.exists():
        raise RuntimeError('Portable smoke-test evidence was not written.')
    report = json.loads(evidence.read_text(encoding='utf-8'))
    if not report.get('ok') or not report.get('frozen'):
        raise RuntimeError(f'Portable smoke-test report rejected: {report}')
    return report

def build_zip(dist_dir: Path, output_zip: Path) -> Path:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    output_zip.unlink(missing_ok=True)
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(dist_dir.rglob('*')):
            if path.is_file():
                archive.write(path, f'KR Book To Audio Portable/{path.relative_to(dist_dir).as_posix()}')
    return output_zip

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--dist-dir', type=Path, required=True)
    ap.add_argument('--evidence', type=Path, required=True)
    ap.add_argument('--portable-zip', type=Path)
    args=ap.parse_args()
    exe=args.dist_dir/'KRBookToAudio.exe'
    if not exe.exists(): raise RuntimeError(f'Portable executable missing: {exe}')
    pe=inspect_pe(exe)
    if not pe['windows_gui_subsystem']: raise RuntimeError(f'Expected Windows GUI subsystem: {pe}')
    if not pe['has_icon_resource']: raise RuntimeError(f'Expected embedded icon resource: {pe}')
    smoke_evidence=args.evidence.with_name(args.evidence.stem+'-runtime.json')
    smoke=run_smoke(exe, smoke_evidence)
    report={'ok':True,'exe':str(exe.resolve()),'pe':pe,'smoke':smoke}
    args.evidence.parent.mkdir(parents=True,exist_ok=True)
    args.evidence.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')
    if args.portable_zip: build_zip(args.dist_dir,args.portable_zip)
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
