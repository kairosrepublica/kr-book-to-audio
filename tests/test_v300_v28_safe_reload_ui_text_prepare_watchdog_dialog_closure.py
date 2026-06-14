from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / 'src' / 'kr_book_to_audio' / 'gui.py'

class V300V28SafeReloadUiTextPrepareWatchdogDialogClosureTests(unittest.TestCase):
    def gui(self) -> str:
        return GUI.read_text(encoding='utf-8')

    def test_cleanup_all_has_no_optional_prefix_and_is_right_aligned(self):
        source = self.gui()
        self.assertIn("self.cleanup_all_button = button(cleanup, 'Apply all recommended cleanup', self.apply_all_cleanup)", source)
        self.assertIn("self.cleanup_all_button.grid(row=2,column=1,sticky='e',pady=2)", source)
        self.assertIn("self.workflow_buttons['cleanup_all'] = self.cleanup_all_button", source)
        self.assertNotIn("'[OPTIONAL] Apply all recommended cleanup'", source)

    def test_approve_reviewed_text_button_label_is_shortened(self):
        source = self.gui()
        self.assertIn("'approve_text', 'Approve reviewed text', self.approve_proofread", source)
        self.assertNotIn("'approve_text', 'Approve reviewed text and rebuild'", source)

    def test_reload_is_disabled_during_external_audio_or_ocr_work(self):
        source = self.gui()
        self.assertIn('def _reload_blocked_by_active_external_work', source)
        for token in ('preview part 1', 'synthesize all', 'preview ocr', 'run full ocr'):
            self.assertIn(token, source)
        self.assertIn("button.config(text='Reload book', bg='SystemButtonFace', fg='SystemGrayText', state='disabled'", source)

    def test_reject_rolls_ui_back_to_preview_only(self):
        source = self.gui()
        self.assertIn('_part_one_rejected_pending_preview = True', source)
        self.assertIn("elif bool(getattr(self, '_part_one_rejected_pending_preview', False)):", source)
        self.assertIn("roles['preview'] = 'next'", source)

    def test_prepare_has_truthful_watchdog_trace(self):
        source = self.gui()
        self.assertIn('def _prepare_watchdog_tick', source)
        self.assertIn("prepare-text-heartbeat.log", source)
        self.assertIn("Prepare text is running | elapsed", source)

    def test_ocr_dialogs_align_to_main_window_top_left(self):
        source = self.gui()
        self.assertIn('def _place_child_dialog_at_main_window_top_left', source)
        self.assertIn('self.root.winfo_rootx()', source)
        self.assertIn('self.root.winfo_rooty()', source)
        self.assertIn('self._show_ocr_completion_dialog(path)', source)

if __name__ == '__main__': unittest.main()
