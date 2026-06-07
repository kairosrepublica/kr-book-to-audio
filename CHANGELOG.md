# Changelog

## Istanbul Release v1.0.0 - 2026-06-08

Founding public release.

### Added

- Shared Python core for command-line and Tkinter desktop entry points.
- Automatic general-prose and Chinese-optimized cleaning modes.
- Chinese extraction cleanup with whitespace normalization, running-header removal and conservative reflow.
- Optional OpenCC Traditional-to-Simplified conversion.
- Proofread gate and user-editable pronunciation replacement dictionary.
- Manifest-driven resumability and stale-output invalidation.
- Atomic speech output with `ffprobe` validation.
- Strict merge completeness gate and numeric part ordering beyond 99 parts.
- Direct support for PDF, EPUB, MOBI/PalmDOC-compatible AZW or PRC, DOCX, TXT and Markdown.
- Explicit AZW3 rejection until a verified parser fixture exists.
- Tests for Chinese normalization, long-paragraph splitting, stale-artifact removal, safe ZIP extraction, numeric ordering and merge-gap rejection.
