import tempfile
import unittest
from pathlib import Path
from kr_book_to_audio.audio import audio_signature, expected_audio_paths, merge_parts
from kr_book_to_audio.manifest import load_manifest, save_manifest
from kr_book_to_audio.models import JobPaths
from kr_book_to_audio.pipeline import rebuild_parts
from kr_book_to_audio.utils import atomic_write_text
from helpers import fake_validate, make_prepared_job

class ManifestIntegrityTests(unittest.TestCase):
    def make_job(self, td):
        return make_prepared_job(Path(td))

    def test_rebuild_deletes_stale_parts_and_audio(self):
        with tempfile.TemporaryDirectory() as td:
            job = self.make_job(td)
            atomic_write_text(job.proofread, '\n\n'.join(['中' * 100 + '。'] * 3))
            rebuild_parts(job, chunk_chars=100)
            (job.parts_audio / 'part-0003.mp3').write_bytes(b'x' * 2000)
            atomic_write_text(job.proofread, '中' * 100 + '。')
            rebuild_parts(job, chunk_chars=100)
            self.assertEqual(sorted(path.name for path in job.parts_text.glob('part-*.txt')), ['part-0001.txt'])
            self.assertFalse((job.parts_audio / 'part-0003.mp3').exists())

    def test_expected_paths_are_numeric_above_99(self):
        with tempfile.TemporaryDirectory() as td:
            job = self.make_job(td)
            manifest = {'parts': [{'index': index} for index in range(1, 102)]}
            names = [path.name for path in expected_audio_paths(job, manifest)]
            self.assertEqual(names[9:12], ['part-0010.mp3', 'part-0011.mp3', 'part-0012.mp3'])
            self.assertEqual(names[-2:], ['part-0100.mp3', 'part-0101.mp3'])

    def test_merge_refuses_missing_completion_record(self):
        with tempfile.TemporaryDirectory() as td:
            text = '中' * 100 + '。\n\n' + '文' * 100 + '。'
            job = make_prepared_job(Path(td), text=text, chunk_chars=100)
            manifest = load_manifest(job)
            signature = audio_signature(voice='voice', rate='+0%')
            manifest['audio']['signature'] = signature
            first = job.parts_audio / 'part-0001.mp3'
            first.write_bytes(b'x' * 2048)
            manifest['audio']['completed']['1'] = {'text_sha256': manifest['parts'][0]['sha256'], 'signature': signature, **fake_validate(first)}
            manifest['gates']['preview'] = {'approved_audio_signature': signature, 'approved_part_sha256': manifest['parts'][0]['sha256'], 'approved_utc': 'test'}
            save_manifest(job, manifest)
            with self.assertRaisesRegex(RuntimeError, 'missing or stale'):
                merge_parts(job, validator=fake_validate)

if __name__ == '__main__': unittest.main()
