from __future__ import annotations
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from kr_book_to_audio.providers import KokoroLocalProvider, ProviderTimedOut


class FakeFoundation:
    def __init__(self):
        self.python = Path('python.exe')
        self.worker = Path('kokoro_worker.py')
    def assert_ready(self): return None
    def worker_env(self): return {}


class CompletingProcess:
    def __init__(self, request_path: Path):
        request = json.loads(request_path.read_text(encoding='utf-8'))
        self.wav_path = Path(request['output'])
        self.calls = 0
        self.returncode = None
    def poll(self):
        self.calls += 1
        if self.calls < 3:
            return None
        self.wav_path.write_bytes(b'RIFF' + b'x' * 100)
        self.returncode = 0
        return 0


class HungProcess:
    def __init__(self):
        self.returncode = None
        self.terminated = False
        self.killed = False
        self.wait_calls = 0
    def poll(self): return None
    def terminate(self): self.terminated = True
    def kill(self): self.killed = True; self.returncode = -9
    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.wait_calls == 1:
            raise TimeoutError('still hung')
        return self.returncode


class KokoroHeartbeatTests(unittest.TestCase):
    def test_local_worker_emits_heartbeat_and_completion(self):
        provider = KokoroLocalProvider()
        events = []
        def fake_popen(args, **kwargs):
            return CompletingProcess(Path(args[-1]))
        def fake_run(args, **kwargs):
            Path(args[-1]).write_bytes(b'mp3')
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        with tempfile.TemporaryDirectory() as td, \
             patch.object(provider, '_foundation', return_value=FakeFoundation()), \
             patch('kr_book_to_audio.providers.shutil.which', return_value='ffmpeg'), \
             patch('kr_book_to_audio.providers.popen_hidden_cli', side_effect=fake_popen), \
             patch('kr_book_to_audio.providers.run_hidden_cli', side_effect=fake_run), \
             patch('kr_book_to_audio.providers.time.sleep', return_value=None):
            output = Path(td) / 'out.mp3'
            provider.synthesize('hello', output, voice='af_heart', rate='+0%', pitch='+0Hz', volume='+0%', progress=events.append)
        stages = [event['stage'] for event in events]
        self.assertIn('local-worker-running', stages)
        self.assertIn('local-worker-encoding', stages)
        self.assertEqual(stages[-1], 'local-worker-completed')

    def test_hung_local_worker_is_terminated_then_killed(self):
        provider = KokoroLocalProvider()
        process = HungProcess()
        timeline = iter([0.0, 0.0, 1.0, 2.0, 3.0])
        with tempfile.TemporaryDirectory() as td, \
             patch.object(provider, '_foundation', return_value=FakeFoundation()), \
             patch('kr_book_to_audio.providers.shutil.which', return_value='ffmpeg'), \
             patch('kr_book_to_audio.providers.popen_hidden_cli', return_value=process), \
             patch('kr_book_to_audio.providers.time.monotonic', side_effect=lambda: next(timeline, 10.0)), \
             patch('kr_book_to_audio.providers.time.sleep', return_value=None), \
             patch.dict(os.environ, {'KR_B2A_KOKORO_TOTAL_TIMEOUT_SECONDS': '0.5'}):
            with self.assertRaises(ProviderTimedOut):
                provider.synthesize('hello', Path(td) / 'out.mp3', voice='af_heart', rate='+0%', pitch='+0Hz', volume='+0%')
        self.assertTrue(process.terminated)
        self.assertTrue(process.killed)


if __name__ == '__main__':
    unittest.main()
