# Architecture

## Core rule

The command-line interface and desktop interface are thin adapters around one shared Python core. OCR, text processing and text-to-speech are separate layers.

## Data flow

```text
source
  OCR advisor
    native text accepted
    or local OCR recommended
  extract
  profile-aware clean
  cleanup advisor
  proofread.txt
  explicit proofreading approval
  pronunciation dictionary
  sentence-aware chunking
  Part-1 synthesis and listening approval
  provider-bound TTS synthesis
  ffprobe validation
  exact overall progress and estimated current-part progress
  strict manifest-bound merge
  durable execution checkpoint
  Recent jobs index
```

## Provider contracts

`providers.py` defines independent OCR and TTS registries.

Enabled TTS provider:

```text
edge-tts
```

Discoverable local OCR providers:

```text
paddleocr-ppocrv5
tesseract-local
ocrmypdf-tesseract
```

Reserved external API slots:

```text
openai-vision-api
claude-vision-api
custom-http-ocr-api
azure-speech-api
openai-tts-api
custom-http-tts-api
```

Reserved providers are disabled and cannot run. Credentials may only come from Owner-local environment variables or a future secret store. Job manifests, logs and public configuration never persist API secrets.

## Durable resume

`job_manifest.json` is the authoritative per-job checkpoint. It records operation state, PID, heartbeat, current Part, last completed Part and whether resume is required.

`execution_history.json` is a rebuildable application-level navigation index stored under the stable application root. The GUI uses it to show recent jobs across upgrades.

Validated MP3 files receive sidecar metadata binding the MP3 hash to the text hash, TTS audio signature and task-bound speech controls. After an abnormal exit, recovery deletes residual partial files, validates recorded MP3 files, adopts only trusted sidecar-bound orphans and resumes from the first incomplete Part.

Stale lock recovery is conservative: an existing lock is removed automatically only after the recorded process ID is confirmed dead. Malformed locks remain blocked for manual review.

Windows keep-awake wraps long OCR and TTS operations and is always released on normal completion or handled exceptions.

## OCR advisor

The advisor first avoids unnecessary OCR. OCR providers also declare whether page-level checkpointing can be supported in a future release; the current release records OCR execution state without claiming universal page-level resume. For PDFs it combines existing PDF diagnosis, representative-page sampling, local capability discovery and language characteristics. When OCR is required it recommends a local provider. The desktop keeps manual override inside a collapsed advanced section.

## Text processing profiles

```text
auto
chinese
english
mixed
general-prose
```

Chinese normalization removes glyph-gap whitespace while preserving ASCII-internal spaces. English and general prose avoid Chinese-specific deletion rules.

## Cleanup advisor

Cleanup analysis reports high-confidence and review-required candidates. Action buttons apply only high-confidence candidates. Ambiguous repeated text remains preserved. Every cleanup action creates a proofread backup and invalidates stale approvals and audio when the text changes.

## Progress boundary

Overall progress is exact because it is derived from validated completed MP3 parts. Current-part progress is estimated because edge-tts does not expose an authoritative server-side percentage. Estimated progress stops below 100 until the MP3 passes `ffprobe` validation.

## Safety boundary

The merger trusts only manifest-declared numeric sequences, provider-bound audio signatures and validated hashes. AZW3 remains rejected until a real parser fixture exists. Cloud API adapters remain disabled until a future explicit privacy, cost and provider-specific approval.

## Recent-job presentation boundary

`execution_history.json` is a rebuildable index. The GUI resume panel displays only valid job roots with an existing `_work/job_manifest.json`, only actionable interrupted or incomplete jobs and only the newest resumable attempt for each source book. Validation fixtures must use an isolated `KR_B2A_APP_ROOT`.


## Resume speech-control boundary

Each job manifest stores the TTS provider, voice, rate, pitch and volume that produced the approved Part-1 signature. One-click resume restores this task-bound tuple before continuing from the first incomplete Part.

Legacy tasks created before v1.3.2 may not contain the raw control tuple. The application may recover only a tuple that cryptographically matches the stored audio signature. It must not guess custom settings. If no safe match exists, existing MP3 files remain preserved and the operator receives an actionable request to generate and approve Part 1 again.


## Branding surface

The Owner-approved SVG is the canonical BA icon source. The PNG asset is retained as a Tk desktop fallback, and a multi-resolution Windows ICO is generated for title-bar, taskbar, Alt + Tab and future portable-executable reuse.

GUI icon setup is deliberately fail-soft: a missing optional branding asset must not block audiobook work. The bottom footer is a separate layout row below the log and Part-status surfaces so it cannot cover progress or operator controls.
