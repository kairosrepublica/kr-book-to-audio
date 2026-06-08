import json
import tempfile
import unittest
from pathlib import Path

from helpers import approve_fake_audio, fake_save, fake_validate, make_prepared_job
from kr_book_to_audio.audio import approve_preview, synthesize_parts
from kr_book_to_audio.export import _atomic_copy, export_manifest_path, export_parts_dir, finalize_export, verify_export
from kr_book_to_audio.manifest import load_manifest, save_manifest


class ExportFinalizationTests(unittest.TestCase):
    def test_full_synthesis_triggers_verified_export_finalization(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td), text=('中文内容。' * 70), chunk_chars=100)
            synthesize_parts(job, voice='voice', start=1, end=1, require_preview_approval=False, save_func=fake_save, validator=fake_validate, gap_seconds=0)
            approve_preview(job, voice='voice', validator=fake_validate)
            result = synthesize_parts(job, voice='voice', save_func=fake_save, validator=fake_validate, gap_seconds=0)
            manifest = load_manifest(job)
            expected = len(manifest['parts'])
            self.assertEqual(result['export']['status'], 'verified')
            self.assertEqual(result['export']['exported_parts'], expected)
            self.assertEqual(len(list(export_parts_dir(job).glob('part-*.mp3'))), expected)
            self.assertTrue(export_manifest_path(job).exists())
            self.assertEqual(manifest['export']['status'], 'verified')

    def test_legacy_empty_export_is_repaired_without_regeneration(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td), text=('中文内容。' * 30), chunk_chars=100)
            approve_fake_audio(job)
            self.assertFalse(job.export.exists())
            result = finalize_export(job, validator=fake_validate)
            self.assertEqual(result['status'], 'verified')
            self.assertTrue(job.export.exists())
            self.assertTrue(export_manifest_path(job).exists())
            self.assertEqual(len(list(export_parts_dir(job).glob('part-*.mp3'))), len(load_manifest(job)['parts']))

    def test_missing_internal_part_blocks_export(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            approve_fake_audio(job)
            (job.parts_audio / 'part-0001.mp3').unlink()
            with self.assertRaisesRegex(RuntimeError, 'MP3 missing|missing or too small'):
                finalize_export(job, validator=fake_validate)
            self.assertFalse(export_manifest_path(job).exists())

    def test_empty_exported_mp3_blocks_verification_and_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            approve_fake_audio(job)
            finalize_export(job, validator=fake_validate)
            export_manifest_path(job).unlink()
            exported = export_parts_dir(job) / 'part-0001.mp3'
            exported.write_bytes(b'')
            with self.assertRaisesRegex(RuntimeError, 'missing or too small'):
                verify_export(job, validator=fake_validate)
            self.assertFalse(export_manifest_path(job).exists())

    def test_export_filenames_must_be_exact_and_continuous(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            approve_fake_audio(job)
            finalize_export(job, validator=fake_validate)
            (export_parts_dir(job) / 'part-9999.mp3').write_bytes(b'x' * 2048)
            with self.assertRaisesRegex(RuntimeError, 'Exported Part set mismatch'):
                verify_export(job, validator=fake_validate)

    def test_atomic_export_does_not_leave_partial_file_after_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'part-0001.mp3'
            destination = root / 'export' / 'part-0001.mp3'
            source.write_bytes(b'x' * 4096)
            def rejecting(_path: Path):
                raise RuntimeError('deliberate validator rejection')
            with self.assertRaisesRegex(RuntimeError, 'deliberate validator rejection'):
                _atomic_copy(source, destination, rejecting)
            self.assertFalse(destination.exists())
            self.assertFalse((destination.parent / 'part-0001.partial.mp3').exists())

    def test_export_manifest_is_written_only_after_verification_pass(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            approve_fake_audio(job)
            calls = {'count': 0}
            def fail_on_export(path: Path):
                calls['count'] += 1
                if export_parts_dir(job) in path.parents:
                    raise RuntimeError('export validator rejection')
                return fake_validate(path)
            with self.assertRaisesRegex(RuntimeError, 'export validator rejection'):
                finalize_export(job, validator=fail_on_export)
            self.assertFalse(export_manifest_path(job).exists())

    def test_retry_style_second_full_run_finalizes_after_missing_part_is_filled(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td), text=('中文内容。' * 70), chunk_chars=100)
            synthesize_parts(job, voice='voice', start=1, end=1, require_preview_approval=False, save_func=fake_save, validator=fake_validate, gap_seconds=0)
            approve_preview(job, voice='voice', validator=fake_validate)
            attempts = {'failed': False}
            def one_failure(text, out, **kwargs):
                if out.name == 'part-0002.partial.mp3' and not attempts['failed']:
                    attempts['failed'] = True
                    raise RuntimeError('deliberate part failure')
                fake_save(text, out, **kwargs)
            first = synthesize_parts(job, voice='voice', save_func=one_failure, validator=fake_validate, retries=0, gap_seconds=0)
            self.assertTrue(first['failures'])
            self.assertFalse(export_manifest_path(job).exists())
            second = synthesize_parts(job, voice='voice', save_func=fake_save, validator=fake_validate, gap_seconds=0)
            self.assertFalse(second['failures'])
            self.assertEqual(second['export']['status'], 'verified')


if __name__ == '__main__':
    unittest.main()
