import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import approve_fake_audio, fake_validate, make_prepared_job
from kr_book_to_audio.export import cleaned_text_export_path, export_manifest_path, finalize_export, legacy_export_manifest_path, legacy_export_parts_dir


class FlatExportV240Tests(unittest.TestCase):
    def test_user_export_root_is_flat_mp3_plus_cleaned_txt_only(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            approve_fake_audio(job)
            finalize_export(job, validator=fake_validate)
            children = list(job.export.iterdir())
            self.assertFalse([path for path in children if path.is_dir()])
            self.assertTrue((job.export / 'part-0001.mp3').is_file())
            self.assertTrue(cleaned_text_export_path(job).is_file())
            self.assertFalse(legacy_export_manifest_path(job).exists())
            self.assertTrue(export_manifest_path(job).is_file())
            self.assertEqual(export_manifest_path(job).parent, job.work)

    def test_legacy_parts_folder_is_flattened_after_verification(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            approve_fake_audio(job)
            legacy = legacy_export_parts_dir(job)
            legacy.mkdir(parents=True)
            shutil.copyfile(job.parts_audio / 'part-0001.mp3', legacy / 'part-0001.mp3')
            legacy_export_manifest_path(job).write_text(json.dumps({'legacy': True}), encoding='utf-8')
            finalize_export(job, validator=fake_validate)
            self.assertFalse(legacy.exists())
            self.assertFalse(legacy_export_manifest_path(job).exists())
            self.assertTrue((job.export / 'part-0001.mp3').is_file())

    def test_conflicting_existing_flat_mp3_blocks_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            approve_fake_audio(job)
            job.export.mkdir(parents=True)
            (job.export / 'part-0001.mp3').write_bytes(b'conflict' * 1000)
            with self.assertRaisesRegex(RuntimeError, 'will not be overwritten'):
                finalize_export(job, validator=fake_validate)


if __name__ == '__main__':
    unittest.main()
