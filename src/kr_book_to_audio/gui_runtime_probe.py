from __future__ import annotations
from pathlib import Path
import json
import os
import queue
import tempfile
import threading
import time
import tkinter as tk


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8', newline='\n')


def run_gui_responsiveness_probe(evidence_path: Path) -> dict[str, object]:
    """Exercise the real Tk event loop under sustained Provider telemetry pressure.

    The probe avoids network access. It instantiates the production App, injects one
    control transition and a large burst of latest-only Provider telemetry from a
    background producer, then verifies that Tk heartbeats, scheduled close handling
    and always-available diagnostics controls continue to execute.
    """
    from . import gui

    evidence_path = Path(evidence_path)
    with tempfile.TemporaryDirectory(prefix='kr-b2a-v241-gui-probe-') as temp_dir:
        probe_root = Path(temp_dir)
        os.environ['KR_B2A_APP_ROOT'] = str(probe_root / 'app-root')
        original_load_config = gui.load_config
        original_save_config = gui.save_config
        original_refresh_voices = gui.App._refresh_voices
        original_startup_recovery = gui.App._startup_recovery
        gui.load_config = lambda: {}
        gui.save_config = lambda _payload: None
        gui.App._refresh_voices = lambda self, *, background: None
        gui.App._startup_recovery = lambda self: None
        root = tk.Tk()
        root.title('KR Book To Audio v2.4.1 GUI responsiveness probe')
        root.geometry('1200x900')
        app = gui.App(root)
        app._progress_event({'index': 1, 'state': 'running', 'estimated_percent': 5, 'text_chars': 5000, 'attempt': 1})
        heartbeat_count = 0
        close_requested_monotonic: float | None = None
        close_processed_monotonic: float | None = None
        producer_done = threading.Event()
        producer_error: list[str] = []

        def producer() -> None:
            try:
                for seq in range(100_000):
                    app._progress_event({
                        'index': 1,
                        'state': 'provider-status',
                        'provider_id': 'edge-tts',
                        'stage': 'receiving-audio',
                        'attempt': 1,
                        'elapsed_seconds': seq / 1000.0,
                        'bytes_received': seq * 1024,
                        'last_audio_seconds_ago': 0.0,
                    })
            except Exception as exc:  # pragma: no cover - target-runtime evidence path
                producer_error.append(f'{type(exc).__name__}: {exc}')
            finally:
                producer_done.set()

        def heartbeat() -> None:
            nonlocal heartbeat_count
            heartbeat_count += 1
            root.after(10, heartbeat)

        def request_close() -> None:
            nonlocal close_requested_monotonic
            close_requested_monotonic = time.monotonic()
            root.after(10, close_probe)

        def close_probe() -> None:
            nonlocal close_processed_monotonic
            close_processed_monotonic = time.monotonic()
            root.quit()

        threading.Thread(target=producer, daemon=True).start()
        root.after(5, heartbeat)
        root.after(850, request_close)
        started = time.monotonic()
        try:
            root.mainloop()
        finally:
            elapsed = time.monotonic() - started
            diagnostics_state = str(app.diagnostic_button.cget('state'))
            open_diagnostics_state = str(app.open_diagnostics_button.cget('state'))
            queue_size = int(app.events.qsize())
            telemetry_pending = int(app.telemetry_mailbox.pending_count())
            try:
                root.destroy()
            except tk.TclError:
                pass
            gui.load_config = original_load_config
            gui.save_config = original_save_config
            gui.App._refresh_voices = original_refresh_voices
            gui.App._startup_recovery = original_startup_recovery
        producer_done.wait(timeout=3.0)
        close_latency = None
        if close_requested_monotonic is not None and close_processed_monotonic is not None:
            close_latency = close_processed_monotonic - close_requested_monotonic
        report = {
            'ok': bool(
                not producer_error
                and producer_done.is_set()
                and heartbeat_count >= 15
                and close_latency is not None
                and close_latency < 0.50
                and telemetry_pending <= 1
                and diagnostics_state != 'disabled'
                and open_diagnostics_state != 'disabled'
                and elapsed < 5.0
            ),
            'heartbeat_count': heartbeat_count,
            'close_latency_seconds': close_latency,
            'elapsed_seconds': elapsed,
            'producer_done': producer_done.is_set(),
            'producer_error': producer_error,
            'control_queue_size': queue_size,
            'telemetry_pending': telemetry_pending,
            'diagnostic_button_state': diagnostics_state,
            'open_diagnostics_button_state': open_diagnostics_state,
            'telemetry_injected': 100_000,
        }
        _write_json(evidence_path, report)
        if not report['ok']:
            raise RuntimeError(f'GUI responsiveness probe rejected: {report}')
        return report
