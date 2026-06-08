# Changelog

## 2.0.0 — Istanbul Release 2.0

- Added portable Windows x64 onedir executable packaging with no console window.
- Added timestamped auto-scrolling runtime log.
- Added green-highlighted, auto-centered current Part with dynamic estimated progress.
- Added Linux and Windows CI jobs with portable smoke validation.
- Added public GUI screenshot and bilingual README branding.
- Added complete integer-Release AI co-coder takeover handoff.

## 1.3.4

- declare Pillow in the test extra and package branding assets inside the Python distribution;
- run GitHub Actions only for `main`, pull requests and manual dispatch;
- wait for green remote CI before creating a tag or GitHub Release;
- add explicit resume checkpoint states and guided legacy voice verification;
- preserve completed legacy MP3 files while the Owner compares preserved and candidate Part 1 previews;
- collapse older attempts by source hash, normalized source path or ordered part aggregate, with an explicit Show older attempts option.

## Istanbul Release v1.3.3 - 2026-06-08

Branding surface checkpoint.

### Added

- Owner-provided BA SVG and PNG branding assets.
- Multi-resolution Windows ICO generated from the approved BA asset.
- Desktop title-bar, taskbar and Alt + Tab icon setup with missing-asset fallback.
- Bottom footer with `COPYRIGHT © KENT REIS` on the left and `KAIROS REPÚBLICA` on the right.

## Istanbul Release v1.3.2 - 2026-06-08

Resume speech-control rehydration and recent-attempt deduplication hotfix.

### Fixed

- Persist task-bound provider, voice, rate, pitch and volume controls.
- Restore stored controls before one-click resume.
- Recover legacy default controls by audio-signature matching.
- Replace low-level preview-gate RuntimeError with an actionable legacy-task message when controls cannot be proven.
- Resume directly from the first incomplete Part.
- Collapse older resumable attempts for the same source book from the default panel.

## Istanbul Release v1.3.1 - 2026-06-08

Recent-jobs usability and validation-state isolation hotfix.

### Fixed

- Isolate validation fixtures from the Owner-local execution history.
- Prune missing-manifest history entries automatically.
- Show only interrupted or incomplete resumable jobs in the GUI.
- Replace raw idle states and ISO timestamps with actionable labels and compact local time.
- Move keep-awake control into the long-running-operations section.

## Istanbul Release v1.3.0 - 2026-06-08

Durable resume, Recent jobs and automatic sleep prevention.

### Added

- Stable application-level `execution_history.json` recent-job index.
- Authoritative per-job execution checkpoints with PID, heartbeat, current Part and resume state.
- Recent jobs desktop panel with one-click resume, output-folder access and non-destructive history hiding.
- Conservative stale-lock recovery after confirming the prior process is dead.
- Partial MP3 cleanup, sidecar metadata and safe orphan-MP3 reconciliation.
- Automatic Windows keep-awake during long OCR and TTS work.
- OCR provider page-checkpoint capability declarations and OCR execution-state snapshots.
- CLI commands for recent-job listing and recovery.

### Fixed

- Resume selected now continues from the first incomplete Part when approvals remain valid.
- Malformed lock files remain blocked instead of being deleted automatically.

## Istanbul Release v1.2.0 - 2026-06-08

OCR Advisor Foundation, provider registries and multilingual desktop UX.

### Added

- OCR applicability and necessity analysis.
- Local OCR discovery for PaddleOCR, Tesseract, OCRmyPDF, Tesseract language packs and advisory GPU availability.
- Automatic local OCR recommendation with sample-page preview and full OCR actions.
- Shared OCR and TTS provider contracts.
- Reserved disabled API adapter slots for OpenAI Vision, Claude Vision, custom HTTP OCR, Azure Speech, OpenAI TTS and custom HTTP TTS.
- Readonly TTS-engine selector with edge-tts as the only enabled provider.
- Cached, refreshable voice dropdown with profile-based filtering and Show-all override.
- Processing profiles for auto, Chinese, English, mixed Chinese-English and general prose.
- Automatic cleanup advisor with not-needed, recommended and review-required outcomes.
- High-confidence cleanup action buttons with backup and stale-state invalidation.
- Estimated Part-1 and current-part progress plus exact overall progress.

### Fixed

- Preserve ambiguous repeated text instead of deleting review-required candidates.
- Include TTS provider ID in audio signatures so future provider changes invalidate stale audio.

## Istanbul Release v1.1.1 - 2026-06-08

Windows PDF and GUI cleanup hotfix.

### Fixed

- Read Poppler output as bytes before decoding so Windows console-code-page assumptions cannot crash PDF preparation.
- Fall back safely to the source filename when PDF metadata output is empty or unusable.

### Changed

- Add compact hover help and explicit default-folder actions.
- Remove the unrelated Traditional-to-Simplified conversion feature.

## Istanbul Release v1.1.0 - 2026-06-08

Production Run Safety release.

### Added

- Proofreading and Part-1 listening approval gates.
- Manifest-bound stale-audio invalidation, targeted retry, logging and strict merge validation.
- One-job-at-a-time locking and improved PDF diagnosis.

## Istanbul Release v1.0.0 - 2026-06-08

Founding public release.

- Correct the Windows PyInstaller spec-root contract: treat `SPECPATH` as the spec directory, use one parent traversal and preload `src` before hook-based package-data collection.
