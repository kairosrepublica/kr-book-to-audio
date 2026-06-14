from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / 'src' / 'kr_book_to_audio' / 'gui.py'

class V300V31RemoveSaveSingleAuthorityAudioStatusClosureTests(unittest.TestCase):
    def gui(self) -> str:
        return GUI.read_text(encoding='utf-8')

    def test_save_button_and_manual_save_entrypoints_are_removed(self):
        source = self.gui()
        self.assertNotIn("self.save_job_button = button(workspace, 'Save job', self.save_current_job)", source)
        self.assertNotIn('def _render_save_job_button', source)
        self.assertNotIn('def save_current_job', source)
        self.assertNotIn("append_job_log(self.job, 'manual-save-job'", source)
        self.assertNotIn("'saved_kind': 'ocr-prejob'", source)

    def test_automatic_interrupted_resume_remains_present(self):
        source = self.gui()
        self.assertIn('Resume interrupted or incomplete jobs', source)
        self.assertIn('def refresh_recent_jobs', source)
        self.assertIn('def resume_selected', source)
        self.assertIn('list_resumable_jobs', source)

    def test_audio_status_has_one_minimal_summary_authority(self):
        source = self.gui()
        self.assertIn('def _render_audio_status_summary', source)
        self.assertIn("line = f'Part {index:03d} / {total:03d} | {percent:03d}%'", source)
        self.assertIn("self.status.config(text=line, width=28, anchor='w')", source)
        self.assertNotIn("line = f'{mode} | Part {index:03d} / {total:03d} | {percent:03d}%'", source)

    def test_audio_status_blocks_generic_marquee_and_provider_fragment_overwrite(self):
        source = self.gui()
        self.assertIn('if self._audio_status_active():', source)
        self.assertIn('self._render_audio_status_summary()', source)
        self.assertIn('Provider telemetry | Part', source)
        self.assertIn('self._log_event(detail)', source)

    def test_v31_runtime_marker_exists(self):
        self.assertIn('V31_REMOVE_SAVE_SINGLE_AUTHORITY_AUDIO_STATUS_RUNTIME', self.gui())

if __name__ == '__main__': unittest.main()
