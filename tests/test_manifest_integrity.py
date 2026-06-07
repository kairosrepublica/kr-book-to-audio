import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kr_book_to_audio.audio import expected_audio_paths, merge_parts
from kr_book_to_audio.manifest import new_manifest, save_manifest
from kr_book_to_audio.models import JobPaths
from kr_book_to_audio.pipeline import rebuild_parts
from kr_book_to_audio.utils import atomic_write_text

class ManifestIntegrityTests(unittest.TestCase):
    def make_job(self, td):
        job = JobPaths.from_root(Path(td) / 'job'); job.ensure()
        source = Path(td) / 'source.txt'; source.write_text('中文。', encoding='utf-8')
        manifest = new_manifest(source=source, source_sha256='x', title='book', options={'chunk_chars': 100})
        save_manifest(job, manifest)
        return job
    def test_rebuild_deletes_stale_parts_and_audio(self):
        with tempfile.TemporaryDirectory() as td:
            job = self.make_job(td)
            atomic_write_text(job.proofread, '\n\n'.join(['中' * 100 + '。'] * 3))
            rebuild_parts(job, chunk_chars=100)
            (job.parts_audio / 'part-0003.mp3').write_bytes(b'x' * 2000)
            atomic_write_text(job.proofread, '中' * 100 + '。')
            rebuild_parts(job, chunk_chars=100)
            self.assertEqual(sorted(p.name for p in job.parts_text.glob('part-*.txt')), ['part-0001.txt'])
            self.assertFalse((job.parts_audio / 'part-0003.mp3').exists())
    def test_expected_paths_are_numeric_above_99(self):
        with tempfile.TemporaryDirectory() as td:
            job = self.make_job(td)
            manifest = {'parts': [{'index': i} for i in range(1, 102)]}
            names = [p.name for p in expected_audio_paths(job, manifest)]
            self.assertEqual(names[9:12], ['part-0010.mp3', 'part-0011.mp3', 'part-0012.mp3'])
            self.assertEqual(names[-2:], ['part-0100.mp3', 'part-0101.mp3'])
    def test_merge_refuses_missing_manifest_part(self):
        with tempfile.TemporaryDirectory() as td:
            job = self.make_job(td)
            manifest = json.loads(job.manifest.read_text(encoding='utf-8'))
            manifest['parts'] = [{'index': 1, 'file': 'part-0001.txt', 'sha256': 'a'}, {'index': 2, 'file': 'part-0002.txt', 'sha256': 'b'}]
            save_manifest(job, manifest)
            (job.parts_audio / 'part-0001.mp3').write_bytes(b'x' * 2000)
            def validator(path):
                if not path.exists(): raise RuntimeError('missing')
                return {'bytes': path.stat().st_size, 'duration_seconds': 1, 'sha256': 'x'}
            with self.assertRaisesRegex(RuntimeError, 'missing'):
                merge_parts(job, validator=validator)

if __name__ == '__main__': unittest.main()
