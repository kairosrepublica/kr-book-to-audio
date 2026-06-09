# KR Book To Audio — Istanbul Release v2.4.0

## Scope

This Release closes the long-running Edge Online TTS observability gap, adds an operational offline fallback and cleans the user-facing deliverable boundary.

## Edge Online resilience

- Stream real audio bytes rather than waiting inside one opaque save call.
- Show Provider stage, elapsed time, received bytes, last-audio age and retry attempt.
- Enforce no-audio and total-Part watchdogs.
- Retry with bounded backoff and show possible network or Provider-side causes.
- Recommend switching to Kokoro Local after Edge Online failure.

## Local Provider

- Add Kokoro Local TTS as the operational offline fallback.
- Keep the local environment and model cache under `C:\dev\KR_TTS_Local`.
- Prepare optional Qwen3-TTS 0.6B CustomVoice benchmark weights without making them a blocking runtime dependency.
- Preserve the Preview Part 1 approval gate whenever Provider changes.

## Diagnostics

- Add **Export diagnostic ZIP** and **Open diagnostics folder** actions.
- Export sanitized `run.log` and runtime summary only.
- Exclude book body text, MP3 files, credentials and unnecessary absolute paths.

## Flat Export

The human-facing Export folder contains direct verified Part MP3 files, an optional merged MP3 and one reviewed cleaned-text TXT named after the book title. It contains no subfolders and no internal JSON files. Legacy `parts` folders are flattened only after verification and conflicts stop safely without overwrite.

## Frozen subsystems

SQLite durable state, Resume semantics, OCR, text chunking and quiet-export receipt reuse remain preserved.

## Isolated Kokoro runtime compatibility

The local foundation setup detects Python-version incompatibility before installing Kokoro. Kokoro 0.9.4 is installed into an isolated Owner-local Python 3.12 runtime provisioned through pinned `uv==0.11.19`. Existing incompatible partial environments are recreated safely. Owner global Python, `PATH` and registry configuration remain unchanged.

## Governed offline-resource archive

The Local Provider foundation now separates online acquisition from offline execution. Reusable Kokoro wheels, the isolated Python runtime, model snapshots, optional Qwen benchmark snapshots, samples and SHA-256 receipts are mirrored into the Owner-private `_Resource\KR_TTS_Offline_Resources` archive before deployment into the rebuildable `C:\dev\KR_TTS_Local` runtime copy.

## Windows-safe resumable model acquisition

Local Provider bootstrap disables Hugging Face cache symlinks and uses persistent `_Resource` staging. This prevents Windows privilege failures on ordinary non-administrator sessions and preserves partial model downloads for later resume.
