import tempfile
import unittest
from pathlib import Path
from kr_book_to_audio.audio import synthesize_parts
from helpers import fake_save, fake_validate, make_prepared_job

class ProgressEventTests(unittest.TestCase):
    def test_preview_progress_includes_validating_and_done_percentages(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            events=[]
            synthesize_parts(job, voice='voice', save_func=fake_save, validator=fake_validate, gap_seconds=0, require_preview_approval=False, progress=events.append)
            states=[item['state'] for item in events]
            self.assertIn('validating', states)
            self.assertEqual([item for item in events if item['state']=='done'][-1]['estimated_percent'], 100)

if __name__ == '__main__': unittest.main()
