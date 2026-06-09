from __future__ import annotations
import tempfile
import unittest
from pathlib import Path

from helpers import make_prepared_job
from kr_book_to_audio.audio import _provider_progress_bridge
from kr_book_to_audio.manifest import load_manifest


class AudioProviderBackpressureTests(unittest.TestCase):
    def test_audio_bridge_throttles_high_frequency_ui_telemetry(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            manifest = load_manifest(job)
            events = []
            bridge = _provider_progress_bridge(job, manifest, events.append, index=1, attempt=1, provider_id='edge-tts')
            for seq in range(10_000):
                bridge({'stage': 'receiving-audio', 'bytes_received': seq, 'elapsed_seconds': seq / 1000.0})
            self.assertGreaterEqual(len(events), 1)
            self.assertLessEqual(len(events), 3)
            self.assertEqual(events[-1]['state'], 'provider-status')
            self.assertEqual(manifest['audio']['last_runtime_telemetry']['bytes_received'], 9999)
            self.assertLessEqual(load_manifest(job)['audio']['last_runtime_telemetry']['bytes_received'], 9999)


if __name__ == '__main__':
    unittest.main()
