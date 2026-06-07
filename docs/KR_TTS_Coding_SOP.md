# KR Book To Audio Operator SOP

## Scope

Use this workflow for continuous prose. Do not use it for books whose meaning depends on tables, formulas or figures unless information loss is acceptable.

## Source selection

Prefer born-digital EPUB, MOBI or DOCX sources. For scanned books, preserve the scan as visual ground truth and produce an OCR text layer first. Prefer predictable page noise over stochastic reflow corruption.

PDF diagnosis now checks representative extracted-text samples as well as font rows. When sampled prose is unusable, re-OCR the PDF or choose a better source.

## Environment

Install Python dependencies:

```bash
python -m pip install -e .
python -m pip install opencc  # only for Traditional-to-Simplified conversion
```

Install Poppler for PDF input and FFmpeg for audio validation and merge.

## Desktop workflow

```bash
kr-book-to-audio-gui
```

Then:

1. Prepare text.
2. Open and review `proofread.txt`.
3. Click **Approve proofread & rebuild** after proofread or dictionary changes.
4. Audition the selected voice.
5. Generate and listen to Part 1.
6. Click **Approve Part 1**.
7. Generate all parts.
8. Use **Retry failed** when a network interruption leaves recorded failures.
9. Merge only after generation completes without gaps.

The interface blocks conflicting background actions. Changing proofread text, dictionary content, voice or speaking rate invalidates the affected approval.

## Command-line workflow

```bash
kr-book-to-audio diagnose book.epub
kr-book-to-audio prepare book.epub --dictionary pronunciation.json
kr-book-to-audio approve-proofread PATH_TO_JOB --dictionary pronunciation.json
kr-book-to-audio audition --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio preview PATH_TO_JOB --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio approve-preview PATH_TO_JOB --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio tts PATH_TO_JOB --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio retry-failed PATH_TO_JOB --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio merge PATH_TO_JOB
```

When a pronunciation dictionary is used, pass it again to `approve-proofread` after editing it. The manifest stores the approved dictionary path for subsequent freshness checks.

## Recovery

Re-run `retry-failed` against the same job directory after a network interruption. Valid manifest-matched MP3 files are reused. Invalid, truncated or stale files are regenerated. Inspect `_work/run.log` for JSON-line evidence of retries and failures.

If a process terminates abnormally and leaves `_work/.operation.lock`, confirm that no synthesis or merge operation is running before deleting that stale lock file.

## AZW3 boundary

Convert AZW3 to EPUB or MOBI before import. Native AZW3 parsing is intentionally blocked until a verified Kindle Format 8 fixture exists.
