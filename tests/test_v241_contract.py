from pathlib import Path
import inspect
import unittest

from kr_book_to_audio import audio, gui, providers

ROOT = Path(__file__).resolve().parents[1]


class V241ContractTests(unittest.TestCase):
    def test_release_notes_exist(self):
        self.assertTrue((ROOT / 'docs' / 'RELEASE_NOTES_ISTANBUL_RELEASE_v2.4.1.md').is_file())

    def test_gui_uses_latest_only_telemetry_and_bounded_drain(self):
        source = inspect.getsource(gui)
        self.assertIn('class LatestTelemetryMailbox', source)
        self.assertIn('CONTROL_EVENT_QUEUE_MAXSIZE', source)
        self.assertIn('CONTROL_EVENTS_PER_DRAIN', source)
        self.assertIn('CONTROL_DRAIN_TIME_BUDGET_SECONDS', source)
        self.assertIn('self.telemetry_mailbox.publish(payload)', source)
        self.assertIn('self.telemetry_mailbox.take_latest', source)
        self.assertIn('last_played_preview_token', source)

    def test_gui_telemetry_rendering_does_not_force_full_job_refresh(self):
        source = inspect.getsource(gui.App._update_provider_telemetry)
        self.assertNotIn('_refresh_job_view', source)

    def test_audio_bridge_throttles_ui_telemetry(self):
        source = inspect.getsource(audio._provider_progress_bridge)
        self.assertIn('last_ui_emit_monotonic', source)
        self.assertIn('>= 0.20', source)

    def test_kokoro_has_heartbeat_timeout_terminate_and_kill(self):
        source = inspect.getsource(providers.KokoroLocalProvider)
        self.assertIn("stage='local-worker-running'", source)
        self.assertIn('process.terminate()', source)
        self.assertIn('process.kill()', source)
        self.assertIn('ProviderTimedOut', source)

    def test_packaged_windows_probe_is_required(self):
        portable = (ROOT / 'packaging' / 'verify_portable_windows.py').read_text(encoding='utf-8')
        spec = (ROOT / 'packaging' / 'KRBookToAudio.spec').read_text(encoding='utf-8')
        probe = (ROOT / 'src' / 'kr_book_to_audio' / 'gui_runtime_probe.py').read_text(encoding='utf-8')
        self.assertIn('--gui-responsiveness-probe', portable)
        self.assertIn('kr_book_to_audio.gui_runtime_probe', spec)
        self.assertIn('telemetry_injected', probe)
        self.assertIn('100_000', probe)
        self.assertIn('heartbeat_count', probe)
        self.assertIn('close_latency_seconds', probe)


if __name__ == '__main__':
    unittest.main()
