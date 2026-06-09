import unittest
from unittest.mock import patch
from kr_book_to_audio.gui import App
from kr_book_to_audio.ocr import OCRAnalysis

class OcrGuiGatingTests(unittest.TestCase):
    def test_not_required_ocr_invocation_is_informational_noop(self):
        class Dummy:
            ocr_analysis=OCRAnalysis('not-needed','pdf','chinese','native-text','native',[],{},100)
            def _selected_ocr_provider(self): return 'native-text'
            def _log_event(self, text): self.logged=text
        dummy=Dummy()
        with patch('kr_book_to_audio.gui.messagebox.showinfo') as info:
            App.run_ocr(dummy)
        info.assert_called_once()
        self.assertIn('Native text',dummy.logged)
