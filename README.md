# KR Book To Audio

KR Book To Audio is a local, resumable book-to-audiobook pipeline with multilingual text processing, Chinese-language safeguards, an OCR advisor and provider registries for future engine expansion.

It converts text-layer PDF, EPUB, MOBI or PalmDOC-compatible AZW or PRC, DOCX, TXT and Markdown sources into independently recoverable MP3 parts and an optional merged MP3 audiobook.

## Istanbul Release v1.2.0

This release adds an OCR Advisor Foundation and a clearer multilingual desktop workflow:

- automatic OCR applicability and necessity analysis;
- local OCR capability discovery for PaddleOCR, Tesseract, OCRmyPDF, language packs and advisory GPU availability;
- automatic local OCR recommendation instead of forcing the operator to understand engine details;
- sample-page OCR preview before full-book OCR;
- provider registries shared by OCR and text-to-speech paths;
- reserved but disabled API adapter slots for OpenAI Vision, Claude Vision, Azure Speech, OpenAI TTS and custom HTTP providers;
- no cloud upload path enabled in this release;
- readonly TTS-engine selector with `Microsoft Edge Online TTS · edge-tts` as the only enabled provider;
- cached, refreshable voice dropdown with language-profile filtering and manual **Show all voices** override;
- processing-profile selector: auto, Chinese, English, mixed Chinese-English and general prose;
- automatic cleanup analysis with high-confidence action buttons and review-required preservation;
- estimated Part-1 and current-part progress, plus exact overall completed-part progress.

The v1.1.1 Windows PDF hotfix remains active: Poppler output is decoded bytes-first, and missing PDF metadata falls back safely to the source filename.

## Provider model

Three concepts are separated:

```text
OCR provider
Text processing profile
TTS provider and voice
```

The current enabled TTS provider is:

```text
edge-tts
```

The OCR advisor can discover and recommend local providers:

```text
paddleocr-ppocrv5
tesseract-local
ocrmypdf-tesseract
```

Reserved API adapter slots are disabled by default. They exist so future integrations can be added without rewriting the pipeline. Credentials must come from environment variables or a future Owner-local secret store. They are never stored in job manifests, logs or public GitHub files.

## Installation

Requirements:

- Python 3.11 or later;
- FFmpeg and `ffprobe` for audio validation and merge;
- Poppler commands (`pdfinfo`, `pdffonts`, `pdftotext`, `pdftoppm`) for PDF input and OCR rendering;
- `edge-tts` for the current online speech provider.

Install:

```bash
python -m pip install -e .
```

Optional local OCR engines are discovered automatically when installed:

```text
PaddleOCR
Tesseract
OCRmyPDF
```

The application does not auto-install large OCR dependencies.

## Desktop workflow

Launch:

```bash
kr-book-to-audio-gui
```

Recommended workflow:

1. Select a source book.
2. Run **Analyze source** in the OCR section.
3. When OCR is required, preview sample OCR and run the recommended local OCR engine.
4. Select a processing profile or keep **Auto detect · recommended**.
5. Prepare text.
6. Review automatic cleanup recommendations. Apply only the recommended cleanup actions you accept.
7. Open and review the cleaned text.
8. Click **Approve reviewed text & rebuild**.
9. Refresh the voice list when needed, audition the selected voice and generate Part 1.
10. Approve Part 1 after listening.
11. Generate all parts, retry recorded failures when needed and merge only after validation completes.

Changing the reviewed text, pronunciation dictionary, selected voice, speaking controls or TTS provider invalidates the relevant approval.

## OCR boundary

The application prefers native text and avoids OCR when a reliable text layer already exists.

For scanned PDF sources, the advisor:

```text
analyzes representative pages
detects language characteristics
discovers local capabilities
recommends a local OCR provider
supports sample preview before full OCR
```

Cloud OCR adapters are reserved but disabled. No page is uploaded to a remote API in v1.2.0.

## Optional cleanup boundary

Cleanup analysis reports:

```text
not-needed
recommended
review-required
```

Only high-confidence candidates can be removed by action buttons. Ambiguous repeated text remains preserved for human review.

## Command-line examples

```bash
kr-book-to-audio providers
kr-book-to-audio ocr-analyze scan.pdf
kr-book-to-audio ocr-preview scan.pdf
kr-book-to-audio ocr-run scan.pdf --output-dir OCR_OUTPUT
kr-book-to-audio prepare book.epub --profile auto --dictionary pronunciation.json
kr-book-to-audio cleanup PATH_TO_JOB metadata-date-time-tags
kr-book-to-audio cleanup PATH_TO_JOB repeated-headers-and-junk
kr-book-to-audio approve-proofread PATH_TO_JOB --dictionary pronunciation.json
kr-book-to-audio audition --engine edge-tts --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio preview PATH_TO_JOB --engine edge-tts --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio approve-preview PATH_TO_JOB --engine edge-tts --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio tts PATH_TO_JOB --engine edge-tts --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio retry-failed PATH_TO_JOB --engine edge-tts --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio merge PATH_TO_JOB
```

## Input boundary

Supported directly:

- text-layer PDF and OCR-produced PDF;
- EPUB;
- MOBI and PalmDOC-compatible AZW or PRC;
- DOCX;
- TXT and Markdown.

Not supported directly:

- AZW3 or Kindle Format 8;
- tables, formulas or figure-dependent material where visual meaning cannot survive audio conversion.

## License

No open-source license has been granted yet. Copyright remains with the project owner unless a later release states otherwise.
