import os
import tempfile
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch

from kr_book_to_audio.local_tts import KOKORO_VOICES, governed_resource_archive_root, kokoro_foundation, kokoro_speed_from_rate
from kr_book_to_audio.providers import TTS_PROVIDER_SPECS, get_tts_provider

ROOT = Path(__file__).resolve().parents[1]


class LocalTTSFoundationTests(unittest.TestCase):
    def test_kokoro_local_provider_is_registered_and_lists_chinese_and_english(self):
        self.assertTrue(TTS_PROVIDER_SPECS['kokoro-local'].enabled)
        voices = get_tts_provider('kokoro-local').list_voices()
        self.assertTrue(any(item['locale'].startswith('zh-') for item in voices))
        self.assertTrue(any(item['locale'].startswith('en-') for item in voices))

    def test_foundation_paths_are_isolated_under_owner_local_root(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'KR_B2A_LOCAL_TTS_ROOT': td}):
            foundation = kokoro_foundation()
            self.assertEqual(foundation.root, Path(td))
            self.assertIn('kokoro_worker.py', foundation.worker.name)
            self.assertFalse(foundation.ready()[0])

    def test_kokoro_rate_conversion_is_bounded(self):
        self.assertEqual(kokoro_speed_from_rate('+0%'), 1.0)
        self.assertAlmostEqual(kokoro_speed_from_rate('-10%'), 0.9)
        with self.assertRaises(RuntimeError):
            kokoro_speed_from_rate('+200%')

    def test_setup_tool_downloads_required_kokoro_and_optional_qwen_foundation(self):
        text = (ROOT / 'tools' / 'setup_local_tts_foundation.py').read_text(encoding='utf-8')
        self.assertIn('hexgrad/Kokoro-82M', text)
        self.assertIn('hexgrad/Kokoro-82M-v1.1-zh', text)
        self.assertIn('Qwen/Qwen3-TTS-Tokenizer-12Hz', text)
        self.assertIn('Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice', text)
        self.assertIn('LOCAL TTS FOUNDATION PASS', text)

    def test_setup_uses_isolated_uv_managed_python_312_for_kokoro_094(self):
        text = (ROOT / 'tools' / 'setup_local_tts_foundation.py').read_text(encoding='utf-8')
        self.assertIn("KOKORO_PACKAGE = 'kokoro==0.9.4'", text)
        self.assertIn("KOKORO_RUNTIME_REQUEST = '3.12'", text)
        self.assertIn("UV_PYTHON_INSTALL_DIR", text)
        self.assertIn("UV_PYTHON_NO_REGISTRY", text)
        self.assertIn("UV_NO_MODIFY_PATH", text)
        self.assertIn("created-isolated-uv-managed-python-3.12", text)

    def test_kokoro_runtime_compatibility_contract_rejects_python_313(self):
        tool_path = ROOT / 'tools' / 'setup_local_tts_foundation.py'
        spec = importlib.util.spec_from_file_location('setup_local_tts_foundation_fixture', tool_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(module.kokoro_python_version_is_supported((3, 12, 13)))
        self.assertFalse(module.kokoro_python_version_is_supported((3, 13, 0)))
        self.assertFalse(module.kokoro_python_version_is_supported((3, 9, 9)))


    def test_online_acquisition_environment_overrides_inherited_offline_flags(self):
        tool_path = ROOT / 'tools' / 'setup_local_tts_foundation.py'
        spec = importlib.util.spec_from_file_location('setup_local_tts_foundation_online_fixture', tool_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.dict(os.environ, {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1'}):
            env = module.online_acquisition_env()
        self.assertEqual(env['HF_HUB_OFFLINE'], '0')
        self.assertEqual(env['TRANSFORMERS_OFFLINE'], '0')
        self.assertEqual(env['HF_DATASETS_OFFLINE'], '0')

    def test_offline_worker_environment_enforces_offline_flags(self):
        tool_path = ROOT / 'tools' / 'setup_local_tts_foundation.py'
        spec = importlib.util.spec_from_file_location('setup_local_tts_foundation_worker_fixture', tool_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as td:
            env = module.worker_env(Path(td))
        self.assertEqual(env['HF_HUB_OFFLINE'], '1')
        self.assertEqual(env['TRANSFORMERS_OFFLINE'], '1')
        self.assertEqual(env['HF_DATASETS_OFFLINE'], '1')

    def test_governed_resource_archive_is_separate_from_runtime_copy(self):
        with tempfile.TemporaryDirectory() as runtime, tempfile.TemporaryDirectory() as archive:
            foundation = kokoro_foundation(Path(runtime), Path(archive))
            self.assertEqual(foundation.root, Path(runtime))
            self.assertEqual(foundation.resource_archive_root, Path(archive))
            self.assertNotEqual(foundation.root, foundation.resource_archive_root)

    def test_setup_archives_before_deploying_runtime_copy(self):
        text = (ROOT / 'tools' / 'setup_local_tts_foundation.py').read_text(encoding='utf-8')
        self.assertIn("'_Resource' / 'KR_TTS_Offline_Resources'", text)
        self.assertIn('archive_repo_from_staging', text)
        self.assertIn('deploy_repo_from_archive', text)
        self.assertLess(text.index('archive_repo_from_staging'), text.index('deploy_repo_from_archive'))
        self.assertIn('RESOURCE_MANIFEST.json', text)
        self.assertIn('SHA256SUMS.txt', text)
        self.assertIn("run([str(py), '-m', 'pip', 'wheel'", text)
        self.assertIn("'--no-index'", text)


    def test_fake_model_cache_is_archived_then_deployed(self):
        tool_path = ROOT / 'tools' / 'setup_local_tts_foundation.py'
        spec = importlib.util.spec_from_file_location('setup_local_tts_foundation_cache_fixture', tool_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            staging_hub = base / 'staging' / 'hub'
            archive_hub = base / 'archive' / 'hub'
            runtime_hub = base / 'runtime' / 'hub'
            repo_id = 'hexgrad/Kokoro-82M'
            fake = staging_hub / module.repo_cache_name(repo_id) / 'snapshots' / 'abc123'
            fake.mkdir(parents=True)
            (fake / 'config.json').write_text('{}', encoding='utf-8')
            module.archive_repo_from_staging(staging_hub=staging_hub, archive_hub=archive_hub, repo_id=repo_id)
            module.deploy_repo_from_archive(archive_hub=archive_hub, runtime_hub=runtime_hub, repo_id=repo_id)
            self.assertTrue((runtime_hub / module.repo_cache_name(repo_id) / 'snapshots' / 'abc123' / 'config.json').is_file())

    def test_resource_manifest_records_archived_files(self):
        tool_path = ROOT / 'tools' / 'setup_local_tts_foundation.py'
        spec = importlib.util.spec_from_file_location('setup_local_tts_foundation_manifest_fixture', tool_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td)
            (archive / 'models').mkdir()
            (archive / 'models' / 'fixture.bin').write_bytes(b'fixture')
            manifest, sums, receipt = module.resource_manifest(archive, report={'runtime_root': 'fixture-runtime', 'kokoro_python': 'fixture-python', 'qwen_benchmark_status': 'not-requested'})
            self.assertTrue(manifest.is_file())
            self.assertTrue(sums.is_file())
            self.assertTrue(receipt.is_file())
            payload = __import__('json').loads(manifest.read_text(encoding='utf-8'))
            self.assertIn('models/fixture.bin', payload['files'])


    def test_online_acquisition_environment_disables_symlink_cache_for_windows_safe_archive(self):
        tool_path = ROOT / 'tools' / 'setup_local_tts_foundation.py'
        spec = importlib.util.spec_from_file_location('setup_local_tts_foundation_symlink_fixture', tool_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        env = module.online_acquisition_env()
        self.assertEqual(env['HF_HUB_DISABLE_SYMLINKS'], '1')
        self.assertEqual(env['HF_HUB_DISABLE_SYMLINKS_WARNING'], '1')

    def test_model_acquisition_uses_persistent_resource_staging_for_resume(self):
        text = (ROOT / 'tools' / 'setup_local_tts_foundation.py').read_text(encoding='utf-8')
        self.assertIn("staging_root = resource_root / '_staging' / ('hf-' + safe)", text)
        self.assertIn("print(f'PERSISTENT STAGING: {repo_id} -> {staging_root}'", text)
        self.assertNotIn("TemporaryDirectory(prefix=f'kr-b2a-hf-{safe}-'", text)


if __name__ == '__main__':
    unittest.main()
