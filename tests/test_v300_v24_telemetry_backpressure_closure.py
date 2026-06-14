from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]

class V300V24TelemetryBackpressureClosureTests(unittest.TestCase):
    def gui(self) -> str:
        return (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')

    def test_provider_status_uses_latest_only_mailbox_not_control_queue(self):
        source = self.gui()
        self.assertIn("if state == 'provider-status':", source)
        self.assertIn('self.telemetry_mailbox.publish(payload)', source)
        self.assertIn("self.events.put(('progress', 'Synthesis', payload, None))", source)
        provider_branch = source[source.index("if state == 'provider-status':"):source.index("if index > 0 and state in {'running', 'retrying'}:")]
        self.assertNotIn("self.events.put(('progress'", provider_branch)

    def test_terminal_control_event_discards_stale_mailbox_snapshot(self):
        source = self.gui()
        self.assertIn('self.telemetry_mailbox.reopen(index)', source)
        self.assertIn('self.telemetry_mailbox.mark_terminal(index)', source)
        self.assertIn('self.telemetry_mailbox = LatestTelemetryMailbox()', source)

    def test_ocr_progress_uses_same_generation_boundary(self):
        source = self.gui()
        self.assertIn("normalized['_operation_generation'] = generation", source)
        self.assertIn("self.events.put(('ocr-progress', 'OCR', normalized, None))", source)
        self.assertIn("payload.get('_operation_generation', self._current_operation_generation())", source)

    def test_window_state_replace_uses_central_durable_helper(self):
        source = self.gui()
        self.assertIn('from .durable_io import replace_with_retry', source)
        self.assertIn('replace_with_retry(temp, path)', source)
        self.assertNotIn('os.replace(temp, path)', source)

if __name__ == '__main__': unittest.main()
