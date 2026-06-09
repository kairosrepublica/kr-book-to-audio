import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from zipfile import ZipFile

from helpers import make_prepared_job
from kr_book_to_audio.diagnostics import _sanitize_log_text, export_diagnostic_zip
from kr_book_to_audio.models import JobPaths


class DiagnosticsExportTests(unittest.TestCase):
    def test_diagnostic_zip_is_sanitized_and_easy_to_find(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            job = make_prepared_job(root)
            secret_text = 'BOOK_BODY_SHOULD_NOT_LEAK'
            job.proofread.write_text(secret_text, encoding='utf-8')
            job.run_log.write_text(f'Opened path: {job.root}\nOpened export: {job.export}\n', encoding='utf-8')
            output_root = root / 'diagnostics'
            archive_path = export_diagnostic_zip(job, root=output_root)
            self.assertEqual(archive_path.parent, output_root)
            with ZipFile(archive_path) as archive:
                self.assertEqual(sorted(archive.namelist()), ['diagnostics_summary.json', 'run.log'])
                run_log = archive.read('run.log').decode('utf-8')
                summary = json.loads(archive.read('diagnostics_summary.json'))
            self.assertNotIn(str(job.root), run_log)
            self.assertNotIn(str(job.export), run_log)
            self.assertIn('<JOB_ROOT>', run_log)
            self.assertNotIn(secret_text, json.dumps(summary, ensure_ascii=False))


    def test_specific_paths_are_redacted_before_parent_home_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            job = make_prepared_job(root)
            unrelated = root / 'unrelated' / 'note.txt'
            job.run_log.write_text(
                f'Opened path: {job.root}\n'
                f'Opened export: {job.export}\n'
                f'Opened unrelated: {unrelated}\n',
                encoding='utf-8',
            )
            output_root = root / 'diagnostics'
            with patch('kr_book_to_audio.diagnostics.Path.home', return_value=root):
                archive_path = export_diagnostic_zip(job, root=output_root)
            with ZipFile(archive_path) as archive:
                run_log = archive.read('run.log').decode('utf-8')
            self.assertIn('Opened path: <JOB_ROOT>', run_log)
            self.assertIn('Opened export: <EXPORT_ROOT>', run_log)
            self.assertIn('Opened unrelated: <USER_HOME>', run_log)



    def test_windows_style_nested_paths_use_specific_tokens(self):
        job_root = Path(r'D:\OwnerHome\AppData\Local\Temp\jobs\book')
        export_root = Path(r'D:\OwnerHome\AppData\Local\Temp\exports\book')
        job = JobPaths.from_root(job_root, export_root=export_root)
        with patch('kr_book_to_audio.diagnostics.Path.home', return_value=Path(r'D:\OwnerHome')):
            run_log = _sanitize_log_text(
                job,
                f'Opened path: {job.root}\nOpened export: {job.export}\n',
            )
        self.assertEqual(
            run_log,
            'Opened path: <JOB_ROOT>\nOpened export: <EXPORT_ROOT>\n',
        )



if __name__ == '__main__':
    unittest.main()
