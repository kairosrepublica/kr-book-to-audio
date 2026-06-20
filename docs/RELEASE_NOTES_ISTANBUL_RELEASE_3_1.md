# KR Book To Audio — Istanbul Release 3.1

Istanbul Release 3.1 is a source-code update focused on safer text preparation control for real ebook inputs.

## What changed

- Added a compact **Prepare mode** selector in the existing Text process panel.
- Removed the separate **Prepare text (minimal)** button to avoid competing prepare entry points.
- Added a triangle help marker (`▸`) beside every prepare mode; hover over the triangle to see when to use that mode.
- Preserved the default **Auto smart cleanup** behavior for most TXT, Markdown and DOCX sources.
- Kept **Minimal preserve layout** as an explicit Owner-selected mode for already-cleaned TXT files.
- Kept **Aggressive OCR cleanup** for noisy PDF/OCR/extracted text.
- Kept article-aware splitting on by default so parts prefer article endings before paragraph/sentence fallback.
- Retained the pronunciation dictionary compatibility fix from the prior source patch.

## Prepare mode usage

| Mode | Use when |
|---|---|
| Auto smart cleanup | Most normal TXT, Markdown and DOCX books. Keeps high-confidence title/subtitle/article breaks while cleaning broken line wraps and extra spaces. |
| Minimal preserve layout | Only when the text has already been manually or AI-cleaned. This preserves layout as much as possible and can pass through messy ebook line breaks. |
| Aggressive OCR cleanup | PDF/OCR/extracted text with many bad line breaks or spacing defects. This may collapse intentional title spacing. |

## Validation note

This source checkpoint was validated at source/test level. It is not a rebuilt Windows executable or installer package.
