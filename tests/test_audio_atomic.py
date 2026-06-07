import tempfile
import unittest
from pathlib import Path
from kr_book_to_audio.audio import synthesize_parts
from helpers import fake_save, fake_validate, make_prepared_job

class AudioAtomicTests(unittest.TestCase):
    def test_atomic_partial_is_renamed_only_after_validation(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            report = synthesize_parts(job, voice='voice', save_func=fake_save, validator=fake_validate, gap_seconds=0, require_preview_approval=False)
            self.assertFalse(report['failures'])
            self.assertTrue((job.parts_audio / 'part-0001.mp3').exists())
            self.assertFalse((job.parts_audio / 'part-0001.partial.mp3').exists())

if __name__ == '__main__': unittest.main()
