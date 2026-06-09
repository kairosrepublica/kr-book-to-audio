# KR Book To Audio — Portable Windows x64

Launch by double-clicking:

```text
KRBookToAudio.exe
```

The portable executable uses the Windows GUI subsystem and does not open a PowerShell or command-line window.

Runtime state remains outside the portable folder:

```text
%LOCALAPPDATA%\KRBookToAudio
```

External tools remain discoverable dependencies rather than silently bundled binaries:

```text
FFmpeg / ffprobe: MP3 validation and merge
Poppler: PDF extraction and OCR rendering
PaddleOCR, Tesseract, OCRmyPDF: optional local OCR providers
```
## Export verification

After the final validated Part, the app materializes verified deliverables beneath the configured Export root. Legacy completed jobs with empty external folders are repaired automatically when loaded or opened. The repair reuses trusted internal checkpoints; it does not regenerate speech.

## Silent child-process policy

Console-style external tools launch through the governed hidden-window adapter on Windows. Explorer, cleaned-text opening and preview playback remain visible user actions.

## v2.3.0 durable-state note

Each task owns a local SQLite state database under `_work\state`. The portable application migrates legacy JSON-only jobs automatically and preserves readable snapshots for debugging.

## v2.3.1 desktop-shell note

The normal desktop starts at 1200 px wide, enforces a 1150 px minimum width and starts at exactly 1900 px high on displays taller than 1900 px. The Footer remains fixed while the internal workflow viewport supports mouse-wheel and touchpad scrolling.
## v2.3.2 precision desktop-shell note

The normal desktop starts at 1200 px wide, enforces a 1150 px minimum width and starts at exactly 1870 px high on displays taller than 1870 px. When the actual window height is at least 1870 px, the outer workflow scrollbar is hidden and ordinary outer mouse-wheel or touchpad routing is disabled. Below 1870 px, the scrollbar and ordinary outer scrolling return. Native scrolling inside Run log, Recent jobs, Part status, Listbox and Combobox controls remains preserved.


## v2.3.3 Windows physical-pixel fixed-shell note

On Windows, the 1870 px fixed-shell boundary is evaluated from Desktop Window Manager visible top-level frame bounds in physical screen pixels. Tk toolkit height is retained only as a non-Windows or unavailable-native-API fallback. In fixed mode the outer scrollbar is hidden, the outer Canvas returns to the top and ordinary outer wheel propagation is consumed. Native scrolling inside Run log, Recent jobs, Part status, Listbox and Combobox controls remains preserved.

Portable publication requires a real Windows outer-scroll interaction probe in addition to source tests and the existing hidden smoke test.
