from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / 'src' / 'kr_book_to_audio' / 'gui.py'

class V300V26RuntimeCancellationOCRProgressSaveJobTests(unittest.TestCase):
    def gui(self):
        return GUI.read_text(encoding='utf-8')

    def test_minimum_height_and_orange_save_job(self):
        source = self.gui()
        self.assertIn('minsize(1480, 1260)', source)
        self.assertIn("target = '1580x1260'", source)
        self.assertNotIn("self.save_job_button = button(workspace, 'Save job', self.save_current_job)", source)
        self.assertNotIn("text='[SAVE] Save job', bg='#F0C239'", source)

    def test_cancellation_registry_and_cancellable_progress_wrappers(self):
        source = self.gui()
        self.assertIn('def _interrupt_active_worker_threads', source)
        self.assertIn('PyThreadState_SetAsyncExc', source)
        self.assertIn('def _cancellable_progress_event', source)
        self.assertIn('def _cancellable_ocr_progress_event', source)
        self.assertIn('self._interrupt_active_worker_threads(reason=reason)', source)
        self.assertIn('progress=self._cancellable_progress_event', source)
        self.assertIn('progress=self._cancellable_ocr_progress_event', source)

    def test_reject_is_preview_only_not_reload(self):
        source = self.gui()
        reject = source[source.index('    def reject_part_one(self) -> None:'):source.index('    def reload_current_book(self) -> None:')]
        self.assertIn('self._rollback_part_one_preview_only()', reject)
        self.assertNotIn("self._restart_current_book(reason='Part 1 rejected')", reject)
        self.assertIn('Reviewed text remains approved. Next step: Preview Part 1 again.', source)

    def test_preview_ocr_uses_source_page_truth_and_keeps_whole_book_bar_truthful(self):
        source = self.gui()
        self.assertIn('def _source_pdf_total_pages', source)
        self.assertIn('def _preview_sample_position', source)
        self.assertIn("Preview OCR | sample {sample_index} / {sample_total} | source PDF page {source_page} / {source_total}", source)
        self.assertIn("values = (f'{source_page} / {source_total}', f'{current_pct}%')", source)
        self.assertIn("self._finalize_ocr_progress('Preview OCR sample completed', project_percent=0)", source)

    def test_prepare_gate_requires_completed_full_ocr_not_preview_dir(self):
        source = self.gui()
        self.assertIn('def _ocr_output_ready(self) -> bool:', source)
        self.assertIn("== 'completed'", source)
        self.assertIn("ocr_ready = (not is_pdf) or (analysis is not None and ocr_status != 'required') or self._ocr_output_ready()", source)

    def test_save_job_has_prejob_ocr_and_existing_job_paths(self):
        source = self.gui()
        self.assertNotIn('def save_current_job', source)
        self.assertNotIn("append_job_log(self.job, 'manual-save-job'", source)
        self.assertNotIn("'saved_kind': 'ocr-prejob'", source)
        self.assertNotIn('def _resume_saved_prejob_ocr', source)
        self.assertIn('Resume interrupted or incomplete jobs', source)
        self.assertIn('def resume_selected', source)
        self.assertIn('list_resumable_jobs', source)

if __name__ == '__main__': unittest.main()
