from __future__ import annotations
from pathlib import Path
import argparse
import json
from .audio import approve_preview, audition_sample, merge_parts, retry_failed_parts, synthesize_parts
from .config import DEFAULT_CHUNK_CJK, DEFAULT_PROCESSING_PROFILE, DEFAULT_RATE, DEFAULT_TTS_ENGINE, DEFAULT_VOICE, default_export_root, local_work_root
from .history import list_recent_jobs, rebuild_history, remove_from_history
from .export import finalize_export, verify_export
from .recovery import recover_job
from .extractors import diagnose
from .models import JobPaths
from .ocr import analyze_source, preview_sample_ocr, run_recommended_ocr
from .pipeline import approve_proofread_and_rebuild, apply_cleanup_and_rebuild, job_status, prepare_job, rebuild_parts
from .providers import provider_registry_snapshot


def _job(value: str) -> JobPaths:
    return JobPaths.from_root(Path(value))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Robust book-to-audiobook pipeline with multilingual processing and local OCR advisor.')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('diagnose'); p.add_argument('source')
    p = sub.add_parser('providers')
    p = sub.add_parser('recent-jobs'); p.add_argument('--rebuild', action='store_true'); p.add_argument('--work-root', default=str(local_work_root()))
    p = sub.add_parser('recover'); p.add_argument('job')
    p = sub.add_parser('history-remove'); p.add_argument('job_id')
    p = sub.add_parser('ocr-analyze'); p.add_argument('source')
    p = sub.add_parser('ocr-preview'); p.add_argument('source'); p.add_argument('--provider')
    p = sub.add_parser('ocr-run'); p.add_argument('source'); p.add_argument('--output-dir', required=True); p.add_argument('--provider'); p.add_argument('--allow-sleep', action='store_true')
    p = sub.add_parser('prepare')
    p.add_argument('source'); p.add_argument('--work-root', default=str(local_work_root())); p.add_argument('--export-root', default=str(default_export_root()))
    p.add_argument('--title'); p.add_argument('--dictionary'); p.add_argument('--chars', type=int, default=DEFAULT_CHUNK_CJK)
    p.add_argument('--profile', default=DEFAULT_PROCESSING_PROFILE, choices=['auto', 'chinese', 'english', 'mixed', 'general-prose'])
    p = sub.add_parser('rebuild'); p.add_argument('job'); p.add_argument('--dictionary'); p.add_argument('--chars', type=int)
    p = sub.add_parser('approve-proofread'); p.add_argument('job'); p.add_argument('--dictionary'); p.add_argument('--chars', type=int)
    p = sub.add_parser('cleanup'); p.add_argument('job'); p.add_argument('kind', choices=['repeated-headers-and-junk', 'metadata-date-time-tags']); p.add_argument('--dictionary')
    for command in ('tts', 'retry-failed', 'preview', 'approve-preview'):
        p = sub.add_parser(command); p.add_argument('job'); p.add_argument('--engine', default=DEFAULT_TTS_ENGINE); p.add_argument('--voice', default=DEFAULT_VOICE); p.add_argument('--rate', default=DEFAULT_RATE); p.add_argument('--retries', type=int, default=3)
        p.add_argument('--allow-sleep', action='store_true')
        if command == 'tts': p.add_argument('--start', type=int, default=1); p.add_argument('--end', type=int)
    p = sub.add_parser('audition'); p.add_argument('--engine', default=DEFAULT_TTS_ENGINE); p.add_argument('--voice', default=DEFAULT_VOICE); p.add_argument('--rate', default=DEFAULT_RATE); p.add_argument('--output-dir')
    p = sub.add_parser('merge'); p.add_argument('job'); p.add_argument('--name')
    p = sub.add_parser('finalize-export'); p.add_argument('job')
    p = sub.add_parser('verify-export'); p.add_argument('job'); p.add_argument('--require-merged', action='store_true')
    p = sub.add_parser('status'); p.add_argument('job')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == 'diagnose':
        print(json.dumps(diagnose(Path(args.source)), ensure_ascii=False, indent=2)); return 0
    if args.command == 'providers':
        print(json.dumps(provider_registry_snapshot(), ensure_ascii=False, indent=2)); return 0
    if args.command == 'recent-jobs':
        if args.rebuild: rebuild_history(Path(args.work_root))
        print(json.dumps(list_recent_jobs(), ensure_ascii=False, indent=2)); return 0
    if args.command == 'recover':
        print(json.dumps(recover_job(_job(args.job)), ensure_ascii=False, indent=2)); return 0
    if args.command == 'history-remove':
        remove_from_history(args.job_id); print(args.job_id); return 0
    if args.command == 'ocr-analyze':
        print(json.dumps(analyze_source(Path(args.source)).to_dict(), ensure_ascii=False, indent=2)); return 0
    if args.command == 'ocr-preview':
        analysis = analyze_source(Path(args.source)); print(json.dumps(preview_sample_ocr(Path(args.source), analysis, provider_id=args.provider), ensure_ascii=False, indent=2)); return 0
    if args.command == 'ocr-run':
        analysis = analyze_source(Path(args.source)); print(run_recommended_ocr(Path(args.source), analysis, output_dir=Path(args.output_dir), provider_id=args.provider, keep_awake=not args.allow_sleep)); return 0
    if args.command == 'audition':
        print(audition_sample(provider_id=args.engine, voice=args.voice, rate=args.rate, output_dir=Path(args.output_dir) if args.output_dir else None)); return 0
    if args.command == 'prepare':
        job = prepare_job(Path(args.source), work_root=Path(args.work_root), export_root=Path(args.export_root), title=args.title, processing_profile=args.profile, dictionary_path=Path(args.dictionary) if args.dictionary else None, chunk_chars=args.chars)
        print(json.dumps(job_status(job), ensure_ascii=False, indent=2)); return 0
    job = _job(args.job)
    if args.command == 'rebuild':
        print(json.dumps(rebuild_parts(job, dictionary_path=Path(args.dictionary) if args.dictionary else None, chunk_chars=args.chars), ensure_ascii=False, indent=2)); return 0
    if args.command == 'approve-proofread':
        print(json.dumps(approve_proofread_and_rebuild(job, dictionary_path=Path(args.dictionary) if args.dictionary else None, chunk_chars=args.chars), ensure_ascii=False, indent=2)); return 0
    if args.command == 'cleanup':
        print(json.dumps(apply_cleanup_and_rebuild(job, kind=args.kind, dictionary_path=Path(args.dictionary) if args.dictionary else None), ensure_ascii=False, indent=2)); return 0
    if args.command == 'tts':
        print(json.dumps(synthesize_parts(job, provider_id=args.engine, voice=args.voice, rate=args.rate, start=args.start, end=args.end, retries=args.retries, keep_awake=not args.allow_sleep), ensure_ascii=False, indent=2)); return 0
    if args.command == 'retry-failed':
        print(json.dumps(retry_failed_parts(job, provider_id=args.engine, voice=args.voice, rate=args.rate, retries=args.retries, keep_awake=not args.allow_sleep), ensure_ascii=False, indent=2)); return 0
    if args.command == 'preview':
        print(json.dumps(synthesize_parts(job, provider_id=args.engine, voice=args.voice, rate=args.rate, start=1, end=1, retries=args.retries, require_preview_approval=False, keep_awake=not args.allow_sleep), ensure_ascii=False, indent=2)); return 0
    if args.command == 'approve-preview':
        print(json.dumps(approve_preview(job, provider_id=args.engine, voice=args.voice, rate=args.rate), ensure_ascii=False, indent=2)); return 0
    if args.command == 'merge':
        print(merge_parts(job, output_name=args.name)); return 0
    if args.command == 'finalize-export':
        print(json.dumps(finalize_export(job), ensure_ascii=False, indent=2)); return 0
    if args.command == 'verify-export':
        print(json.dumps(verify_export(job, require_merged=args.require_merged), ensure_ascii=False, indent=2)); return 0
    if args.command == 'status':
        print(json.dumps(job_status(job), ensure_ascii=False, indent=2)); return 0
    raise AssertionError(args.command)

if __name__ == '__main__':
    raise SystemExit(main())
