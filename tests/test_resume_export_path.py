import tempfile
import unittest
from pathlib import Path
from kr_book_to_audio.manifest import new_manifest, save_manifest
from kr_book_to_audio.models import JobPaths

class ResumeExportPathTests(unittest.TestCase):
    def test_resume_rehydrates_separate_export_path_from_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); export = root / 'separate-export'; job = JobPaths.from_root(root / 'job', export); job.ensure()
            src = root / 'src.txt'; src.write_text('中文。', encoding='utf-8')
            manifest = new_manifest(source=src, source_sha256='x', title='book', options={'chunk_chars': 100})
            manifest['paths'] = {'export_runtime_only': str(export)}
            save_manifest(job, manifest)
            resumed = JobPaths.from_root(job.root)
            self.assertEqual(resumed.export, export)

if __name__ == '__main__': unittest.main()
