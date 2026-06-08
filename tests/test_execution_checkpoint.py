import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from helpers import fake_save, fake_validate, make_prepared_job
from kr_book_to_audio.audio import synthesize_parts
from kr_book_to_audio.manifest import load_manifest


class ExecutionCheckpointTests(unittest.TestCase):
    def test_successful_synthesis_clears_running_state_and_records_last_part(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'KR_B2A_APP_ROOT': str(Path(td) / 'app')}):
            job = make_prepared_job(Path(td))
            synthesize_parts(job, voice='voice', save_func=fake_save, validator=fake_validate, gap_seconds=0, require_preview_approval=False)
            execution = load_manifest(job)['execution']
            self.assertEqual(execution['status'], 'idle')
            self.assertEqual(execution['last_completed_part'], 1)
            self.assertFalse(execution['resume_required'])

    def test_failed_save_does_not_leave_false_completion(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'KR_B2A_APP_ROOT': str(Path(td) / 'app')}):
            job = make_prepared_job(Path(td))
            def fail(*args, **kwargs): raise RuntimeError('endpoint down')
            result = synthesize_parts(job, voice='voice', save_func=fail, validator=fake_validate, gap_seconds=0, retries=0, require_preview_approval=False)
            manifest = load_manifest(job)
            self.assertEqual(result['failures'][0]['index'], 1)
            self.assertEqual(manifest['execution']['status'], 'completed-with-failures')
            self.assertNotIn('1', manifest['audio']['completed'])


if __name__ == '__main__': unittest.main()
