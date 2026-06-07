import tempfile
import unittest
from pathlib import Path
from kr_book_to_audio.models import JobPaths
from kr_book_to_audio.utils import job_operation_lock

class OperationLockTests(unittest.TestCase):
    def test_second_operation_is_rejected_while_job_is_locked(self):
        with tempfile.TemporaryDirectory() as td:
            job = JobPaths.from_root(Path(td) / 'job'); job.ensure()
            with job_operation_lock(job, 'first'):
                with self.assertRaisesRegex(RuntimeError, 'Job is busy'):
                    with job_operation_lock(job, 'second'):
                        pass
            self.assertFalse((job.work / '.operation.lock').exists())

if __name__ == '__main__': unittest.main()
