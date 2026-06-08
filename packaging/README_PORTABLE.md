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
