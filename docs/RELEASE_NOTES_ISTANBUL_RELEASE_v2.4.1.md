# KR Book To Audio — Istanbul Release v2.4.1

## Scope

This Release is a narrow GUI responsiveness hotfix for Istanbul Release v2.4.0. It preserves the existing Edge Online resilience, Kokoro Local fallback, governed resource archive and flat Export contract.

## GUI event backpressure

- Replace per-chunk GUI queue growth with a fixed-memory latest-only Provider telemetry mailbox.
- Keep ordered control transitions in a separate queue.
- Bound every GUI drain cycle by event count and elapsed milliseconds.
- Yield back to the Tkinter and Windows event loops after every cycle.
- Reject stale telemetry after validating, done or failed terminal transitions.

## Thread confinement

- Snapshot Provider, Voice, Rate, Pitch, Volume and Keep-awake values on the GUI thread before starting workers.
- Prevent background workers from reading Tkinter variables.
- Dispatch Preview playback from the GUI success callback after checkpoint completion.

## Kokoro Local resilience

- Emit local-worker heartbeat telemetry while the subprocess is running.
- Enforce a bounded local-worker deadline.
- Terminate and then kill a hung worker safely.
- Keep existing completed checkpoints intact.

## Windows target-runtime gate

Portable publication now executes a packaged Windows GUI responsiveness probe that injects 100,000 telemetry updates, verifies Tk heartbeat continuity, verifies bounded close handling and confirms diagnostics controls remain available during stress.

## Frozen subsystems

SQLite durable state, Resume semantics, OCR, text chunking, flat Export, governed Local TTS resource layout and quiet-export receipt reuse remain unchanged.
