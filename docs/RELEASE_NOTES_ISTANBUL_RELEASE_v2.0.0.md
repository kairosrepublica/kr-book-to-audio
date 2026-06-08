# Istanbul Release 2.0

KR Book To Audio reaches its first portable Windows desktop milestone.

## Highlights

- Portable Windows x64 onedir executable.
- No PowerShell or console window during normal desktop launch.
- Timestamped runtime activity log.
- Green-highlighted active Part with dynamic estimated percentage.
- Separate exact overall progress and estimated current-Part progress.
- Linux unit-test CI and Windows portable-build smoke CI.
- Public screenshot, bilingual README positioning and Owner branding.
- Complete private AI co-coder takeover handoff for future debugging and development.

## External-tool boundary

The portable bundle includes the Python runtime and Python dependencies. It does not silently bundle FFmpeg, Poppler or optional OCR engines. The application continues to discover those external tools and provides actionable diagnostics when required capabilities are missing.

## Portable-build correction

The Windows portable spec resolves PyInstaller `SPECPATH` as the spec directory, traverses one parent to reach the frozen payload root and preloads the `src` layout before package-data collection.
