import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from kr_book_to_audio.job_state import JobStateBusyError, JobStateIntegrityError, StaleStateRevisionError, acquire_lease, quick_check, release_lease, regenerate_snapshot
from kr_book_to_audio.manifest import load_manifest, save_manifest
from kr_book_to_audio.models import JobPaths


class JobStateEngineTests(unittest.TestCase):
    def _legacy_job(self, root: Path) -> JobPaths:
        job=JobPaths.from_root(root / '任务'); job.ensure()
        job.manifest.write_text(json.dumps({'schema_version':3,'job_id':'legacy','title':'书','paths':{'export_runtime_only':str(root/'export')}}),encoding='utf-8')
        return job

    def test_legacy_json_migrates_to_sqlite_and_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            job=self._legacy_job(Path(td))
            manifest=load_manifest(job)
            self.assertTrue(job.state_db.exists())
            self.assertTrue(job.legacy_manifest.exists())
            self.assertEqual(manifest['job_id'],'legacy')
            quick_check(job)

    def test_corrupt_snapshot_is_regenerated_from_sqlite(self):
        with tempfile.TemporaryDirectory() as td:
            job=self._legacy_job(Path(td)); load_manifest(job)
            job.manifest.write_text('{broken',encoding='utf-8')
            regenerated=regenerate_snapshot(job)
            self.assertEqual(json.loads(regenerated.read_text(encoding='utf-8'))['job_id'],'legacy')

    def test_stale_revision_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            job=self._legacy_job(Path(td)); first=load_manifest(job); second=load_manifest(job)
            first['title']='new'; save_manifest(job,first)
            second['title']='stale'
            with self.assertRaises(StaleStateRevisionError): save_manifest(job,second)


    def test_connect_closes_partial_handle_when_setup_fails(self):
        job=self._legacy_job(Path(tempfile.mkdtemp()))
        connection=MagicMock()
        connection.execute.side_effect=__import__('sqlite3').DatabaseError('file is not a database')
        with patch('kr_book_to_audio.job_state.sqlite3.connect', return_value=connection):
            with self.assertRaises(__import__('sqlite3').DatabaseError):
                load_manifest(job)
        connection.close.assert_called_once_with()

    def test_corrupt_sqlite_stops_safely(self):
        with tempfile.TemporaryDirectory() as td:
            job=self._legacy_job(Path(td)); load_manifest(job)
            job.state_db.write_bytes(b'not sqlite')
            with self.assertRaises(Exception): load_manifest(job)

    def test_second_live_lease_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            job=self._legacy_job(Path(td)); load_manifest(job)
            token=acquire_lease(job,operation='one',pid=111,process_checker=lambda _pid: True)
            try:
                with self.assertRaises(JobStateBusyError): acquire_lease(job,operation='two',pid=222,process_checker=lambda _pid: True)
            finally:
                release_lease(job,token)

    def test_snapshot_write_failure_does_not_corrupt_sqlite_authority(self):
        with tempfile.TemporaryDirectory() as td:
            job=self._legacy_job(Path(td)); manifest=load_manifest(job)
            manifest['title']='committed in sqlite'
            with patch('kr_book_to_audio.job_state.write_json', side_effect=PermissionError('snapshot locked')):
                save_manifest(job,manifest)
            self.assertEqual(load_manifest(job)['title'],'committed in sqlite')
            quick_check(job)

    def test_live_process_lease_is_not_stolen_even_with_old_heartbeat(self):
        with tempfile.TemporaryDirectory() as td:
            job=self._legacy_job(Path(td)); load_manifest(job)
            token=acquire_lease(job,operation='one',pid=111,process_checker=lambda _pid: True,stale_after_seconds=0)
            try:
                with self.assertRaises(JobStateBusyError):
                    acquire_lease(job,operation='two',pid=222,process_checker=lambda _pid: True,stale_after_seconds=0)
            finally:
                release_lease(job,token)
