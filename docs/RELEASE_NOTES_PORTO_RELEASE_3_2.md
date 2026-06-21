# KR Book To Audio — Porto Release 3.2

Released: 2026-06-20
Release note: Kent Reis @ Porto, Portugal

Porto Release 3.2 is the text-processing stabilization release for KR Book To Audio. It promotes the 3.1 prepare-mode work to the public release line, fixes the remaining window-title version mismatch, and documents the text cleanup modes for real ebook workflows.

![KR Book To Audio — Porto Release 3.2](https://raw.githubusercontent.com/kairosrepublica/kr-book-to-audio/main/docs/https://raw.githubusercontent.com/kairosrepublica/kr-book-to-audio/main/docs/images/kr_book_to_audio_porto_release_3_2_20260620.png)

## Main upgrade: text processing

The main upgrade is the new **Prepare mode** control in the Text process area. It gives the Owner explicit control over how much cleanup the application should perform before text review and TTS.

### Auto smart cleanup

Default mode. Use it for most TXT, Markdown and DOCX books where the source is already mostly readable but still may contain minor line-break and spacing defects.

Auto smart cleanup is structure-aware: it preserves likely article titles, headings and subheadings, while still reflowing low-confidence broken lines and obvious spacing noise. It is the recommended first pass when the source has meaningful paragraphs and visible section structure.

### Minimal preserve layout

Manual-preservation mode. Use it only when the source TXT has already been manually cleaned or AI-cleaned and the layout should be trusted.

Minimal preserve layout performs only necessary safety normalization and avoids aggressive reflow. It is the right choice for final hand-edited text where the Owner wants the program to respect existing blank lines and paragraph boundaries.

### Aggressive OCR cleanup

Strong cleanup mode. Use it for PDF/OCR/extracted text with many bad line breaks, broken paragraphs, page headers, page footers, page numbers or spacing defects.

Aggressive OCR cleanup assumes the source layout is not trustworthy. It may improve heavily damaged text, but it is more likely than Auto to compress weak headings or remove spacing the Owner wanted to keep. It should not be the default for carefully prepared TXT files.

## Part splitting behavior

Porto Release 3.2 keeps article-aware part splitting as the default strategy. The program prioritizes splitting at article boundaries rather than cutting inside an article merely because a character threshold was reached. If a single article exceeds the TTS size ceiling, the fallback order is paragraph, sentence, and only then hard length splitting.

## Pronunciation dictionary compatibility

The release retains pronunciation dictionary compatibility work from the 3.1 line. The app accepts the existing simple `replacements` format and can safely import direct `source` to `spoken` entries from richer pronunciation lexicon files. IPA, pinyin and heteronym metadata are not blindly converted into text substitutions because the current TTS path is plain-text based.

## UI update

The Text process panel now shows three Prepare mode radio options with a small triangle hover marker beside each option. The hover marker explains when the mode should be used. The main action remains a single `Prepare text` button, avoiding multiple competing prepare buttons.

## Version correction

The desktop window title is corrected to `KR Book To Audio 3.2`, including the window-state restore path that previously reset the visible title to an older version string.

## Validation status

Source-level validation in the AI sandbox covered syntax, targeted text-processing tests, prepare-mode UI contract tests, manifest integrity tests and the Porto 3.2 release contract. Windows packaging was previously verified on the Owner machine for the 3.1 line; 3.2 source is ready for the same portable packaging path.
