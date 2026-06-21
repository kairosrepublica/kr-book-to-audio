# KR Book To Audio — Porto Release 3.3

Release note: **Kent Reis @ Porto, Portugal**.

Porto Release 3.3 is the text-engine refactor release. It addresses the failure mode where EPUB, PDF and MOBI-family books were flattened too early into plain text and then repaired by increasingly fragile heuristics.

![KR Book To Audio — Porto Release interface reference](https://raw.githubusercontent.com/kairosrepublica/kr-book-to-audio/main/docs/https://raw.githubusercontent.com/kairosrepublica/kr-book-to-audio/main/docs/images/kr_book_to_audio_porto_release_3_2_20260620.png)

## Main upgrade: DocumentBlock text engine

The extraction layer now emits semantic `DocumentBlock` records before prepare-text cleanup. Blocks include headings, paragraphs, list items, captions, page numbers and footers where the source format can support them. Prepare text can then operate on structure instead of guessing all structure from a lossy plain-text string.

## Source-specific behavior

- **EPUB**: parse spine XHTML and preserve block-level boundaries from headings, paragraphs, list items, block quotes and captions.
- **PDF native text**: extract page-level text, remove high-confidence URL / page-number footer noise before reflow, and preserve more heading/list boundaries.
- **DOCX**: preserve Word paragraph boundaries and basic heading styles.
- **TXT / Markdown**: keep the existing Prepare modes while routing through the same block engine.
- **MOBI / AZW / PRC**: prefer Calibre `ebook-convert` to convert the file to EPUB first. The legacy PalmDOC parser remains a fallback only for simple old files and now reports a clearer error when the file is outside that parser's safe envelope.

## Prepare modes remain

- **Auto smart cleanup** remains the default. Use it for most EPUB, PDF native-text, TXT, Markdown and DOCX inputs.
- **Minimal preserve layout** remains the manual trust mode for already-clean text.
- **Aggressive OCR cleanup** remains the destructive repair mode for noisy OCR/PDF extraction.

## Why this matters

Earlier 3.x cleanup logic could improve one source type while damaging another because extraction, heading detection, footer removal, paragraph reflow and chunking were mixed together. Porto 3.3 separates these layers enough that future debugging can identify whether a failure belongs to extraction, block classification, cleanup policy or TTS chunking.

## Public documentation link hygiene

Porto Release 3.3 also corrects the prior screenshot-link failure class: public Markdown now uses a verified `docs/images/...` repository path or an absolute raw GitHub image URL instead of the broken `images/...` path that produced a 404 on the previous Porto release page.

## Known limits

No public algorithm perfectly solves Chinese and English text preparation across TXT, EPUB, MOBI, native PDF and OCR PDF. Porto 3.3 uses mature source-specific extraction where feasible and keeps KR Book To Audio's own code focused on TTS-oriented normalization, reviewable text and part splitting.

MOBI/AZW reliability depends on Calibre for complex Kindle formats. Without Calibre, only simple legacy PalmDOC-compatible files can be attempted.
