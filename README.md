# KR Book To Audio

**Possibly the world's best book-to-audio conversion software.**<br>
**可能是全世界最好用的 Book-to-Audio 转换软件。**

Built by Kent Reis from Constantinople with love.

Copyright © Kent Reis & Kairos República

KR Book To Audio is a Windows-first desktop application for turning real books, PDFs, OCR text and long-form documents into clean, resumable audiobook projects. It is built for long jobs, Chinese/English workflows, unstable providers, interrupted runs and human review before full synthesis.

## Istanbul Release 3.0

**Istanbul Release 3.0** is the current public release line.

![KR Book To Audio — Istanbul Release 3.0](docs/images/kr_book_to_audio_3_0_ui_status_runtime_20260614.png)

This release consolidates the 3.0 development sequence into a public checkpoint: clearer workflow stages, smoother progress reporting, visible part-level synthesis status, cleaner diagnostic logs, portable Windows distribution and a stronger recovery-first operating model.

## Features

- Windows desktop GUI for long-form book-to-audio conversion.
- Text-layer PDF, EPUB, MOBI, PalmDOC-compatible AZW/PRC, DOCX, TXT and Markdown intake.
- OCR workflow support for hard PDFs and image-only sources.
- Human review checkpoint before full audiobook synthesis.
- Voice selection, language-matched voice samples, rate and volume controls.
- First-part preview before synthesizing the entire book.
- Recoverable MP3 part generation and optional merged audiobook output.
- Durable job state, resume support and diagnostic receipts for interrupted runs.
- Portable Windows ZIP release artifact.

## Core functions

### 1. Book intake and source analysis

Select the book source, working root and export root, then analyze whether the source can be read directly or needs OCR. The application keeps OCR decisions visible instead of hiding them behind a black-box conversion.

### 2. OCR workflow for hard PDFs

Detect image-only or weak-text PDFs, preview OCR samples before committing to a full OCR run, and preserve receipts for long or interrupted OCR work.

### 3. Text preparation and review

Prepare extracted/OCR text, run cleanup analysis, open the cleaned text for review and require approval before full audiobook synthesis.

### 4. Voice and speech controls

Choose language and voice, preview samples in the matching language, adjust rate and volume, and approve Part 1 before producing the whole book.

### 5. Resumable audiobook synthesis

Synthesize one recoverable MP3 part at a time, track whole-book progress and current-part status, and resume interrupted work instead of starting over.

### 6. Diagnostics and release evidence

Keep logs, status, receipts, source/test updates and release artifacts visible enough to debug real failures instead of relying on unverifiable success claims.

## Why this exists

Most text-to-speech tools are acceptable for short snippets. Real books create different problems: broken OCR, long runtimes, provider stalls, partial failures, bad text cleanup, confusing progress and no safe recovery after interruption.

KR Book To Audio is built around those real-book problems. It favors explicit workflow states, recoverable parts, review checkpoints, diagnostics and visible progress over a one-button black box.

## Release artifacts

- Release notes: `docs/RELEASE_NOTES_ISTANBUL_RELEASE_3_0.md`
- Latest screenshot: `docs/images/kr_book_to_audio_3_0_ui_status_runtime_20260614.png`
- Portable Windows ZIP: `release_artifacts/KR_Book_To_Audio_Istanbul_Release_3_0_Portable_Windows_x64.zip`
- Portable ZIP SHA-256: `release_artifacts/KR_Book_To_Audio_Istanbul_Release_3_0_Portable_Windows_x64.zip.sha256.txt`
- Development chronology: `docs/dev-history/ISTANBUL_RELEASE_3_0_DEVELOPMENT_CHRONOLOGY.md`

## Iteration history

| Public release line | Focus |
|---|---|
| Istanbul Release 1.x | Early portable book-to-audio foundation, provider wiring and release packaging. |
| Istanbul Release 2.0 | More complete desktop workflow and public GitHub presentation. |
| Istanbul Release 2.4.x | GUI responsiveness, provider telemetry handling, TTS reliability and flat export behavior. |
| Istanbul Release 2.5.x | Governed local OCR foundation and offline OCR resource architecture. |
| Istanbul Release 3.0 | Consolidated local acceptance line with improved workflow presentation, progress/status visibility, diagnostic logs, source/test publication and portable Windows artifact. |

Internal engineering checkpoints were used during development. They are not public product names. The public-facing version for the current checkpoint is **Istanbul Release 3.0**.

## Development principles

- Real-book workflow over toy snippets.
- User-visible state over hidden background work.
- Recoverable parts over all-or-nothing synthesis.
- Explicit OCR and text-review gates over silent conversion.
- Portable local execution over fragile machine-specific installs.
- Diagnostics and receipts over unverifiable success claims.

## Current status

Istanbul Release 3.0 is a published public checkpoint with source, tests, screenshot, release notes and a portable Windows release artifact.

Historical release notes and earlier screenshots remain under `docs/` and `docs/images/`.
