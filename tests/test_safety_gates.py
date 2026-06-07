import json
import tempfile
import unittest
from pathlib import Path
from kr_book_to_audio.audio import approve_preview, merge_parts, retry_failed_parts, synthesize_parts
from kr_book_to_audio.pipeline import approve_proofread_and_rebuild
from helpers import fake_save, fake_validate, make_prepared_job

class SafetyGateTests(unittest.TestCase):
    def test_full_synthesis_requires_preview_approval(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            with self.assertRaisesRegex(RuntimeError, 'Part 1 preview'):
                synthesize_parts(job, voice='voice', save_func=fake_save, validator=fake_validate, gap_seconds=0)

    def test_preview_then_approval_allows_full_synthesis(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            synthesize_parts(job, voice='voice', save_func=fake_save, validator=fake_validate, gap_seconds=0, require_preview_approval=False)
            approve_preview(job, voice='voice', validator=fake_validate)
            result = synthesize_parts(job, voice='voice', save_func=fake_save, validator=fake_validate, gap_seconds=0)
            self.assertFalse(result['failures'])

    def test_proofread_edit_blocks_preview_until_reapproved(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            job.proofread.write_text(job.proofread.read_text(encoding='utf-8') + '新增内容。', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'proofread.txt changed'):
                synthesize_parts(job, voice='voice', save_func=fake_save, validator=fake_validate, gap_seconds=0, require_preview_approval=False)

    def test_dictionary_edit_blocks_preview_until_reapproved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dictionary = root / 'dictionary.json'
            dictionary.write_text(json.dumps({'replacements': [{'find': '中文', 'replace': '中 文'}]}, ensure_ascii=False), encoding='utf-8')
            job = make_prepared_job(root, dictionary=dictionary)
            dictionary.write_text(json.dumps({'replacements': [{'find': '中文', 'replace': '钟 文'}]}, ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'dictionary changed'):
                synthesize_parts(job, voice='voice', save_func=fake_save, validator=fake_validate, gap_seconds=0, require_preview_approval=False)

    def test_voice_change_requires_new_preview_approval(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            synthesize_parts(job, voice='voice-a', save_func=fake_save, validator=fake_validate, gap_seconds=0, require_preview_approval=False)
            approve_preview(job, voice='voice-a', validator=fake_validate)
            with self.assertRaisesRegex(RuntimeError, 'Part 1 preview'):
                synthesize_parts(job, voice='voice-b', save_func=fake_save, validator=fake_validate, gap_seconds=0)

    def test_failed_part_retry_only_retries_recorded_failure(self):
        with tempfile.TemporaryDirectory() as td:
            text = '中' * 100 + '。\n\n' + '文' * 100 + '。'
            job = make_prepared_job(Path(td), text=text, chunk_chars=100)
            synthesize_parts(job, voice='voice', start=1, end=1, save_func=fake_save, validator=fake_validate, gap_seconds=0, require_preview_approval=False)
            approve_preview(job, voice='voice', validator=fake_validate)
            def fail_second(text, out, **kwargs):
                if text.startswith('文'):
                    raise RuntimeError('simulated endpoint failure')
                fake_save(text, out, **kwargs)
            result = synthesize_parts(job, voice='voice', save_func=fail_second, validator=fake_validate, gap_seconds=0, retries=0)
            self.assertEqual([item['index'] for item in result['failures']], [2])
            retried = retry_failed_parts(job, voice='voice', save_func=fake_save, validator=fake_validate, gap_seconds=0, retries=0)
            self.assertFalse(retried['failures'])
            self.assertEqual(retried['completed'], [1, 2])

    def test_merge_rejects_audio_file_modified_after_validation(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            synthesize_parts(job, voice='voice', save_func=fake_save, validator=fake_validate, gap_seconds=0, require_preview_approval=False)
            approve_preview(job, voice='voice', validator=fake_validate)
            (job.parts_audio / 'part-0001.mp3').write_bytes(b'z' * 4096)
            with self.assertRaisesRegex(RuntimeError, 'changed after validation'):
                merge_parts(job, validator=fake_validate)

    def test_progress_callback_reports_queue_running_and_done(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            events = []
            synthesize_parts(job, voice='voice', save_func=fake_save, validator=fake_validate, gap_seconds=0, require_preview_approval=False, progress=events.append)
            states = [item['state'] for item in events]
            self.assertIn('queued', states)
            self.assertIn('running', states)
            self.assertIn('done', states)

    def test_synthesis_writes_durable_json_line_log(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            synthesize_parts(job, voice='voice', save_func=fake_save, validator=fake_validate, gap_seconds=0, require_preview_approval=False)
            log = job.run_log.read_text(encoding='utf-8')
            self.assertIn('synthesis-started', log)
            self.assertIn('part-completed', log)
            self.assertIn('synthesis-finished', log)

if __name__ == '__main__': unittest.main()
