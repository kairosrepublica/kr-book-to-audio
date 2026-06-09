import tempfile
import unittest
from pathlib import Path
from helpers import approve_fake_audio, fake_validate, make_prepared_job
from kr_book_to_audio.export import finalize_export

class QuietExportTests(unittest.TestCase):
    def test_receipt_reuse_bounds_validator_launches_for_many_parts(self):
        with tempfile.TemporaryDirectory() as td:
            job=make_prepared_job(Path(td),text=('中文内容。'*800),chunk_chars=100)
            approve_fake_audio(job)
            calls={'count':0}
            def counting(path):
                calls['count'] += 1
                return fake_validate(path)
            report=finalize_export(job,validator=counting)
            self.assertEqual(report['status'],'verified')
            # Trusted completion receipts allow export to remain hash-safe without re-running ffprobe per exported copy.
            self.assertLessEqual(calls['count'],1)
            self.assertEqual(report['receipt_reuse']['internal_parts'],report['expected_parts'])
