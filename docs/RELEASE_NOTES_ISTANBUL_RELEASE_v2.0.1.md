# Istanbul Release v2.0.1 — Export Finalization

This patch closes a deliverable-boundary defect discovered during Owner acceptance of Istanbul Release 2.0. Internal checkpoint MP3 files could be valid while the configured external output folder remained empty.

## Added

- mandatory export finalization after successful full synthesis and retry completion;
- atomic copying of validated Part MP3 files into `<Export root>/<job>/parts`;
- `export_manifest.json` written only after exact verification passes;
- **9. Verify export** for legacy empty-output repair without TTS regeneration;
- direct **Open** actions beside Book, Local working root, Export root and Pronunciation dictionary paths.

## Changed

- **Open output folder** no longer creates an empty output directory. If final export is not ready, it offers the internal working-audio folder instead.
- Merge MP3 refreshes export verification and records the merged audiobook in the export manifest.

## Integrity boundary

An externally deliverable job is complete only when expected Part count, continuous filenames, non-empty MP3 readability and SHA-256 checkpoint matching all pass. Internal resume checkpoints are preserved.
