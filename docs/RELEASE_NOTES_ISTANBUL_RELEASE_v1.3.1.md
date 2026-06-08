# Istanbul Release v1.3.1

Recent-jobs usability and validation-state isolation hotfix.

## Fixed

- Isolate Owner-machine publication tests from the real application state root.
- Prune stale history entries whose job manifest no longer exists.
- Show only interrupted or incomplete resumable jobs in the desktop resume panel.
- Render human-readable resume statuses instead of internal `idle` state.
- Render compact local last-active timestamps instead of raw ISO timestamps.
- Move the keep-awake option into a dedicated long-running-operations section.

## Recovery boundary

The application-level history remains a rebuildable index. Per-job `job_manifest.json` remains authoritative.
