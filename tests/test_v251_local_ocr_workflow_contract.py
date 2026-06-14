import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class V251LocalOCRWorkflowContractTests(unittest.TestCase):
    def test_guided_controls_exist(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        for token in ('Analyze text', 'Preview 3-page OCR sample', 'Run full OCR', 'Open OCR results', 'Pause OCR', 'Resume OCR', 'Cancel OCR'):
            self.assertIn(token, source)
    def test_maintenance_is_inside_advanced_panel(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        self.assertIn("self.ocr_advanced = ttk.Frame", source)
        self.assertIn('Install / repair local OCR foundation', source)
        self.assertIn('Open OCR resource folder', source)
    def test_export_routing_uses_export_root(self):
        gui=(ROOT/'src/kr_book_to_audio/gui.py').read_text(encoding='utf-8'); ocr=(ROOT/'src/kr_book_to_audio/ocr.py').read_text(encoding='utf-8')
        self.assertIn('ocr_results_dir(Path(self.export_root.get()), source)',gui)
        self.assertIn('export_dir: Path | None = None',ocr)
        self.assertIn('_ocr_review.txt',ocr)
    def test_normal_log_filters_hidden_launch_noise(self):
        gui=(ROOT/'src/kr_book_to_audio/gui.py').read_text(encoding='utf-8')
        self.assertNotIn('hidden-window launch',gui)
if __name__=='__main__': unittest.main()
