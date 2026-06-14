# KR Book To Audio 3.0 UI Fix V2 - 2026-06-14

## Scope

This update starts from the Owner-selected V32 source baseline and avoids the later V35-V43 fixture-pollution chain.

## UI fixes

1. Status Treeview percent display now reuses the same live percent used by the bottom progress label.
2. Status row percent refresh no longer recenters the Treeview on every tick, preventing blue-row jump/flicker.
3. Estimated progress no longer visually stalls at 94%; the UI estimate can advance toward 98%, while true 100% remains reserved for actual completion.
4. Run log output is split by line and provider telemetry is throttled into diagnostically useful events instead of per-second spam.

## Files and artifacts

- Latest source ZIP SHA-256: `e42445eb11431fd0f1a3d3ebb45926b19b4333de0a218cc0b53554ce6cc593d0`
- V2 EXE builder SHA-256: `82aa4a8cfcdedeeb0c3a16e622e94d5fb26c21f4bd493bde8b4898b3cba4e460`
- Runtime screenshot SHA-256: `4acf1c86674935a77400d4ec74f813adf6e2f5280fdfc74c042d1ff5376806cb`

## Boundaries

No OCR implementation, TTS provider, resume/reload/reject/save-job, layout, color, font, or GitHub publication logic was changed by the UI patch itself.

## Runtime note

The screenshot committed with this update is Owner-provided runtime evidence for the Status panel and Run log area. It should be used as UI/debug context, not as proof that every long-running TTS edge case is closed.
