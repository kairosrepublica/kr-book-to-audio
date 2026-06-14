# KR Book To Audio — Istanbul Release 3.0 Development Chronology

This document summarizes the public-facing development story behind Istanbul Release 3.0.

## Public release naming

The public release name is:

```text
Istanbul Release 3.0
```

Internal acceptance labels and patch labels were used during engineering to isolate fixes and validation. They are not public product names.

## Major development arc

### 1. Desktop book-to-audio foundation

Early Istanbul releases established the Windows GUI, source selection, provider registry, part-based audio output, portable packaging and public repository presentation.

### 2. Provider reliability and GUI responsiveness

The 2.4 line focused on keeping the UI responsive during long provider operations, making telemetry visible without freezing the GUI, and preserving durable export behavior.

### 3. Local OCR foundation

The 2.5 line introduced a governed local OCR foundation for image-only PDFs, local resource management, fallback profiles and safer recovery patterns.

### 4. 3.0 acceptance line

The 3.0 acceptance line concentrated on practical user-facing workflow closure: source analysis, OCR visibility, text preparation, approval gates, preview-first audio generation, resumable full synthesis and clearer status/progress presentation.

### 5. Final public presentation cleanup

The final publication pass corrected the public repository surface: README, changelog, screenshot, release notes, sanitized manifest and GitHub Release naming.

## Commit-history note

Some internal engineering checkpoints were consolidated before publication. This chronology records the development sequence without rewriting Git history or inventing per-checkpoint commits after the fact.
