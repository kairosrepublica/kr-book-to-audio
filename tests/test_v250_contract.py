import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class V250ContractTests(unittest.TestCase):
    def test_append_only_local_ocr_foundation_is_shipped(self):
        setup = (ROOT / 'src/kr_book_to_audio/local_ocr_setup.py').read_text(encoding='utf-8')
        local = (ROOT / 'src/kr_book_to_audio/local_ocr.py').read_text(encoding='utf-8')
        self.assertIn('KR_OCR_Offline_Resources', local)
        self.assertIn('HF_HUB_DISABLE_SYMLINKS', setup)
        self.assertIn("'bundles'", setup)
        self.assertIn("'deployments'", setup)
        self.assertIn('ACTIVE_DEPLOYMENT.json', local)
        self.assertIn('RESOURCE_MANIFEST.json', setup)
        self.assertIn('SHA256SUMS.txt', setup)
        self.assertIn('append-only immutable archive bundle', setup)
        self.assertIn('manual cleanup candidates only', setup)

    def test_ordinary_program_use_has_no_first_use_model_download(self):
        providers = (ROOT / 'src/kr_book_to_audio/providers.py').read_text(encoding='utf-8')
        self.assertNotIn('snapshot_download', providers)
        self.assertNotIn('urlopen(', providers)
        self.assertIn('foundation.offline_env()', providers)

    def test_synthesize_all_confirmation_is_removed(self):
        gui = (ROOT / 'src/kr_book_to_audio/gui.py').read_text(encoding='utf-8')
        self.assertNotIn("messagebox.askyesno('Synthesize all parts'", gui)

    def test_portable_verifier_requires_ocr_foundation_probe(self):
        verifier = (ROOT / 'packaging/verify_portable_windows.py').read_text(encoding='utf-8')
        self.assertIn('--ocr-foundation-probe', verifier)
        self.assertIn('run_ocr_foundation_probe', verifier)

    def test_portable_repair_uses_system_python_bootstrap_and_verified_archive_seed(self):
        setup = (ROOT / 'src/kr_book_to_audio/local_ocr_setup.py').read_text(encoding='utf-8')
        self.assertIn('bootstrap_python_command', setup)
        self.assertIn('archived_tree_verified', setup)
        self.assertIn('seed_candidate_archive', setup)

    def test_paddle_worker_receives_explicit_model_names(self):
        providers = (ROOT / 'src/kr_book_to_audio/providers.py').read_text(encoding='utf-8')
        worker = (ROOT / 'src/kr_book_to_audio/paddleocr_worker_script.py').read_text(encoding='utf-8')
        self.assertIn('text_detection_model_name', providers)
        self.assertIn('text_recognition_model_name', providers)
        self.assertIn('text_detection_model_name=det_name', worker)
        self.assertIn('text_recognition_model_name=rec_name', worker)

    def test_unrelated_tts_foundation_remains_present(self):
        self.assertTrue((ROOT / 'src/kr_book_to_audio/local_tts.py').is_file())
        self.assertTrue((ROOT / 'tools/setup_local_tts_foundation.py').is_file())


if __name__ == '__main__':
    unittest.main()
