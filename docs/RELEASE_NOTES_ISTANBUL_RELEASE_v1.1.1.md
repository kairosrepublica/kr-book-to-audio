# Istanbul Release v1.1.1

Windows PDF and GUI cleanup hotfix.

## Fixed

- Poppler output is read as bytes before decoding, preventing Windows reader-thread failures caused by implicit console-code-page assumptions.
- PDF-title extraction falls back safely to the source filename when metadata output is empty or unusable.

## Simplified

- The desktop form remains compact. Detailed explanations live behind `ⓘ` hover markers.
- Book folder, local working root and export root now provide explicit default-setting actions.
- Metadata-like date/time cleanup now lives under **Optional cleanup**.
- The unrelated script-conversion feature and its optional dependency have been removed.

## Compatibility

Older local configuration and job manifests remain readable. Retired fields are migrated or ignored safely.
