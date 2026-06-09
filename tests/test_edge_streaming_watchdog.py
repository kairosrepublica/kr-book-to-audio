import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from kr_book_to_audio.providers import EdgeTTSProvider, ProviderStalled


class _NormalCommunicate:
    def __init__(self, *args, **kwargs):
        pass

    async def stream(self):
        yield {'type': 'audio', 'data': b'a' * 2048}
        await asyncio.sleep(0.001)
        yield {'type': 'audio', 'data': b'b' * 2048}


class _StalledCommunicate:
    def __init__(self, *args, **kwargs):
        pass

    async def stream(self):
        await asyncio.sleep(0.2)
        if False:
            yield {}


class _SlowActiveCommunicate:
    def __init__(self, *args, **kwargs):
        pass

    async def stream(self):
        for token in (b'a', b'b', b'c'):
            await asyncio.sleep(0.01)
            yield {'type': 'audio', 'data': token * 2048}


class EdgeStreamingWatchdogTests(unittest.TestCase):
    def _module(self, communicate):
        return types.SimpleNamespace(Communicate=communicate)

    def test_streaming_audio_writes_real_bytes_and_emits_telemetry(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(sys.modules, {'edge_tts': self._module(_NormalCommunicate)}):
            output = Path(td) / 'part.partial.mp3'
            events = []
            EdgeTTSProvider().synthesize('text', output, voice='v', rate='+0%', pitch='+0Hz', volume='+0%', progress=events.append, no_audio_timeout_seconds=0.05, total_timeout_seconds=1)
            self.assertEqual(output.read_bytes(), b'a' * 2048 + b'b' * 2048)
            self.assertIn('receiving-audio', [event['stage'] for event in events])
            self.assertEqual(events[-1]['stage'], 'provider-completed')
            self.assertEqual(events[-1]['bytes_received'], 4096)

    def test_no_audio_stall_raises_and_removes_partial(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(sys.modules, {'edge_tts': self._module(_StalledCommunicate)}):
            output = Path(td) / 'part.partial.mp3'
            with self.assertRaisesRegex(ProviderStalled, 'no audio bytes'):
                EdgeTTSProvider().synthesize('text', output, voice='v', rate='+0%', pitch='+0Hz', volume='+0%', no_audio_timeout_seconds=0.02, total_timeout_seconds=1)
            self.assertFalse(output.exists())

    def test_slow_but_active_stream_is_not_killed(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(sys.modules, {'edge_tts': self._module(_SlowActiveCommunicate)}):
            output = Path(td) / 'part.partial.mp3'
            EdgeTTSProvider().synthesize('text', output, voice='v', rate='+0%', pitch='+0Hz', volume='+0%', no_audio_timeout_seconds=0.04, total_timeout_seconds=1)
            self.assertGreater(output.stat().st_size, 4096)


if __name__ == '__main__':
    unittest.main()
