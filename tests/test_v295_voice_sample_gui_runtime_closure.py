from __future__ import annotations
from pathlib import Path
import tempfile
import unittest

from kr_book_to_audio.edge_voice_samples import EdgeSampleCache

ROOT = Path(__file__).resolve().parents[1]


class V295VoiceSampleGuiRuntimeClosureTests(unittest.TestCase):
    def test_gui_routes_voice_sample_telemetry_to_dedicated_adapter(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')
        self.assertIn('def _voice_sample_progress_event(self, payload: dict) -> None:', source)
        self.assertIn("('voice-sample-progress', 'Play voice sample', normalized, None)", source)
        self.assertIn("if kind == 'voice-sample-progress':", source)
        self.assertIn('Ignored malformed voice-sample telemetry', source)
        self.assertIn("if 'index' not in payload:", source)
        self.assertNotIn("volume=request['volume'], progress=self._progress_event)", source)

    def test_edge_sample_preview_uses_short_watchdogs(self):
        observed = {}
        events = []

        class Provider:
            def synthesize(self, text, out_path, **kwargs):
                observed.update(kwargs)
                kwargs['progress']({
                    'provider_id': 'edge-tts',
                    'stage': 'connecting',
                    'elapsed_seconds': 0.0,
                    'bytes_received': 0,
                })
                Path(out_path).write_bytes(b'ID3' + b'x' * 2048)

        with tempfile.TemporaryDirectory() as td:
            path = EdgeSampleCache(Path(td)).generate(
                Provider(),
                voice='en-US-TestNeural',
                locale='en-US',
                progress=events.append,
            )
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 1024)

        self.assertEqual(observed['no_audio_timeout_seconds'], 20.0)
        self.assertEqual(observed['total_timeout_seconds'], 60.0)
        self.assertEqual(events[0]['stage'], 'connecting')


if __name__ == '__main__':
    unittest.main()
