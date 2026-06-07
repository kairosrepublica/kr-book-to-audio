import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from kr_book_to_audio.audio import audio_signature, merge_parts, validate_mp3
from kr_book_to_audio.manifest import load_manifest, save_manifest
from helpers import make_prepared_job

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg fixture requires ffmpeg and ffprobe')
class RealAudioMergeTests(unittest.TestCase):
    def test_real_ffmpeg_merge_uses_inferable_partial_extension(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            part = job.parts_audio / 'part-0001.mp3'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.2', '-q:a', '9', str(part)], check=True)
            manifest = load_manifest(job)
            signature = audio_signature(voice='voice', rate='+0%')
            manifest['audio']['signature'] = signature
            manifest['audio']['completed']['1'] = {'text_sha256': manifest['parts'][0]['sha256'], 'signature': signature, **validate_mp3(part)}
            manifest['gates']['preview'] = {'approved_audio_signature': signature, 'approved_part_sha256': manifest['parts'][0]['sha256'], 'approved_utc': 'test'}
            save_manifest(job, manifest)
            output = merge_parts(job)
            self.assertTrue(output.exists())
            self.assertGreater(validate_mp3(output)['duration_seconds'], 0)
            self.assertFalse((job.export / 'book.partial.mp3').exists())

if __name__ == '__main__': unittest.main()
