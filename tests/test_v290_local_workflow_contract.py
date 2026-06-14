import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class V290LocalWorkflowContractTests(unittest.TestCase):
    def test_reload_button_is_present(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        self.assertIn("self.reload_button = button(workspace, 'Reload book'", source)
    def test_voice_play_is_next_to_voice_controls(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        self.assertIn("'Play sample'", source)
        self.assertIn("'Refresh voice samples'", source)
        self.assertIn('self.rate_scale = tk.Scale', source)
        self.assertIn('self.volume_scale = tk.Scale', source)
    def test_optional_cleanup_title_and_highlight_logic(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        self.assertIn('Apply all recommended cleanup', source)
        self.assertIn('junk_ready or datetime_ready', source)
    def test_legacy_audition_workflow_step_removed(self):
        gui=(ROOT/'src/kr_book_to_audio/gui.py').read_text(encoding='utf-8')
        self.assertNotIn("'audition', '5. Audition voice'",gui)
    def test_reject_and_approve_controls_exist(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        self.assertIn("'Reject Part 1'", source)
        self.assertIn("'Approve Part 1'", source)
        self.assertIn("'Part 1 playback'", source)
    def test_single_part_direct_export_uses_existing_chain(self):
        gui=(ROOT/'src/kr_book_to_audio/gui.py').read_text(encoding='utf-8')
        self.assertIn("if receipt['single_part_direct_export']:",gui)
        self.assertIn("merged = str(merge_parts(job))",gui)
        self.assertIn("append_job_log(job, 'single-part-direct-export'",gui)
        self.assertNotIn("export_report = finalize_export(job, progress=self._progress_event)",gui)
    def test_paint_helper_is_instance_bound(self):
        gui=(ROOT/'src/kr_book_to_audio/gui.py').read_text(encoding='utf-8')
        self.assertIn("def _paint_button(self, button: tk.Button",gui)
        self.assertNotIn("@staticmethod\n    def _paint_button",gui)
    def test_source_change_unlocks_speech_settings(self):
        gui=(ROOT/'src/kr_book_to_audio/gui.py').read_text(encoding='utf-8')
        self.assertIn("self.speech_settings_locked = False\n        self._apply_speech_settings_lock()\n        self.ocr_analysis = None",gui)
if __name__=='__main__': unittest.main()
