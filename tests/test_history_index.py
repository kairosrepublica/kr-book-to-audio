import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from helpers import make_prepared_job
from kr_book_to_audio.config import execution_history_path, local_work_root
from kr_book_to_audio.history import list_recent_jobs, read_history, rebuild_history, remove_from_history


class HistoryIndexTests(unittest.TestCase):
    def test_recent_history_is_written_and_remove_does_not_delete_job(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'KR_B2A_APP_ROOT': str(Path(td) / 'app')}):
            job = make_prepared_job(Path(td))
            items = list_recent_jobs()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]['job_root'], str(job.root))
            remove_from_history(items[0]['job_id'])
            self.assertEqual(list_recent_jobs(), [])
            self.assertTrue(job.manifest.exists())

    def test_history_rebuild_after_malformed_json(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'KR_B2A_APP_ROOT': str(Path(td) / 'app')}):
            app = Path(td) / 'app'; app.mkdir()
            source = Path(td) / 'source.txt'; source.write_text('中文内容。', encoding='utf-8')
            from kr_book_to_audio.pipeline import prepare_job
            job = prepare_job(source, work_root=local_work_root(), export_root=Path(td) / 'exports')
            execution_history_path().write_text('{broken', encoding='utf-8')
            rebuilt = rebuild_history(local_work_root())
            self.assertEqual(len(rebuilt['jobs']), 1)
            self.assertEqual(rebuilt['jobs'][0]['job_root'], str(job.root))

    def test_recent_jobs_are_sorted_by_updated_time(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'KR_B2A_APP_ROOT': str(Path(td) / 'app')}):
            from kr_book_to_audio.history import write_history
            write_history({'jobs': [
                {'job_id': 'old', 'title': 'old', 'updated_utc': '2020-01-01T00:00:00Z'},
                {'job_id': 'new', 'title': 'new', 'updated_utc': '2026-01-01T00:00:00Z'},
            ]})
            self.assertEqual([item['job_id'] for item in list_recent_jobs()], ['new', 'old'])


if __name__ == '__main__': unittest.main()
