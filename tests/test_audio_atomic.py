import tempfile
import unittest
from pathlib import Path
from kr_book_to_audio.audio import synthesize_parts
from kr_book_to_audio.manifest import new_manifest, save_manifest
from kr_book_to_audio.models import JobPaths
from kr_book_to_audio.utils import atomic_write_text, sha256_text

class AudioAtomicTests(unittest.TestCase):
    def test_atomic_partial_is_renamed_only_after_validation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); job = JobPaths.from_root(root / 'job'); job.ensure()
            src = root / 'src.txt'; src.write_text('中文', encoding='utf-8')
            atomic_write_text(job.parts_text / 'part-0001.txt', '中文')
            manifest = new_manifest(source=src, source_sha256='x', title='book', options={'chunk_chars': 100})
            manifest['parts'] = [{'index': 1, 'file': 'part-0001.txt', 'sha256': sha256_text('中文')}]
            save_manifest(job, manifest)
            def fake_save(text, out, **kwargs): out.write_bytes(b'x' * 2048)
            def fake_validate(path): return {'bytes': path.stat().st_size, 'duration_seconds': 1.0, 'sha256': 'fake'}
            report = synthesize_parts(job, voice='voice', save_func=fake_save, validator=fake_validate, gap_seconds=0)
            self.assertFalse(report['failures'])
            self.assertTrue((job.parts_audio / 'part-0001.mp3').exists())
            self.assertFalse((job.parts_audio / 'part-0001.mp3.partial').exists())

if __name__ == '__main__': unittest.main()
