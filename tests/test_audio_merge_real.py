import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from kr_book_to_audio.audio import merge_parts, validate_mp3
from kr_book_to_audio.manifest import new_manifest, save_manifest
from kr_book_to_audio.models import JobPaths

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg fixture requires ffmpeg and ffprobe')
class RealAudioMergeTests(unittest.TestCase):
    def test_real_ffmpeg_merge_uses_inferable_partial_extension(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); job = JobPaths.from_root(root / 'job'); job.ensure()
            source = root / 'source.txt'; source.write_text('中文。', encoding='utf-8')
            manifest = new_manifest(source=source, source_sha256='x', title='book', options={'chunk_chars': 100})
            manifest['parts'] = [{'index': 1, 'file': 'part-0001.txt', 'sha256': 'a'}]
            save_manifest(job, manifest)
            part = job.parts_audio / 'part-0001.mp3'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.2', '-q:a', '9', str(part)], check=True)
            output = merge_parts(job)
            self.assertTrue(output.exists())
            self.assertGreater(validate_mp3(output)['duration_seconds'], 0)
            self.assertFalse((job.export / 'book.partial.mp3').exists())

if __name__ == '__main__': unittest.main()
