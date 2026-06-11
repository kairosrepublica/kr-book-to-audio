import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import kr_book_to_audio.local_ocr_setup as setup
from kr_book_to_audio.local_ocr import LocalOCRFoundation


def _touch_ready_runtime(foundation: LocalOCRFoundation) -> None:
    for path in (
        foundation.paddle_python,
        foundation.paddle_worker,
        foundation.pdftoppm,
        foundation.pdftotext,
        foundation.pdfinfo,
        foundation.pdffonts,
        foundation.tesseract,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x')
    for profile in ('server', 'mobile'):
        for model in foundation.paddle_model_paths(profile):
            model.mkdir(parents=True, exist_ok=True)
            (model / 'model.pdmodel').write_bytes(b'x')
    for profile in ('fast', 'best'):
        tessdata = foundation.tessdata(profile)
        tessdata.mkdir(parents=True, exist_ok=True)
        for name in ('eng.traineddata', 'chi_sim.traineddata', 'chi_tra.traineddata', 'osd.traineddata'):
            (tessdata / name).write_bytes(b'x')
    foundation.manifest.parent.mkdir(parents=True, exist_ok=True)
    foundation.manifest.write_text('{"entries": {}}', encoding='utf-8')


class _FakeHTTPResponse:
    def __init__(self, body: bytes, headers: dict[str, str], status: int = 200):
        self._body = io.BytesIO(body)
        self.headers = headers
        self.status = status
    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): return False
    def read(self, size=-1): return self._body.read(size)


class LocalOCRFoundationV250Tests(unittest.TestCase):
    def test_governed_archive_and_runtime_copy_are_separate(self):
        foundation = LocalOCRFoundation(Path('C:/dev/KR_OCR_Local'), Path('D:/Resource/KR_OCR_Offline_Resources'))
        self.assertNotEqual(foundation.root, foundation.resource_root)
        self.assertEqual(foundation.paddle_model_paths('server')[0].name, 'PP-OCRv5_server_det')
        self.assertEqual(foundation.paddle_model_paths('mobile')[1].name, 'PP-OCRv5_mobile_rec')
        self.assertEqual(foundation.tessdata('fast').name, 'fast')
        self.assertEqual(foundation.tessdata('best').name, 'best')

    def test_online_acquisition_clears_offline_only_variables_and_keeps_no_symlink_mode(self):
        with patch.dict(os.environ, {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1'}, clear=False):
            env = setup.online_env()
        self.assertNotIn('HF_HUB_OFFLINE', env)
        self.assertNotIn('TRANSFORMERS_OFFLINE', env)
        self.assertNotIn('HF_DATASETS_OFFLINE', env)
        self.assertEqual(env['HF_HUB_DISABLE_SYMLINKS'], '1')

    def test_normal_ocr_worker_environment_is_offline_only(self):
        foundation = LocalOCRFoundation(Path('C:/dev/KR_OCR_Local'), Path('D:/Resource/KR_OCR_Offline_Resources'))
        env = foundation.offline_env()
        self.assertEqual(env['HF_HUB_OFFLINE'], '1')
        self.assertEqual(env['TRANSFORMERS_OFFLINE'], '1')
        self.assertEqual(env['HF_DATASETS_OFFLINE'], '1')

    def test_foundation_ready_report_requires_archive_manifest_and_deployed_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            foundation = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            self.assertFalse(any(foundation.ready_report().values()))

    def test_archive_reuse_requires_matching_manifest_hash(self):
        with tempfile.TemporaryDirectory() as td:
            foundation = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            file = foundation.resource_root / 'tools' / 'poppler' / 'bin' / 'pdftoppm.exe'
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b'original')
            foundation.manifest.parent.mkdir(parents=True, exist_ok=True)
            import hashlib
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            foundation.manifest.write_text(json.dumps({'entries': {'tools/poppler/bin/pdftoppm.exe': digest}}), encoding='utf-8')
            self.assertTrue(setup.archived_file_verified(foundation, file))
            file.write_bytes(b'corrupt')
            self.assertFalse(setup.archived_file_verified(foundation, file))

    def test_frozen_portable_repair_uses_external_system_python_for_bootstrap(self):
        with patch.object(setup.sys, 'frozen', True, create=True), patch.object(setup.shutil, 'which', side_effect=lambda name: 'C:/Python313/python.exe' if name == 'python.exe' else None):
            self.assertEqual(setup.bootstrap_python_command(), ['C:/Python313/python.exe'])

    def test_managed_python_candidates_reject_internal_template_and_continue_after_bad_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'runtime'
            foundation = LocalOCRFoundation(root, Path(td) / 'archive')
            bin_dir = root / 'runtimes' / 'uv-python-bin'
            install_dir = root / 'runtimes' / 'uv-python'
            broken = bin_dir / 'python3.12.exe'
            valid = install_dir / 'cpython-3.12.13-windows-x86_64-none' / 'python.exe'
            internal = install_dir / 'cpython-3.12.13-windows-x86_64-none' / 'Lib' / 'venv' / 'scripts' / 'nt' / 'python.exe'
            for path in (broken, valid, internal):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture')
            candidates = setup.deterministic_managed_python_candidates(foundation, uv_bin_dir=bin_dir, uv_install_dir=install_dir, platform_name='nt')
            self.assertNotIn(internal, candidates)
            def fake_version(path):
                if path == broken:
                    raise RuntimeError('broken shim')
                if path == valid:
                    return (3, 12, 13)
                raise RuntimeError(f'unexpected candidate: {path}')
            self.assertEqual(setup.select_compatible_python(candidates, version_reader=fake_version), valid)

    def test_managed_python_locator_returns_consolidated_diagnostics_when_no_candidate_works(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / 'missing-python.exe'
            with self.assertRaisesRegex(RuntimeError, 'Candidate diagnostics'):
                setup.select_compatible_python([missing], version_reader=lambda path: (3, 12, 13))

    def test_tesseract_download_uses_second_mirror_after_first_source_403(self):
        with tempfile.TemporaryDirectory() as td:
            destination = Path(td) / 'tesseract.exe'
            calls = []
            def fake_download(url, target):
                calls.append(url)
                if len(calls) == 1:
                    raise HTTPError(url, 403, 'Forbidden', None, None)
                target.write_bytes(b'MZ' + b'x' * (1024 * 1024))
                return target
            sources = (('blocked', 'https://blocked.invalid/tesseract.exe'), ('fallback', 'https://fallback.invalid/tesseract.exe'))
            with patch.object(setup, 'download_with_resume', side_effect=fake_download):
                actual = setup.download_from_sources_with_resume(sources, destination, validator=lambda path: setup.validate_windows_pe_download(path, label='fixture'))
            self.assertEqual(actual, destination)
            self.assertEqual(calls, [sources[0][1], sources[1][1]])

    def test_tesseract_download_reports_all_failed_mirrors(self):
        with tempfile.TemporaryDirectory() as td:
            destination = Path(td) / 'tesseract.exe'
            sources = (('one', 'https://one.invalid/tesseract.exe'), ('two', 'https://two.invalid/tesseract.exe'))
            with patch.object(setup, 'download_with_resume', side_effect=RuntimeError('network down')):
                with self.assertRaisesRegex(RuntimeError, 'one: RuntimeError: network down'):
                    setup.download_from_sources_with_resume(sources, destination)

    def test_tesseract_download_rejects_html_payload(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'download.exe'
            path.write_bytes(b'<html>' + b'x' * (1024 * 1024))
            with self.assertRaisesRegex(RuntimeError, 'not a Windows PE executable'):
                setup.validate_windows_pe_download(path, label='fixture')

    def test_truncated_http_response_preserves_partial_and_does_not_promote(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / 'archive'
            destination = base / 'bundles' / 'candidate_one' / 'downloads' / 'model.tar'
            url = 'https://fixture.invalid/model.tar'
            staged = setup._persistent_download_target(url, destination)
            response = _FakeHTTPResponse(b'abc', {'Content-Length': '10'}, status=200)
            with patch.object(setup, 'urlopen', return_value=response):
                with self.assertRaisesRegex(RuntimeError, 'Download truncated'):
                    setup.online_download_with_resume(url, destination)
            self.assertFalse(staged.exists())
            self.assertTrue(staged.with_suffix(staged.suffix + '.part').is_file())
            self.assertFalse(destination.exists())

    def test_rerun_reuses_persistent_download_across_fresh_candidate_bundles(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / 'archive'
            url = 'https://fixture.invalid/model.tar'
            first = base / 'bundles' / 'candidate_one' / 'downloads' / 'model.tar'
            second = base / 'bundles' / 'candidate_two' / 'downloads' / 'model.tar'
            with patch.object(setup, 'urlopen', return_value=_FakeHTTPResponse(b'abcdef', {'Content-Length': '6'}, status=200)):
                setup.online_download_with_resume(url, first)
            with patch.object(setup, 'urlopen', side_effect=AssertionError('network must not run on verified rerun')):
                setup.online_download_with_resume(url, second)
            self.assertEqual(first.read_bytes(), b'abcdef')
            self.assertEqual(second.read_bytes(), b'abcdef')
            self.assertEqual(setup._persistent_download_target(url, first), setup._persistent_download_target(url, second))


class AppendOnlyDeploymentTests(unittest.TestCase):
    def test_candidate_structure_creates_containers_but_not_append_only_runtime_leaf(self):
        with tempfile.TemporaryDirectory() as td:
            base = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            setup.ensure_base_structure(base)
            context = setup.create_context(base, bundle_id='leaf-contract')
            setup.ensure_candidate_structure(context.candidate)
            self.assertTrue((context.candidate.resource_root / 'runtimes').is_dir())
            self.assertFalse((context.candidate.resource_root / 'runtimes' / 'uv-python').exists())
            self.assertTrue((context.candidate.resource_root / 'wheelhouse').is_dir())
            self.assertFalse((context.candidate.resource_root / 'tools' / 'poppler').exists())
            self.assertFalse((context.candidate.resource_root / 'tools' / 'tesseract').exists())

    def test_fresh_bundle_python_archive_lifecycle_does_not_collide_with_candidate_structure(self):
        with tempfile.TemporaryDirectory() as td:
            base = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            setup.ensure_base_structure(base)
            context = setup.create_context(base, bundle_id='fresh-runtime-archive')
            foundation = context.candidate
            setup.ensure_candidate_structure(foundation)
            runtime = foundation.root / 'runtimes' / 'uv-python'
            managed = runtime / 'cpython-3.12.13-windows-x86_64-none' / 'python.exe'
            managed.parent.mkdir(parents=True, exist_ok=True)
            managed.write_bytes(b'fixture-python')
            env_python = setup.python_in(foundation.root / 'envs' / 'paddleocr')

            def fake_run(args, **kwargs):
                if '-m' in args and 'venv' in args:
                    env_python.parent.mkdir(parents=True, exist_ok=True)
                    env_python.write_bytes(b'fixture-venv-python')
                return subprocess.CompletedProcess(args=args, returncode=0, stdout='', stderr='')

            with patch.object(setup, 'locate_managed_python', return_value=managed), \
                 patch.object(setup, 'run', side_effect=fake_run), \
                 patch.object(setup, 'python_version', return_value=(3, 12, 13)):
                selected = setup.ensure_python(foundation, Path('uv.exe'))
            self.assertEqual(selected, env_python)
            archived = foundation.resource_root / 'runtimes' / 'uv-python' / 'cpython-3.12.13-windows-x86_64-none' / 'python.exe'
            self.assertTrue(archived.is_file())

    def test_full_fresh_bundle_execute_lifecycle_and_rerun_are_green_without_touching_prior_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            base = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            report_one = Path(td) / 'report-one.json'
            report_two = Path(td) / 'report-two.json'

            def touch_runtime_files(foundation):
                for path in (foundation.pdftoppm, foundation.pdftotext, foundation.pdfinfo, foundation.pdffonts, foundation.tesseract):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b'fixture')
                for profile in ('fast', 'best'):
                    tessdata = foundation.tessdata(profile)
                    tessdata.mkdir(parents=True, exist_ok=True)
                    for filename in ('eng.traineddata', 'chi_sim.traineddata', 'chi_tra.traineddata', 'osd.traineddata'):
                        (tessdata / filename).write_bytes(b'fixture')
                for profile in ('server', 'mobile'):
                    for model in foundation.paddle_model_paths(profile):
                        model.mkdir(parents=True, exist_ok=True)
                        (model / 'model.pdmodel').write_bytes(b'fixture')
                foundation.paddle_worker.parent.mkdir(parents=True, exist_ok=True)
                foundation.paddle_worker.write_text('fixture', encoding='utf-8')

            def fake_locate(foundation, uv):
                managed = foundation.root / 'runtimes' / 'uv-python' / 'cpython-3.12.13-windows-x86_64-none' / 'python.exe'
                managed.parent.mkdir(parents=True, exist_ok=True)
                managed.write_bytes(b'fixture-managed-python')
                return managed

            def fake_run(args, **kwargs):
                args = [str(item) for item in args]
                if '-m' in args and 'venv' in args:
                    target = Path(args[-1])
                    python = setup.python_in(target)
                    python.parent.mkdir(parents=True, exist_ok=True)
                    python.write_bytes(b'fixture-venv-python')
                return subprocess.CompletedProcess(args=args, returncode=0, stdout='', stderr='')

            def fake_wheelhouse(foundation, py):
                wheel = foundation.resource_root / 'wheelhouse' / 'paddleocr_py312_win_amd64' / 'fixture.whl'
                wheel.parent.mkdir(parents=True, exist_ok=True)
                wheel.write_bytes(b'fixture')
                return wheel.parent

            def fake_poppler(foundation):
                touch_runtime_files(foundation)

            def fake_tesseract(foundation):
                touch_runtime_files(foundation)

            def fake_tessdata(foundation):
                touch_runtime_files(foundation)

            def fake_models(foundation):
                touch_runtime_files(foundation)

            def fake_worker(foundation):
                touch_runtime_files(foundation)

            no_op = lambda *args, **kwargs: None
            with patch.object(setup, 'local_ocr_foundation', return_value=base), \
                 patch.object(setup, 'require_windows_target', no_op), \
                 patch.object(setup, 'ensure_space', no_op), \
                 patch.object(setup, 'seed_candidate_archive', return_value=[]), \
                 patch.object(setup, 'ensure_uv', return_value=Path('uv.exe')), \
                 patch.object(setup, 'locate_managed_python', side_effect=fake_locate), \
                 patch.object(setup, 'run', side_effect=fake_run), \
                 patch.object(setup, 'python_version', return_value=(3, 12, 13)), \
                 patch.object(setup, 'ensure_wheelhouse', side_effect=fake_wheelhouse), \
                 patch.object(setup, 'ensure_poppler', side_effect=fake_poppler), \
                 patch.object(setup, 'ensure_tesseract', side_effect=fake_tesseract), \
                 patch.object(setup, 'ensure_tessdata', side_effect=fake_tessdata), \
                 patch.object(setup, 'ensure_paddle_models', side_effect=fake_models), \
                 patch.object(setup, 'ensure_worker', side_effect=fake_worker), \
                 patch.object(setup, 'tesseract_probe', no_op), \
                 patch.object(setup, 'paddle_import_probe', no_op):
                first = setup.execute(report_path=report_one, activate=True)
                first_bundle = first['bundle_id']
                first_runtime = base.root / 'deployments' / first_bundle
                first_archive = base.resource_root / 'bundles' / first_bundle
                self.assertTrue(first['ok'])
                self.assertTrue(first['activated'])
                self.assertTrue((first_archive / 'runtimes' / 'uv-python').is_dir())
                self.assertEqual(base.runtime_root, first_runtime)
                self.assertEqual(base.archive_root, first_archive)

                second = setup.execute(report_path=report_two, activate=True)
                second_bundle = second['bundle_id']
                self.assertTrue(second['ok'])
                self.assertTrue(second['activated'])
                self.assertNotEqual(first_bundle, second_bundle)
                self.assertTrue(first_runtime.is_dir())
                self.assertTrue(first_archive.is_dir())
                self.assertEqual(base.runtime_root, base.root / 'deployments' / second_bundle)
                self.assertEqual(base.archive_root, base.resource_root / 'bundles' / second_bundle)

    def test_create_context_never_touches_existing_legacy_tree(self):
        with tempfile.TemporaryDirectory() as td:
            base = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            setup.ensure_base_structure(base)
            legacy = base.root / 'models' / 'legacy-locked'
            legacy.mkdir(parents=True)
            sentinel = legacy / 'KEEP.txt'
            sentinel.write_text('keep', encoding='utf-8')
            context = setup.create_context(base, bundle_id='bundle_a')
            setup.ensure_candidate_structure(context.candidate)
            self.assertTrue(sentinel.is_file())
            self.assertTrue((base.root / 'deployments' / 'bundle_a').is_dir())
            self.assertTrue((base.resource_root / 'bundles' / 'bundle_a').is_dir())

    def test_activation_is_pointer_only_and_resolves_versioned_runtime_and_archive(self):
        with tempfile.TemporaryDirectory() as td:
            base = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            setup.ensure_base_structure(base)
            context = setup.create_context(base, bundle_id='bundle_green')
            setup.ensure_candidate_structure(context.candidate)
            _touch_ready_runtime(context.candidate)
            setup.activate_context(context)
            self.assertEqual(base.runtime_root, context.candidate.root)
            self.assertEqual(base.archive_root, context.candidate.resource_root)
            payload = json.loads(base.active_deployment_pointer.read_text(encoding='utf-8'))
            self.assertEqual(payload['active_bundle'], 'bundle_green')
            self.assertEqual(payload['active_archive_bundle'], 'bundle_green')

    def test_activation_uses_one_authoritative_atomic_pointer_write(self):
        with tempfile.TemporaryDirectory() as td:
            base = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            setup.ensure_base_structure(base)
            context = setup.create_context(base, bundle_id='bundle_green')
            setup.ensure_candidate_structure(context.candidate)
            _touch_ready_runtime(context.candidate)
            calls = []
            with patch.object(setup, '_write_pointer', side_effect=lambda path, payload: calls.append(path)):
                setup.activate_context(context)
            self.assertEqual(calls, [base.active_deployment_pointer])

    def test_activation_rejects_incomplete_candidate_and_preserves_previous_pointer(self):
        with tempfile.TemporaryDirectory() as td:
            base = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            setup.ensure_base_structure(base)
            base.active_deployment_pointer.parent.mkdir(parents=True, exist_ok=True)
            base.active_deployment_pointer.write_text('{"active_bundle": "old"}', encoding='utf-8')
            context = setup.create_context(base, bundle_id='bundle_bad')
            with self.assertRaisesRegex(RuntimeError, 'Cannot activate incomplete'):
                setup.activate_context(context)
            self.assertEqual(json.loads(base.active_deployment_pointer.read_text(encoding='utf-8'))['active_bundle'], 'old')

    def test_locked_historical_model_tree_does_not_block_new_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            base = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            setup.ensure_base_structure(base)
            historical = base.root / 'models' / 'paddleocr' / 'PP-OCRv5_server_det'
            historical.mkdir(parents=True)
            sentinel = historical / 'LOCKED_KEEP.txt'
            sentinel.write_text('keep', encoding='utf-8')
            context = setup.create_context(base, bundle_id='new_bundle')
            setup.ensure_candidate_structure(context.candidate)
            self.assertTrue(sentinel.is_file())
            self.assertNotEqual(context.candidate.root, base.root)
            self.assertTrue((context.candidate.root / 'models' / 'paddleocr').is_dir())

    def test_repeated_candidate_creation_is_isolated_and_append_only(self):
        with tempfile.TemporaryDirectory() as td:
            base = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            setup.ensure_base_structure(base)
            first = setup.create_context(base, bundle_id='bundle_one')
            setup.ensure_candidate_structure(first.candidate)
            marker = first.candidate.root / 'KEEP.txt'
            marker.write_text('first', encoding='utf-8')
            second = setup.create_context(base, bundle_id='bundle_two')
            setup.ensure_candidate_structure(second.candidate)
            self.assertTrue(marker.is_file())
            self.assertNotEqual(first.candidate.root, second.candidate.root)
            self.assertTrue(first.candidate.resource_root.is_dir())
            self.assertTrue(second.candidate.resource_root.is_dir())

    def test_activation_pointer_write_failure_preserves_previous_pointer(self):
        with tempfile.TemporaryDirectory() as td:
            base = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            setup.ensure_base_structure(base)
            base.active_deployment_pointer.parent.mkdir(parents=True, exist_ok=True)
            base.active_deployment_pointer.write_text('{"active_bundle": "old"}', encoding='utf-8')
            context = setup.create_context(base, bundle_id='bundle_green')
            setup.ensure_candidate_structure(context.candidate)
            _touch_ready_runtime(context.candidate)
            with patch.object(setup, '_write_pointer', side_effect=PermissionError('pointer locked')):
                with self.assertRaisesRegex(PermissionError, 'pointer locked'):
                    setup.activate_context(context)
            self.assertEqual(json.loads(base.active_deployment_pointer.read_text(encoding='utf-8'))['active_bundle'], 'old')

    def test_manual_cleanup_report_lists_inactive_bundles_without_deleting(self):
        with tempfile.TemporaryDirectory() as td:
            base = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            setup.ensure_base_structure(base)
            for bundle in ('old_a', 'old_b'):
                (base.root / 'deployments' / bundle).mkdir()
                (base.resource_root / 'bundles' / bundle).mkdir()
            report_path = setup.write_manual_cleanup_report(base)
            payload = json.loads(report_path.read_text(encoding='utf-8'))
            self.assertEqual(payload['policy'], 'manual cleanup candidates only; no automatic deletion')
            self.assertEqual(payload['inactive_runtime_deployments'], ['old_a', 'old_b'])
            self.assertTrue((base.root / 'deployments' / 'old_a').is_dir())

    def test_setup_module_has_no_destructive_owner_tree_operations(self):
        source = Path(setup.__file__).read_text(encoding='utf-8')
        self.assertNotIn('shutil.rmtree(', source)
        self.assertNotIn('shutil.move(', source)
        self.assertNotIn('quarantine_archive_path', source)
        self.assertNotIn('_quarantine_local_runtime_unit', source)

    def test_seed_candidate_archive_copies_only_verified_known_tree(self):
        with tempfile.TemporaryDirectory() as td:
            base = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            setup.ensure_base_structure(base)
            source = base.archive_root / 'models' / 'paddleocr'
            source.mkdir(parents=True)
            model = source / 'PP-OCRv5_mobile_det' / 'model.pdmodel'
            model.parent.mkdir(parents=True)
            model.write_bytes(b'model')
            base.manifest.parent.mkdir(parents=True)
            import hashlib
            digest = hashlib.sha256(model.read_bytes()).hexdigest()
            base.manifest.write_text(json.dumps({'entries': {'models/paddleocr/PP-OCRv5_mobile_det/model.pdmodel': digest}}), encoding='utf-8')
            context = setup.create_context(base, bundle_id='seeded')
            seeded = setup.seed_candidate_archive(context)
            self.assertIn('models/paddleocr', seeded)
            self.assertTrue((context.candidate.resource_root / 'models/paddleocr/PP-OCRv5_mobile_det/model.pdmodel').is_file())
            self.assertTrue(model.is_file())

    def test_execute_collects_independent_failures_and_never_activates_failed_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            base = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            report_path = Path(td) / 'report.json'
            called = []
            def mark(name, error=None):
                def action(*args, **kwargs):
                    called.append(name)
                    if error:
                        raise error
                return action
            no_op = lambda *args, **kwargs: None
            with patch.object(setup, 'local_ocr_foundation', return_value=base), \
                 patch.object(setup, 'require_windows_target', no_op), \
                 patch.object(setup, 'ensure_space', no_op), \
                 patch.object(setup, 'seed_candidate_archive', return_value=[]), \
                 patch.object(setup, 'ensure_uv', return_value=Path('uv.exe')), \
                 patch.object(setup, 'ensure_python', return_value=Path('python.exe')), \
                 patch.object(setup, 'ensure_wheelhouse', mark('wheelhouse')), \
                 patch.object(setup, 'ensure_poppler', mark('poppler', PermissionError('locked'))), \
                 patch.object(setup, 'ensure_tesseract', mark('tesseract', RuntimeError('mirror down'))), \
                 patch.object(setup, 'ensure_tessdata', mark('tessdata')), \
                 patch.object(setup, 'ensure_paddle_models', mark('models')), \
                 patch.object(setup, 'ensure_worker', mark('worker')), \
                 patch.object(setup, 'manifest', no_op):
                report = setup.execute(report_path=report_path, activate=True)
            self.assertFalse(report['ok'])
            self.assertFalse(report['activated'])
            self.assertFalse(base.active_deployment_pointer.exists())
            self.assertIn('tessdata', called)
            self.assertIn('models', called)
            self.assertIn('worker', called)
            self.assertEqual([item['stage'] for item in report['failures']], ['Archive and deploy Poppler', 'Archive and deploy Tesseract'])
            self.assertTrue(report_path.is_file())

    def test_python_m_entrypoint_executes_self_test_and_writes_report(self):
        with tempfile.TemporaryDirectory() as td:
            report_path = Path(td) / 'entrypoint-self-test-report.json'
            repo_root = Path(__file__).resolve().parents[1]
            env = os.environ.copy()
            env['PYTHONPATH'] = str(repo_root / 'src') + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
            result = subprocess.run([sys.executable, '-m', 'kr_book_to_audio.local_ocr_setup', '--self-test-only', '--report', str(report_path)], cwd=repo_root, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('OCR FOUNDATION SELF-TEST PASS', result.stdout)
            report = json.loads(report_path.read_text(encoding='utf-8'))
            self.assertTrue(report['ok'])
            self.assertTrue(report['entrypoint'])
            self.assertEqual(report['mode'], 'self-test-only')

    def test_setup_self_test_passes_without_mutation(self):
        self.assertEqual(setup.self_test(), 0)

    def test_paddle_runtime_pin_avoids_paddlepaddle_330_onednn_regression(self):
        self.assertEqual(setup.PADDLE_PACKAGE, 'paddlepaddle==3.2.2')

    def test_seeded_old_wheelhouse_requires_pinned_paddlepaddle_322_acquisition(self):
        with tempfile.TemporaryDirectory() as td:
            wheelhouse = Path(td)
            (wheelhouse / 'paddlepaddle-3.3.0-cp312-cp312-win_amd64.whl').write_bytes(b'old')
            (wheelhouse / 'paddleocr-3.6.0-py3-none-any.whl').write_bytes(b'ocr')
            self.assertFalse(setup.wheelhouse_has_distribution(wheelhouse, 'paddlepaddle', '3.2.2'))
            (wheelhouse / 'paddlepaddle-3.2.2-cp312-cp312-win_amd64.whl').write_bytes(b'good')
            self.assertTrue(setup.wheelhouse_has_distribution(wheelhouse, 'paddlepaddle', '3.2.2'))

    def test_offline_runtime_disables_mkldnn_and_worker_passes_explicit_safe_cpu_options(self):
        with tempfile.TemporaryDirectory() as td:
            foundation = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            self.assertEqual(foundation.offline_env()['FLAGS_use_mkldnn'], '0')
        worker = setup.PADDLEOCR_WORKER_SCRIPT
        self.assertIn("os.environ['FLAGS_use_mkldnn'] = '0'", worker)
        self.assertIn('enable_mkldnn=False', worker)
        self.assertIn('cpu_threads=1', worker)

    def test_ensure_wheelhouse_repairs_seeded_old_tree_by_acquiring_pinned_322(self):
        with tempfile.TemporaryDirectory() as td:
            foundation = LocalOCRFoundation(Path(td) / 'runtime', Path(td) / 'archive')
            wheelhouse = foundation.resource_root / 'wheelhouse' / 'paddleocr_py312_win_amd64'
            wheelhouse.mkdir(parents=True)
            (wheelhouse / 'paddlepaddle-3.3.0-cp312-cp312-win_amd64.whl').write_bytes(b'old')
            (wheelhouse / 'paddleocr-3.6.0-py3-none-any.whl').write_bytes(b'ocr')
            calls = []
            def fake_run(args, **kwargs):
                calls.append([str(item) for item in args])
                if 'download' in args:
                    (wheelhouse / 'paddlepaddle-3.2.2-cp312-cp312-win_amd64.whl').write_bytes(b'good')
                return subprocess.CompletedProcess(args=args, returncode=0, stdout='', stderr='')
            with patch.object(setup, 'run', side_effect=fake_run):
                setup.ensure_wheelhouse(foundation, Path('python.exe'))
            self.assertTrue(any('download' in args for args in calls))
            self.assertTrue(setup.wheelhouse_has_distribution(wheelhouse, 'paddlepaddle', '3.2.2'))


if __name__ == '__main__':
    unittest.main()
