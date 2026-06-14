from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / 'src' / 'kr_book_to_audio' / 'gui.py'

class V300V30CleanupAlignmentAudioStatusAntiJitterClosureTests(unittest.TestCase):
    def gui(self) -> str:
        return GUI.read_text(encoding='utf-8')

    def test_cleanup_all_uses_same_button_family_and_geometry_as_cleanup_rows(self):
        source = self.gui()
        self.assertIn("self.cleanup_all_button = button(cleanup, 'Apply all recommended cleanup', self.apply_all_cleanup)", source)
        self.assertIn("self.cleanup_all_button.grid(row=2,column=1,sticky='e',pady=2)", source)
        self.assertIn("self.workflow_buttons['cleanup_all'] = self.cleanup_all_button", source)

    def test_audio_status_uses_fixed_single_line_numeric_template(self):
        source = self.gui()
        self.assertIn('def _render_audio_status_summary', source)
        self.assertIn("line = f'Part {index:03d} / {total:03d} | {percent:03d}%'", source)
        self.assertIn("self.status.config(text=line, width=28, anchor='w')", source)
        self.assertNotIn("line = f'{mode} | Part {index:03d} / {total:03d} | {percent:03d}%'", source)

    def test_audio_status_mode_is_stable_and_provider_detail_stays_out_of_status_line(self):
        source = self.gui()
        self.assertIn('def _audio_status_active', source)
        self.assertIn('def _update_provider_telemetry', source)
        self.assertIn("self._log_event(detail)", source)
        self.assertIn('self._render_audio_status_summary(index=index, percent=self.current_estimate)', source)

    def test_v30_runtime_marker_exists(self):
        self.assertIn('V31_REMOVE_SAVE_SINGLE_AUTHORITY_AUDIO_STATUS_RUNTIME', self.gui())

if __name__ == '__main__': unittest.main()
