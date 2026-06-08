import json
import tempfile
import unittest
from pathlib import Path
from kr_book_to_audio.models import JobPaths
from kr_book_to_audio.utils import job_operation_lock, recover_stale_lock


class StaleLockTests(unittest.TestCase):
    def test_dead_pid_lock_is_removed_before_new_operation(self):
        with tempfile.TemporaryDirectory() as td:
            job = JobPaths.from_root(Path(td) / 'job'); job.ensure()
            lock = job.work / '.operation.lock'; lock.write_text(json.dumps({'pid': 987654, 'operation': 'old'}), encoding='utf-8')
            report = recover_stale_lock(job, process_checker=lambda pid: False)
            self.assertTrue(report['removed'])
            self.assertFalse(lock.exists())

    def test_live_pid_lock_remains_and_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            job = JobPaths.from_root(Path(td) / 'job'); job.ensure()
            lock = job.work / '.operation.lock'; lock.write_text(json.dumps({'pid': 123, 'operation': 'old'}), encoding='utf-8')
            report = recover_stale_lock(job, process_checker=lambda pid: True)
            self.assertEqual(report['reason'], 'live-process')
            self.assertTrue(lock.exists())

    def test_malformed_lock_is_not_deleted_automatically(self):
        with tempfile.TemporaryDirectory() as td:
            job = JobPaths.from_root(Path(td) / 'job'); job.ensure()
            lock = job.work / '.operation.lock'; lock.write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'malformed'):
                recover_stale_lock(job, process_checker=lambda pid: False)
            self.assertTrue(lock.exists())


if __name__ == '__main__': unittest.main()
