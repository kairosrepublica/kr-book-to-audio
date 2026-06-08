# Istanbul Release v1.3.2

Resume speech-control rehydration and recent-attempt deduplication hotfix.

## Fixed

- Persist task-bound TTS controls (`provider_id`, voice, rate, pitch and volume) in each job manifest and MP3 sidecar.
- Restore task-bound speech controls before one-click resume.
- Safely recover legacy default speech controls by matching the existing audio signature against cached voice candidates.
- Stop with a clear operator message instead of leaking a low-level preview-gate RuntimeError when legacy custom controls cannot be reconstructed safely.
- Resume directly from the first incomplete Part instead of re-scanning completed Parts.
- Collapse older resumable attempts for the same source book from the default Recent-jobs panel while retaining them in the rebuildable history index.

## Safety boundary

Existing MP3 files remain preserved when legacy custom speech controls cannot be proven. The operator must regenerate and approve Part 1 before continuing with a changed configuration.
