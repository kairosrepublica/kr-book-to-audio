# KR Book To Audio

KR Book To Audio is a local, resumable general-prose book-to-audiobook pipeline with additional Chinese-language safeguards. It converts extractable PDF, EPUB, MOBI/PalmDOC-compatible AZW or PRC, DOCX, TXT and Markdown sources into independently recoverable MP3 parts and an optional merged MP3 audiobook.

## Why this project exists

Chinese audiobook generation fails in ways that generic text-to-speech wrappers often miss. Optical character recognition and PDF extraction may inject invisible layout damage into Chinese prose: glyph-gap spaces, recurring page headers, page numbers, mid-sentence page breaks and repeated junk. These defects sound much worse than they look because a speech engine treats them as segmentation cues.

This release treats source cleanup, human proofread approval and audio integrity as first-class stages.

## Istanbul Release v1.0.0

The founding release provides:

- one shared Python pipeline core used by both the command-line interface and the Tkinter desktop interface;
- Chinese-character whitespace normalization while preserving ordinary ASCII spaces such as `S&P 500`;
- conservative page-header removal and sentence-aware reflow;
- optional OpenCC Traditional-to-Simplified conversion;
- a user-editable pronunciation replacement dictionary for names, polyphonic characters and recurring terms;
- automatic `chinese-optimized` and `general-prose` cleaning modes;
- a proofread file that can be opened and corrected before speech synthesis;
- manifest-driven resumability with source, text, dictionary, chunk and audio signatures;
- safe splitting of pathological long paragraphs;
- numeric part ordering beyond 99 parts;
- atomic `.partial` audio generation with `ffprobe` validation;
- refusal to merge incomplete or invalid audio sequences;
- local non-cloud working storage by default and a separate configurable export folder;
- explicit rejection of unverified AZW3 / Kindle Format 8 parsing.

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
2. Open the generated `proofread.txt` and correct visible extraction errors.
3. Rebuild parts after proofreading or dictionary edits.
4. Audition the selected voice.
5. Generate and listen to Part 1.
6. Generate the remaining MP3 parts only after Part 1 is acceptable.
7. Merge the MP3 files only after all manifest-declared parts pass validation.

Work files default to a local non-cloud directory. Finished audio exports go to a separate configurable folder.

## Command-line workflow

```bash
kr-book-to-audio diagnose book.epub
kr-book-to-audio prepare book.epub --t2s --dictionary pronunciation.json
kr-book-to-audio audition --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio rebuild PATH_TO_JOB --dictionary pronunciation.json
kr-book-to-audio preview PATH_TO_JOB --voice zh-CN-YunyangNeural --rate +0%
kr-book-to-audio tts PATH_TO_JOB --voice zh-CN-YunyangNeural --rate +0%
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

The replacement text should be chosen by listening tests. The dictionary is deliberately transparent: every replacement count is written into `pronunciation_preview.json` before synthesis.

## Input boundary

Supported directly:

- text-layer PDF and OCR-produced PDF;
- EPUB;
- MOBI and PalmDOC-compatible AZW or PRC;
- DOCX;
- TXT and Markdown.

Not supported directly in this release:

- image-only scanned PDF before OCR;
- AZW3 / Kindle Format 8;
- tables, formulas or figure-dependent material where visual meaning cannot survive audio conversion.

## Roadmap

Planned extensions include integrated OCR, paid Azure Speech support with richer pronunciation controls, semantic chapter extraction, chapter-aware M4B export, mixed Chinese-English routing and optional offline backends.

## License

No open-source license has been granted yet. Copyright remains with the project owner unless a later release states otherwise.
