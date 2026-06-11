# KR Book To Audio — Istanbul Release v2.5.0

## Scope

This Release adds a governed local OCR foundation for image-only PDFs and removes the redundant confirmation dialog before `8. Synthesize all`.

## Local OCR

Operational local OCR profiles:

```text
PaddleOCR PP-OCRv5 server accuracy
PaddleOCR PP-OCRv5 mobile fallback
Tesseract local OCR fast fallback
Tesseract local OCR best accuracy
```

## Append-only local-resource architecture

Reusable OCR downloads are retained under the Owner-private `_Resource` tree. New formal archive resources are written into immutable versioned bundles. Runtime candidates are written into new versioned deployments under `C:\dev\KR_OCR_Local\deployments`.

Ordinary OCR setup does not delete, replace, move or quarantine historical Owner-local OCR directories. A verified candidate becomes active only through a small `ACTIVE_DEPLOYMENT.json` pointer update after required validation passes. Historical cleanup is reported for later Owner review and is not performed automatically.

Normal OCR execution is offline-only. PaddleOCR server and mobile profiles bind their matching model names and local model directories explicitly.

## OCR workflow

```text
Analyze source
Install / repair local OCR foundation when required
Preview OCR sample
Run recommended OCR
Resume from page-level checkpoints after interruption
Prepare text from the selected OCR output
```

## Audio workflow simplification

Clicking `8. Synthesize all` starts synthesis immediately. Busy protection, checkpoints, Retry and Resume remain unchanged.

## Failure handling

OCR setup records independent failures, continues every dependency-valid path and writes a consolidated private report when blockers remain. Failed candidates remain inactive. Existing verified deployments remain untouched.

## Preserved behavior

```text
Edge Online TTS
Kokoro Local TTS
SQLite durable state
Resume semantics
GUI backpressure protection
flat Export contract
diagnostics
```
