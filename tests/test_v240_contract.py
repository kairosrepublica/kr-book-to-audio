from pathlib import Path
import inspect
import unittest

from kr_book_to_audio import diagnostics, export, gui, providers

ROOT = Path(__file__).resolve().parents[1]


class V240ContractTests(unittest.TestCase):
    def test_release_notes_exist(self):
        self.assertTrue((ROOT / 'docs' / 'RELEASE_NOTES_ISTANBUL_RELEASE_v2.4.0.md').is_file())

    def test_edge_online_is_streamed_with_watchdogs(self):
        source = inspect.getsource(providers.EdgeTTSProvider)
        self.assertIn('communicate.stream()', source)
        self.assertIn('ProviderStalled', source)
        self.assertIn('ProviderTimedOut', source)
        self.assertIn('bytes_received', source)

    def test_gui_keeps_updating_after_estimated_ceiling_and_exports_diagnostics(self):
        source = inspect.getsource(gui)
        self.assertIn("text='Export diagnostic ZIP'", source)
        self.assertIn("text='Open diagnostics folder'", source)
        self.assertIn("self.root.after(700, lambda: self._estimate_tick(token))", source)
        self.assertNotIn("if self.current_estimate < 94:", source)
        self.assertIn('last audio', source)

    def test_export_manifest_is_internal_and_user_export_is_flat(self):
        source = inspect.getsource(export)
        self.assertIn("return job.work / 'export_manifest.json'", source)
        self.assertIn('Final Export folder must remain flat', source)
        self.assertIn('cleaned_text_export_path', source)

    def test_diagnostics_exclude_book_body_and_mp3(self):
        source = inspect.getsource(diagnostics)
        self.assertIn('Sanitized diagnostics exclude book text, MP3 files, credentials', source)


    def test_local_provider_uses_governed_archive_first_then_offline_runtime_copy(self):
        setup = (ROOT / 'tools' / 'setup_local_tts_foundation.py').read_text(encoding='utf-8')
        local = (ROOT / 'src' / 'kr_book_to_audio' / 'local_tts.py').read_text(encoding='utf-8')
        self.assertIn("'_Resource' / 'KR_TTS_Offline_Resources'", setup)
        self.assertIn('archive_repo_from_staging', setup)
        self.assertIn('deploy_repo_from_archive', setup)
        self.assertIn("env['HF_HUB_OFFLINE'] = '1'", local)
        self.assertIn("env['TRANSFORMERS_OFFLINE'] = '1'", local)


    def test_local_provider_model_acquisition_is_windows_symlink_safe_and_resumable(self):
        setup = (ROOT / 'tools' / 'setup_local_tts_foundation.py').read_text(encoding='utf-8')
        self.assertIn("env['HF_HUB_DISABLE_SYMLINKS'] = '1'", setup)
        self.assertIn("staging_root = resource_root / '_staging' / ('hf-' + safe)", setup)


if __name__ == '__main__':
    unittest.main()
