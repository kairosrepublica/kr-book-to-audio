from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]

class V20WorkflowStatusReloadContractTests(unittest.TestCase):
    def gui(self) -> str:
        return (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')

    def test_open_cleaned_advances_to_approve_and_prepare_is_completed(self):
        source = self.gui()
        self.assertIn('open_cleaned_text_and_advance', source)
        self.assertIn("roles['open_cleaned'] = 'completed'; roles['approve_text'] = 'next'", source)
        self.assertIn("roles['prepare'] = 'completed'", source)

    def test_reload_is_always_available_and_resets_analysis(self):
        source = self.gui()
        self.assertIn("text='[RELOAD] Reload book'", source)
        self.assertIn('def _reload_blocked_by_active_external_work', source)
        self.assertIn("if self._reload_blocked_by_active_external_work():", source)
        self.assertIn("Reload book is disabled while OCR or audio work is active.", source)
        self.assertIn("self._restart_current_book(reason='manual reload')", source)

    def test_status_is_fixed_width_two_columns_and_has_one_current_bar(self):
        source = self.gui()
        self.assertIn("columns=('part','state')", source)
        self.assertNotIn("heading('stage'", source)
        self.assertIn("self.parts_frame.configure(width=430)", source)
        self.assertIn("self.status_current_progress = ttk.Progressbar", source)
        self.assertNotIn("self.current_progress = ttk.Progressbar", source)

    def test_log_bar_is_overall_and_status_bar_is_current_item(self):
        source = self.gui()
        self.assertIn("self.overall_progress = self.log_progress", source)
        self.assertIn("self.current_progress = self.status_current_progress", source)
        self.assertIn('def _set_project_overall_percent', source)
        self.assertIn('def _set_status_item_percent', source)

    def test_volume_slider_updates_active_embedded_player(self):
        source = self.gui()
        self.assertIn("setaudio kr_b2a_voice_sample volume to", source)
        self.assertIn('def _volume_slider_changed', source)

if __name__ == '__main__': unittest.main()
