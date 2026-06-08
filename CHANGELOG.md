# Changelog

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
