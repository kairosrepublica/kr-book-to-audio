# KR Book To Audio

KR Book To Audio is a local, resumable book-to-audiobook pipeline with additional safeguards for Chinese-language books.

It converts text-layer PDF, EPUB, MOBI or PalmDOC-compatible AZW or PRC, DOCX, TXT and Markdown sources into independently recoverable MP3 parts and an optional merged MP3 audiobook.

## Why this project exists

Chinese audiobook generation fails in ways that generic text-to-speech wrappers often miss. Optical character recognition and PDF extraction may inject invisible layout damage into Chinese prose: glyph-gap spaces, recurring page headers, page numbers, mid-sentence page breaks and repeated junk. These defects sound much worse than they look because a speech engine treats them as segmentation cues.

The pipeline treats cleanup, human proofreading, listening approval and audio integrity as separate gates. A long synthesis run cannot start merely because a button was clicked.

## Istanbul Release v1.1.0

The Production Run Safety release adds:

- enforced proofreading approval bound to the current `proofread.txt` SHA-256 hash;
- enforced Part-1 listening approval bound to the current text, voice and speaking rate;
- automatic blocking when the pronunciation dictionary changes after rebuilding;
- automatic invalidation of stale MP3 files when text or speech controls change;
- one-job-at-a-time locking across desktop and command-line processes;
- persisted failed-part records and targeted retry;
- per-part desktop status and overall progress;
- strict merge validation against manifest hashes, not file existence alone;
- durable JSON-line logs for synthesis retries and merge outcomes;
- PDF diagnosis that samples real extracted text rather than trusting font rows alone.

The founding v1.0.0 capabilities remain:

- one shared Python core used by both command-line and Tkinter desktop interfaces;
- Chinese-character whitespace normalization while preserving ASCII spaces such as `S&P 500`;
- conservative page-header removal and sentence-aware reflow;
- optional OpenCC Traditional-to-Simplified conversion;
- user-editable pronunciation replacement dictionary;
- automatic `chinese-optimized` and `general-prose` cleaning modes;
- safe splitting of pathological long paragraphs;
- numeric part ordering beyond 99 parts;
- atomic `.partial.mp3` generation with `ffprobe` validation;
- local non-cloud working storage by default and a separate configurable export folder;
- explicit rejection of unverified AZW3 or Kindle Format 8 parsing.

## Installation

Requirements:

- Python 3.11 or later;
- FFmpeg and `ffprobe` for audio validation and merge;
- Poppler commands (`pdfinfo`, `pdffonts`, `pdftotext`) for PDF input;
- `edge-tts` for the default online speech backend;
- `opencc` only when Traditional-to-Simplified conversion is needed.

Install the Python package in editable mode:

```bash
python -m pip install -e .
```

Optional conversion support:

```bash
python -m pip install opencc
```

## Desktop workflow

Launch:

```bash
kr-book-to-audio-gui
```

Recommended workflow:

1. Select a book and prepare text.
2. Open `proofread.txt` and correct visible extraction errors.
3. Click **Approve proofread & rebuild**. This binds the current text and pronunciation dictionary to the job manifest.
4. Audition the selected voice.
5. Generate and listen to Part 1.
6. Click **Approve Part 1**.
7. Generate the remaining MP3 parts.
8. Use **Retry failed** when a network interruption leaves recorded failures.
9. Merge only after every manifest-declared MP3 passes validation.

Changing `proofread.txt`, the pronunciation dictionary, the selected voice or the speaking rate invalidates the relevant approval. The interface refuses to continue until the affected gate is repeated.

Work files default to a local non-cloud directory. Finished audio exports go to a separate configurable folder.

## Command-line workflow

```bash
kr-book-to-audio diagnose book.epub
kr-book-to-audio prepare book.epub --t2s --dictionary pronunciation.json
kr-book-to-audio approve-proofread PATH_TO_JOB --dictionary pronunciation.json
kr-book-to-audio audition --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio preview PATH_TO_JOB --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio approve-preview PATH_TO_JOB --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio tts PATH_TO_JOB --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio retry-failed PATH_TO_JOB --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio merge PATH_TO_JOB
```

A pronunciation dictionary is a JSON file:

```json
{
  "replacements": [
    {"find": "重庆", "replace": "重 庆", "enabled": true},
    {"find": "单于", "replace": "蝉 于", "enabled": true}
  ]
}
```

The replacement text should be chosen by listening tests. Every replacement count is written into `pronunciation_preview.json` before synthesis.

## Input boundary

Supported directly:

- text-layer PDF and OCR-produced PDF;
- EPUB;
- MOBI and PalmDOC-compatible AZW or PRC;
- DOCX;
- TXT and Markdown.

Not supported directly:

- image-only scanned PDF before OCR;
- AZW3 or Kindle Format 8;
- tables, formulas or figure-dependent material where visual meaning cannot survive audio conversion.

## Roadmap

Planned extensions include integrated OCR, paid Azure Speech support with richer pronunciation controls, semantic chapter extraction, chapter-aware M4B export, mixed Chinese-English routing and optional offline backends.

## License

No open-source license has been granted yet. Copyright remains with the project owner unless a later release states otherwise.
