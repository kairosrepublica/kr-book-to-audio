import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kr_book_to_audio.ocr import OCRAnalysis, OCRControl, run_recommended_ocr
from kr_book_to_audio.ocr_workflow_ui import OCR_BORDER_COMPLETE, OCR_BORDER_REQUIRED, derive_ocr_ui_plan, ocr_results_dir, provider_display_label


class RecordingProvider:
    page_checkpoint_capable = True
    def __init__(self): self.calls = []
    def recognize_pdf_to_text(self, source, *, language, output_dir, pages=None, progress=None):
        page = int(list(pages or [0])[0]); self.calls.append(page); return f'page {page} text'


class OCRWorkflowV251Tests(unittest.TestCase):
    def test_selected_source_highlights_analyze_and_blocks_prepare(self):
        plan=derive_ocr_ui_plan(source_selected=True,analysis_status=None,provider_available=False,preview_ready=False,output_ready=False,operation=None)
        self.assertEqual(plan.roles['analyze'],'next'); self.assertEqual(plan.roles['prepare'],'blocked')

    def test_native_text_enables_prepare_and_blocks_ocr(self):
        plan=derive_ocr_ui_plan(source_selected=True,analysis_status='not-needed',provider_available=False,preview_ready=False,output_ready=False,operation=None)
        self.assertEqual(plan.roles['prepare'],'next'); self.assertEqual(plan.roles['preview'],'blocked')

    def test_required_source_uses_red_border_and_highlights_preview(self):
        plan=derive_ocr_ui_plan(source_selected=True,analysis_status='required',provider_available=True,preview_ready=False,output_ready=False,operation=None)
        self.assertEqual(plan.border,OCR_BORDER_REQUIRED); self.assertEqual(plan.roles['preview'],'next'); self.assertEqual(plan.roles['run'],'optional')

    def test_preview_completion_highlights_full_ocr(self):
        plan=derive_ocr_ui_plan(source_selected=True,analysis_status='required',provider_available=True,preview_ready=True,output_ready=False,operation=None)
        self.assertEqual(plan.roles['run'],'next')

    def test_completed_ocr_enables_prepare(self):
        plan=derive_ocr_ui_plan(source_selected=True,analysis_status='completed',provider_available=True,preview_ready=True,output_ready=True,operation=None)
        self.assertEqual(plan.border,OCR_BORDER_COMPLETE); self.assertEqual(plan.roles['prepare'],'next'); self.assertEqual(plan.roles['output'],'normal')

    def test_provider_label_marks_recommended_profile(self):
        self.assertEqual(provider_display_label('paddleocr-ppocrv5',recommended_provider='paddleocr-ppocrv5',labels={'paddleocr-ppocrv5':'PaddleOCR PP-OCRv5 · server accuracy'}),'PaddleOCR PP-OCRv5 · server accuracy · recommended')

    def test_export_results_folder_is_below_export_root(self):
        root=Path('D:/Export'); result=ocr_results_dir(root,Path('C:/books/My Book.pdf'))
        self.assertEqual(result.parent.parent,root)
        self.assertEqual(result.name,'OCR')
        self.assertTrue(result.parent.name)

    def test_full_ocr_writes_review_text_below_export_root(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=root/'scan.pdf'; source.write_bytes(b'%PDF')
            analysis=OCRAnalysis('required','pdf','english','fake','test',[1,2],{},0); provider=RecordingProvider()
            with patch('kr_book_to_audio.ocr.get_ocr_provider',return_value=provider),patch('kr_book_to_audio.ocr.diagnose',return_value={'pages':2}):
                output=run_recommended_ocr(source,analysis,output_dir=root/'work',export_dir=root/'export',provider_id='fake',keep_awake=False)
            self.assertEqual(output,root/'export'/'scan_ocr_review.txt')
            self.assertTrue((root/'export'/'scan_ocr_raw.txt').is_file()); self.assertTrue((root/'export'/'scan_ocr_summary.json').is_file())

    def test_cancel_before_checkpoint_commit_does_not_claim_page_complete(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=root/'scan.pdf'; source.write_bytes(b'%PDF')
            analysis=OCRAnalysis('required','pdf','english','fake','test',[1,2],{},0); provider=RecordingProvider(); control=OCRControl(); original=provider.recognize_pdf_to_text
            def cancel_after_first(*args,**kwargs):
                value=original(*args,**kwargs); control.cancel(); return value
            provider.recognize_pdf_to_text=cancel_after_first
            with patch('kr_book_to_audio.ocr.get_ocr_provider',return_value=provider),patch('kr_book_to_audio.ocr.diagnose',return_value={'pages':2}):
                with self.assertRaisesRegex(RuntimeError,'cancelled by the user'):
                    run_recommended_ocr(source,analysis,output_dir=root/'work',provider_id='fake',keep_awake=False,control=control)
            self.assertFalse(list((root/'work').rglob('page-0001.txt')))

    def test_normal_gui_log_does_not_emit_hidden_window_launch(self):
        gui=(Path(__file__).resolve().parents[1]/'src/kr_book_to_audio/gui.py').read_text(encoding='utf-8')
        self.assertNotIn('hidden-window launch',gui); self.assertIn('External tool failed:',gui)

if __name__=='__main__': unittest.main()
