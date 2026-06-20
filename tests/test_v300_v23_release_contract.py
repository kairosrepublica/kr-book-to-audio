from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]

class V300ReleaseContractTests(unittest.TestCase):
    def gui(self) -> str:
        return (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')

    def test_title_minimum_height_and_persistent_window_geometry(self):
        source = self.gui()
        self.assertIn("title('KR Book To Audio 3.2')", source)
        self.assertIn('minsize(1480, 1260)', source)
        self.assertIn("target = '1580x1260'", source)
        self.assertIn('window_state_v3.json', source)
        self.assertIn("binder('<Configure>', self._schedule_window_state_save", source)

    def test_reject_preview_uses_harmonious_light_red_role(self):
        source = self.gui()
        self.assertIn("'reject': ('#F6D6D6', '#7A1F1F', 'normal', '[REJECT] ')", source)
        self.assertIn("roles['reject_preview'] = 'reject'; roles['approve_preview'] = 'approve'", source)

    def test_reload_approve_and_reject_stop_playback_and_cancel_old_work(self):
        source = self.gui()
        self.assertIn('def _reload_blocked_by_active_external_work', source)
        self.assertIn("if self._reload_blocked_by_active_external_work():", source)
        self.assertIn("self._stop_mci_alias('kr_b2a_voice_sample')", source)
        self.assertIn("self._restart_current_book(reason='manual reload')", source)
        self.assertIn("self._rollback_part_one_preview_only()", source)
        self.assertIn("self._part_one_rejected_pending_preview = True", source)

    def test_full_ocr_page_total_overall_progress_and_log_share_one_truth(self):
        source = self.gui()
        self.assertIn('def _source_pdf_total_pages', source)
        self.assertIn("values = (f'{source_page} / {source_total}', f'{current_pct}%')", source)
        self.assertIn('processed / max(1, source_total) * 100.0', source)
        self.assertIn("Full OCR | page {source_page} / {source_total} | current page {current_pct}% | whole book {overall_pct:.1f}%", source)

if __name__ == '__main__': unittest.main()
