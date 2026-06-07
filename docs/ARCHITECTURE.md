# Architecture

## Design rule

The command-line interface and desktop interface are thin adapters around one shared pipeline core. Text processing, extraction, manifest rules, approval gates and audio integrity checks live in importable modules and are tested independently.

## Data flow

```text
source book
  diagnose
  extract
  clean
  optional OpenCC conversion
  proofread.txt
  explicit proofreading approval
  pronunciation dictionary freshness check
  tts_text.txt
  sentence-aware chunking
  parts_text/part-0001.txt ...
  Part-1 synthesis
  explicit listening approval
  edge-tts atomic .partial.mp3 generation
  ffprobe validation
  parts_audio/part-0001.mp3 ...
  failed-part persistence and targeted retry
  strict manifest-bound merge
  export/<title>.mp3
```

## Storage boundary

The default working directory is local and non-cloud-synced. It contains resumable intermediate artifacts. The export directory is separate and user-configurable. Finished files may be copied into a synchronized library without exposing partial synthesis artifacts to sync locking.

## Job manifest

`_work/job_manifest.json` records:

- source filename and SHA-256;
- title and preparation options;
- cleaned, proofread, speech-text and dictionary SHA-256 values;
- expected numbered text parts and hashes;
- proofread approval bound to the current proofread hash;
- Part-1 approval bound to the current text and speech-control signature;
- audio signature derived from voice and speaking controls;
- validated completed MP3 metadata and failed-part records;
- merged-output metadata.

Text, dictionary or chunk changes invalidate stale MP3 files. Voice or speaking-control changes invalidate prior audio state. Full synthesis and merge remain blocked until the required approvals match the current state.

## Concurrency boundary

Each mutating pipeline operation acquires `_work/.operation.lock` using exclusive filesystem creation. Concurrent GUI or command-line operations against the same job are rejected. If a process terminates abnormally, remove a stale lock only after confirming that no KR Book To Audio operation is still running.

## PDF diagnosis

PDF diagnosis requires both detected font rows and a usable extracted-text sample from representative pages. A PDF that exposes fonts but yields no readable sampled prose is conservatively rejected for re-OCR or source replacement.

## Safety boundaries

The merger trusts only the manifest-declared numeric sequence and completion records. It refuses missing, tiny, stale, modified or `ffprobe`-invalid MP3 files. AZW3 is rejected rather than guessed because Kindle Format 8 parsing has not yet passed a real compatibility fixture.
