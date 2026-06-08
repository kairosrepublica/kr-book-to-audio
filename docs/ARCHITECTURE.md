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

## OCR advisor

The advisor first avoids unnecessary OCR. For PDFs it combines existing PDF diagnosis, representative-page sampling, local capability discovery and language characteristics. When OCR is required it recommends a local provider. The desktop keeps manual override inside a collapsed advanced section.

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
