# Architecture

## Design rule

The command-line interface and desktop interface are thin adapters around one shared pipeline core. Text processing, extraction, manifest rules and audio integrity checks live in importable modules and are tested independently.

## Data flow

```text
source book
  diagnose
  extract
  clean
  optional OpenCC conversion
  proofread.txt human gate
  pronunciation replacement preview
  tts_text.txt
  sentence-aware chunking
  parts_text/part-0001.txt ...
  edge-tts atomic .partial generation
  ffprobe validation
  parts_audio/part-0001.mp3 ...
  strict complete-sequence merge
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
- audio signature derived from voice and speaking controls;
- validated completed MP3 metadata.

A change in rendered text or chunk boundaries invalidates stale MP3 files. A change in voice or speech controls invalidates MP3 files before resynthesis.

## Safety boundaries

The merger trusts only the manifest-declared numeric sequence. It refuses missing, tiny or `ffprobe`-invalid MP3 files. AZW3 is rejected rather than guessed because Kindle Format 8 parsing has not yet passed a real compatibility fixture.
