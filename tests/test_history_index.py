import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from helpers import make_prepared_job
from kr_book_to_audio.config import execution_history_path, local_work_root
from kr_book_to_audio.history import display_status, format_last_active, list_recent_jobs, list_resumable_jobs, prune_invalid_history, read_history, rebuild_history, remove_from_history, write_history


class HistoryIndexTests(unittest.TestCase):
    def test_recent_history_is_written_and_remove_does_not_delete_job(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'KR_B2A_APP_ROOT': str(Path(td) / 'app'), 'KR_B2A_HISTORY_SYNC': '1'}):
            job = make_prepared_job(Path(td))
            items = list_recent_jobs()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]['job_root'], str(job.root))
            remove_from_history(items[0]['job_id'])
            self.assertEqual(list_recent_jobs(), [])
            self.assertTrue(job.manifest.exists())

    def test_history_rebuild_after_malformed_json(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'KR_B2A_APP_ROOT': str(Path(td) / 'app'), 'KR_B2A_HISTORY_SYNC': '1'}):
            app = Path(td) / 'app'; app.mkdir()
            source = Path(td) / 'source.txt'; source.write_text('中文内容。', encoding='utf-8')
            from kr_book_to_audio.pipeline import prepare_job
            job = prepare_job(source, work_root=local_work_root(), export_root=Path(td) / 'exports')
            execution_history_path().write_text('{broken', encoding='utf-8')
            rebuilt = rebuild_history(local_work_root())
            self.assertEqual(len(rebuilt['jobs']), 1)
            self.assertEqual(rebuilt['jobs'][0]['job_root'], str(job.root))

    def test_recent_jobs_are_sorted_by_updated_time(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'KR_B2A_APP_ROOT': str(Path(td) / 'app'), 'KR_B2A_HISTORY_SYNC': '1'}):
            roots = []
            for name in ('old', 'new'):
                root = Path(td) / name
                (root / '_work').mkdir(parents=True)
                (root / '_work' / 'job_manifest.json').write_text('{}', encoding='utf-8')
                roots.append(root)
            write_history({'jobs': [
                {'job_id': 'old', 'title': 'old', 'job_root': str(roots[0]), 'updated_utc': '2020-01-01T00:00:00Z'},
                {'job_id': 'new', 'title': 'new', 'job_root': str(roots[1]), 'updated_utc': '2026-01-01T00:00:00Z'},
            ]})
            self.assertEqual([item['job_id'] for item in list_recent_jobs()], ['new', 'old'])

    def test_invalid_fixture_history_is_pruned(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'KR_B2A_APP_ROOT': str(Path(td) / 'app'), 'KR_B2A_HISTORY_SYNC': '1'}):
            missing = Path(td) / 'deleted-test-fixture'
            write_history({'jobs': [{'job_id': 'fixture', 'title': 'source', 'job_root': str(missing), 'updated_utc': '2026-01-01T00:00:00Z'}]})
            report = prune_invalid_history()
            self.assertEqual(report, {'removed': 1, 'remaining': 0})
            self.assertEqual(list_recent_jobs(), [])

    def test_resumable_view_excludes_completed_tasks(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'KR_B2A_APP_ROOT': str(Path(td) / 'app'), 'KR_B2A_HISTORY_SYNC': '1'}):
            roots = []
            for name in ('complete', 'resume'):
                root = Path(td) / name
                (root / '_work').mkdir(parents=True)
                (root / '_work' / 'job_manifest.json').write_text('{}', encoding='utf-8')
                roots.append(root)
            write_history({'jobs': [
                {'job_id': 'complete', 'title': 'done', 'job_root': str(roots[0]), 'total_parts': 3, 'completed_parts': 3, 'resumable': False},
                {'job_id': 'resume', 'title': 'book', 'job_root': str(roots[1]), 'total_parts': 34, 'completed_parts': 16, 'resumable': True},
            ]})
            self.assertEqual([item['job_id'] for item in list_resumable_jobs()], ['resume'])
            self.assertEqual(display_status(list_resumable_jobs()[0]), 'Ready to resume')

    def test_last_active_is_compact_local_time(self):
        rendered = format_last_active('2026-06-08T06:46:12.020013+00:00')
        self.assertRegex(rendered, r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$')

    def test_temp_fixture_job_does_not_pollute_default_history(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'KR_B2A_APP_ROOT': str(Path(td) / 'app')}, clear=False):
            os.environ.pop('KR_B2A_HISTORY_SYNC', None)
            job = make_prepared_job(Path(td))
            self.assertTrue(job.manifest.exists())
            self.assertEqual(read_history().get('jobs'), [])


if __name__ == '__main__': unittest.main()
