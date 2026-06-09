# Istanbul Release v2.3.0

## Durable State Engine, Responsive GUI and Quiet Export

This release replaces the single JSON job-state authority with a per-job SQLite transaction engine. It preserves readable JSON snapshots, migrates legacy jobs without deleting evidence, rejects stale revisions and prevents concurrent writers through a job lease.

The GUI adapts to large and small displays. The Owner 2160p display receives a 1900 px initial height; smaller screens receive a clamped, vertically scrollable layout.

Export finalization reuses verified MP3 receipts, reducing redundant ffprobe launches without weakening integrity checks. OCR execution is disabled when a native text layer is already sufficient.

The real Istanbul Release v2.1.0 Owner-machine screenshot is included as historical interface evidence.
The state engine also closes partially initialized SQLite handles when setup or corruption checks fail. This prevents Windows file-handle leaks from blocking quarantine, cleanup and safe recovery.
