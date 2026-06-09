import tempfile
import unittest
from pathlib import Path

from helpers import fake_validate, make_prepared_job
from kr_book_to_audio.audio import synthesize_parts
from kr_book_to_audio.manifest import load_manifest


class AudioProviderTelemetryTests(unittest.TestCase):
    def test_provider_progress_is_bridged_into_gui_events_and_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            events = []
            def save(text, out, *, progress=None, **kwargs):
                progress({'provider_id': 'edge-tts', 'stage': 'receiving-audio', 'elapsed_seconds': 1.5, 'bytes_received': 2048, 'last_audio_seconds_ago': 0.0})
                out.write_bytes(b'x' * 4096)
            synthesize_parts(job, voice='voice', save_func=save, validator=fake_validate, gap_seconds=0, require_preview_approval=False, progress=events.append)
            telemetry = load_manifest(job)['audio']['last_runtime_telemetry']
            self.assertEqual(telemetry['stage'], 'receiving-audio')
            self.assertEqual(telemetry['bytes_received'], 2048)
            self.assertIn('provider-status', [event['state'] for event in events])

    def test_edge_failure_recommends_local_provider_switch(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            def fail(*args, **kwargs):
                raise RuntimeError('network stalled')
            report = synthesize_parts(job, voice='voice', provider_id='edge-tts', save_func=fail, validator=fake_validate, gap_seconds=0, retries=0, require_preview_approval=False)
            recommendation = report['failures'][0]['switch_recommendation']
            self.assertIn('switch TTS engine to Kokoro Local TTS', recommendation)
            self.assertIn('approve Part 1', recommendation)


if __name__ == '__main__':
    unittest.main()
