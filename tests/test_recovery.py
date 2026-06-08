import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from helpers import fake_save, fake_validate, make_prepared_job
from kr_book_to_audio.audio import _write_audio_sidecar, audio_signature, reconcile_audio_state, synthesize_parts
from kr_book_to_audio.manifest import load_manifest, save_manifest
from kr_book_to_audio.recovery import recover_job
from kr_book_to_audio.utils import atomic_write_json


class RecoveryTests(unittest.TestCase):
    def test_interrupted_job_clears_dead_lock_partial_and_resumes_first_incomplete(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'KR_B2A_APP_ROOT': str(Path(td) / 'app')}):
            text = '中' * 100 + '。\n\n' + '文' * 100 + '。'
            job = make_prepared_job(Path(td), text=text, chunk_chars=100)
            synthesize_parts(job, voice='voice', start=1, end=1, save_func=fake_save, validator=fake_validate, gap_seconds=0, require_preview_approval=False)
            manifest = load_manifest(job)
            manifest['execution'].update({'status': 'running', 'pid': 999999, 'current_part': 2, 'current_part_state': 'running', 'resume_required': False})
            save_manifest(job, manifest)
            atomic_write_json(job.work / '.operation.lock', {'operation': 'synthesize-parts', 'pid': 999999})
            partial = job.parts_audio / 'part-0002.partial.mp3'; partial.write_bytes(b'x' * 2048)
            report = recover_job(job, validator=fake_validate, process_checker=lambda pid: False)
            self.assertTrue(report['interrupted'])
            self.assertTrue(report['stale_lock_removed'])
            self.assertEqual(report['next_part'], 2)
            self.assertFalse(partial.exists())
            self.assertTrue((job.parts_audio / 'part-0001.mp3').exists())

    def test_orphan_final_mp3_is_adopted_only_with_matching_sidecar(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'KR_B2A_APP_ROOT': str(Path(td) / 'app')}):
            job = make_prepared_job(Path(td))
            manifest = load_manifest(job)
            signature = audio_signature(voice='voice')
            manifest['audio']['signature'] = signature
            save_manifest(job, manifest)
            audio = job.parts_audio / 'part-0001.mp3'; fake_save('text', audio)
            metadata = fake_validate(audio)
            _write_audio_sidecar(audio, text_sha256=manifest['parts'][0]['sha256'], signature=signature, metadata=metadata)
            report = reconcile_audio_state(job, validator=fake_validate)
            self.assertEqual(report['completed'], [1])
            self.assertIn('1', load_manifest(job)['audio']['completed'])

    def test_untrusted_orphan_mp3_is_deleted(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {'KR_B2A_APP_ROOT': str(Path(td) / 'app')}):
            job = make_prepared_job(Path(td))
            manifest = load_manifest(job); manifest['audio']['signature'] = audio_signature(voice='voice'); save_manifest(job, manifest)
            audio = job.parts_audio / 'part-0001.mp3'; fake_save('text', audio)
            report = reconcile_audio_state(job, validator=fake_validate)
            self.assertEqual(report['removed_invalid'], [1])
            self.assertFalse(audio.exists())


if __name__ == '__main__': unittest.main()
