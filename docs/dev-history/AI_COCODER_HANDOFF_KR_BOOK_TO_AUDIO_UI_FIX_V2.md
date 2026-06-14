# AI Co-Coder Handoff - KR Book To Audio 3.0 UI Fix V2

## Start here

Baseline: V32 source package, not V35-V43.

Current update package applies only UI-facing changes:

- Status percent synchronization.
- Treeview anti-jitter by removing percent-tick recentering.
- smoother estimated progress display near completion.
- diagnostic-log throttling.

## Files committed by this package

- Full latest source tree from `20260614_1125_KR_BOOK_TO_AUDIO_V32_SOURCE_UI_SMOOTHER_PROGRESS_DIAGNOSTIC_LOG_PATCHED.zip`.
- Release notes for UI Fix V2.
- Sanitized V32-V43 development record.
- Owner runtime screenshot: `docs/images/kr_book_to_audio_3_0_ui_status_runtime_20260614.png`.
- V2 EXE builder script under `tools/build/`.
- V2 diff and validation report under `docs/`.

## Do not do this

- Do not continue from V35-V43 unless explicitly needed.
- Do not add new fixture layers for UI-only problems.
- Do not touch OCR, TTS provider internals, resume, reload, reject, save-job, layout, colors, or fonts unless the Owner reopens scope.

## How to rebuild EXE

Run the builder script from the repository root or from its containing folder after dependencies are available:

```powershell
python .\tools\build\20260614_1125_BUILD_KR_BOOK_TO_AUDIO_V32_UI_FIX_V2_EXE.py
```

The builder produces a portable ZIP in Downloads and a JSON build report in the build evidence folder.
