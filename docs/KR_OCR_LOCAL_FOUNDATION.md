# KR Book To Audio — Local OCR Foundation

## Owner-private reusable-resource archive

```text
%USERPROFILE%\OneDrive\Documents\KRG\KRG Code\_Resource\KR_OCR_Offline_Resources
```

This is the Owner-private authority for reusable OCR downloads and immutable archive bundles. It is append-only during ordinary setup and repair.

```text
KR_OCR_Offline_Resources\
├─ downloads\
├─ bundles\
│  └─ <bundle_id>\
├─ active\
│  └─ ACTIVE_BUNDLE.json
├─ reports\
│  └─ MANUAL_CLEANUP_CANDIDATES_PRIVATE.json
└─ manifests and receipts inside each immutable bundle
```

Existing archive bundles are not deleted, moved or replaced automatically. A matching verified resource is reused read-only. A changed resource is written into a new bundle.

## Versioned runtime deployments

```text
C:\dev\KR_OCR_Local
```

The local runtime root contains versioned deployments and one small active-deployment pointer.

```text
C:\dev\KR_OCR_Local\
├─ deployments\
│  └─ <bundle_id>\
├─ active\
│  └─ ACTIVE_DEPLOYMENT.json
└─ reports\
```

Each setup attempt writes a new candidate deployment. It does not delete, move or replace an existing deployment. A candidate becomes active only after its required resources and target-runtime probes pass.

## Activation contract

Activation is pointer-only:

```text
C:\dev\KR_OCR_Local\active\ACTIVE_DEPLOYMENT.json
```

The pointer identifies the validated runtime deployment and matching immutable archive bundle. If candidate validation fails, the prior active pointer remains unchanged and the failed candidate remains inactive.

## Cleanup contract

Normal setup and repair do not automatically clean historical Owner-local folders. The program may write:

```text
MANUAL_CLEANUP_CANDIDATES_PRIVATE.json
```

This report lists inactive deployments and bundles for later Owner review. Deletion is outside ordinary product publication and requires a separate Owner-approved cleanup action.

## Operational OCR profiles

```text
PaddleOCR PP-OCRv5 server accuracy
PaddleOCR PP-OCRv5 mobile fallback
Tesseract local OCR fast fallback
Tesseract local OCR best accuracy
```

## Policy

```text
archive first
write new immutable bundle second
write new versioned deployment third
validate candidate independently
activate through one small pointer only after validation
normal OCR execution offline-only
no global Python mutation
no PATH mutation
no Registry mutation
no first-use model download
no automatic deletion or replacement of Owner-local OCR directories
```

## Integrity and repair contract

```text
verify archived resources against SHA-256 receipts before read-only reuse
preserve persistent downloads for interrupted large transfers
bootstrap an isolated runtime through an external system Python interpreter when required
bind PaddleOCR server and mobile model names explicitly to matching local model directories
record independent failures and continue every dependency-valid path
write one consolidated report when blockers remain
```
