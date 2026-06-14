from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / 'src' / 'kr_book_to_audio' / 'gui.py'

class V300V27SingleCanonicalRuntimeWriterClosureTests(unittest.TestCase):
    def gui(self) -> str:
        return GUI.read_text(encoding='utf-8')

    def test_reload_uses_truthful_external_work_disable_policy(self):
        source = self.gui()
        self.assertIn('def _reload_blocked_by_active_external_work', source)
        self.assertIn("if self._reload_blocked_by_active_external_work():", source)
        self.assertIn("Reload book is disabled while OCR or audio work is active.", source)

    def test_reject_uses_harmonious_light_red_role(self):
        source = self.gui()
        self.assertIn("'reject': ('#F6D6D6', '#7A1F1F', 'normal', '[REJECT] ')", source)
        self.assertIn('_part_one_rejected_pending_preview = True', source)

    def test_full_ocr_uses_source_page_and_source_total_semantics(self):
        source = self.gui()
        self.assertIn('def _source_pdf_total_pages', source)
        self.assertIn("values = (f'{source_page} / {source_total}', f'{current_pct}%')", source)
        self.assertIn('processed / max(1, source_total) * 100.0', source)
        self.assertIn("Full OCR | page {source_page} / {source_total}", source)

    def test_v28_runtime_owner_marker_exists(self):
        self.assertIn('V28_SAFE_RELOAD_UI_TEXT_PREPARE_WATCHDOG_DIALOG_RUNTIME', self.gui())

if __name__ == '__main__': unittest.main()
