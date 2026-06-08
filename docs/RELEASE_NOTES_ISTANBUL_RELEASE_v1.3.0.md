# Istanbul Release v1.3.0

Durable resume and Recent jobs release.

## Added

- Stable application-level recent-job index.
- Per-job PID, heartbeat, current-Part and resume checkpoints.
- Recent jobs desktop panel with one-click interrupted-task continuation.
- Conservative stale-lock recovery after dead-process confirmation.
- Residual partial MP3 cleanup and trusted sidecar-bound orphan MP3 adoption.
- Automatic Windows keep-awake during OCR and TTS work.
- OCR page-checkpoint capability declarations and OCR execution snapshots.

## Boundary

The global history file is rebuildable navigation state. Per-job manifests remain authoritative. Malformed locks are never deleted automatically. OCR providers declare future page-level resume capability without claiming that all OCR engines already support it.
