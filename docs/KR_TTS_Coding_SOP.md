# KR Book To Audio Operator SOP

## Scope

Use this workflow for continuous prose. Do not use it for books whose meaning depends on tables, formulas or figures unless information loss is acceptable.

## Source selection

Prefer born-digital EPUB, MOBI or DOCX sources. For scanned books, preserve the scan as visual ground truth and produce an OCR text layer first. Prefer predictable page noise over stochastic reflow corruption.

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
3. Rebuild parts after any proofread or dictionary change.
4. Audition the selected voice.
5. Preview Part 1.
6. Generate all parts only after the preview sounds correct.
7. Merge only after generation completes without gaps.

## Command-line workflow

```bash
kr-book-to-audio diagnose book.epub
kr-book-to-audio prepare book.epub --dictionary pronunciation.json
kr-book-to-audio rebuild PATH_TO_JOB --dictionary pronunciation.json
kr-book-to-audio audition --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio preview PATH_TO_JOB
kr-book-to-audio tts PATH_TO_JOB
kr-book-to-audio merge PATH_TO_JOB
```

## Recovery

Re-run `tts` against the same job directory after a network interruption. Valid manifest-matched MP3 files are reused. Invalid, truncated or stale files are regenerated.

## AZW3 boundary

Convert AZW3 to EPUB or MOBI before import. Native AZW3 parsing is intentionally blocked until a verified Kindle Format 8 fixture exists.
