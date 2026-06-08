# Istanbul Release v1.3.4 — Robust Resume UX and CI Closure

This reliability checkpoint closes the remote GitHub Actions packaging defect and makes legacy durable resume explicit.

## CI closure

- declares Pillow under the test extra;
- installs `.[test]` in GitHub Actions;
- packages BA branding assets inside the Python package;
- upgrades GitHub Actions to the Node.js 24 compatible action line;
- triggers push CI only for `main`;
- blocks tag and GitHub Release creation until the remote `main` workflow is green.

## Guided legacy resume

Legacy checkpoints that lack a complete speech-control snapshot enter `voice-check-required`. The desktop preserves completed MP3 files, opens preserved and candidate Part 1 previews for comparison, records explicit Owner approval and automatically resumes from the first incomplete Part. Older attempts remain available through **Show older attempts…** but stay collapsed by default.
