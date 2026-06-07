# Istanbul Release v1.1.0

The Production Run Safety release turns the v1.0.0 foundation into a stricter long-book workflow.

Highlights:

- proofreading approval is enforced and bound to the current proofread-text hash;
- Part-1 listening approval is enforced and bound to the current text, voice and speaking rate;
- dictionary edits block synthesis until text parts are rebuilt and reapproved;
- stale MP3 files are invalidated when text or speech controls change;
- concurrent operations against the same job are rejected;
- failed parts are persisted and can be retried directly;
- the desktop interface displays per-part state and overall progress;
- synthesis retries and merge outcomes are written to a durable JSON-line log;
- merge verifies manifest completion records, text hashes, speech signatures and MP3 hashes;
- PDF diagnosis samples extracted prose rather than trusting font rows alone.

Deferred extensions remain integrated OCR, paid speech backends, semantic chapter extraction, M4B export and offline synthesis.
