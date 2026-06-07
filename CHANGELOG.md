# Changelog

## Istanbul Release v1.1.1 - 2026-06-08

Windows PDF and GUI cleanup hotfix.

### Fixed

- Read Poppler output as bytes before decoding so Windows console-code-page assumptions cannot crash PDF preparation.
- Fall back safely to the source filename when PDF metadata output is empty or unusable.
- Treat legacy configuration and manifest fields as migratable data rather than active conversion controls.

### Changed

- Add compact `ⓘ` hover help instead of long inline explanations.
- Add explicit default-folder actions for book picker, local working root and export root.
- Move metadata-like date/time cleanup into the **Optional cleanup** area.
- Remove the unrelated Traditional-to-Simplified conversion control, command-line option and optional dependency.

### Added

- Regression tests for mixed Windows Poppler output, `stdout=None`, Chinese PDF titles, configuration migration, manifest migration, compact GUI surface and date/time cleanup boundaries.

## Istanbul Release v1.1.0 - 2026-06-08

Production Run Safety release.

### Added

- Enforced proofreading approval bound to the current proofread-text SHA-256 hash.
- Enforced Part-1 listening approval bound to the current text and speech-control signature.
- Pronunciation-dictionary freshness check before synthesis.
- One-job-at-a-time cross-process operation lock.
- Persisted failed-part records and targeted retry command.
- Per-part GUI status table and overall progress bar.
- Durable JSON-line logs for synthesis attempts, retries, failures and merges.
- PDF extracted-text sampling in addition to font-row inspection.
- Tests for approval invalidation, retry, GUI busy guard, job locking, stale-audio merge rejection and PDF sampling.

### Changed

- Merge verifies manifest completion records, text hashes, speech signatures and MP3 hashes before joining files.
- Audio partial files use the inferable `.partial.mp3` naming convention.
- CLI adds `approve-proofread`, `approve-preview` and `retry-failed` commands.

## Istanbul Release v1.0.0 - 2026-06-08

Founding public release.

### Added

- Shared Python core for command-line and Tkinter desktop entry points.
- Automatic general-prose and Chinese-optimized cleaning modes.
- Chinese extraction cleanup with whitespace normalization, running-header removal and conservative reflow.
- Proofread file and user-editable pronunciation replacement dictionary.
- Manifest-driven resumability and stale-output invalidation.
- Atomic speech output with `ffprobe` validation.
- Strict merge completeness gate and numeric part ordering beyond 99 parts.
- Direct support for PDF, EPUB, MOBI or PalmDOC-compatible AZW or PRC, DOCX, TXT and Markdown.
- Explicit AZW3 rejection until a verified parser fixture exists.
