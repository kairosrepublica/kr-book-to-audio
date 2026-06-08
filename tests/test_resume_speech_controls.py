import tempfile
import unittest
from pathlib import Path
from helpers import fake_save, fake_validate, make_prepared_job
from kr_book_to_audio.audio import approve_preview, audio_signature, recover_speech_controls, speech_controls, synthesize_parts
from kr_book_to_audio.manifest import load_manifest, save_manifest


class ResumeSpeechControlsTests(unittest.TestCase):
    def test_preview_generation_persists_task_bound_speech_controls(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td))
            synthesize_parts(
                job,
                provider_id='edge-tts',
                voice='voice-a',
                rate='+12%',
                pitch='+3Hz',
                volume='-4%',
                start=1,
                end=1,
                save_func=fake_save,
                validator=fake_validate,
                gap_seconds=0,
                require_preview_approval=False,
            )
            approve_preview(job, provider_id='edge-tts', voice='voice-a', rate='+12%', pitch='+3Hz', volume='-4%', validator=fake_validate)
            manifest = load_manifest(job)
            self.assertEqual(manifest['audio']['controls'], {
                'provider_id': 'edge-tts',
                'voice': 'voice-a',
                'rate': '+12%',
                'pitch': '+3Hz',
                'volume': '-4%',
            })

    def test_stored_controls_are_restored_when_signature_matches(self):
        controls = speech_controls(provider_id='edge-tts', voice='voice-a', rate='+8%', pitch='+1Hz', volume='-2%')
        manifest = {'audio': {'signature': audio_signature(**controls), 'controls': controls}}
        self.assertEqual(recover_speech_controls(manifest), controls)

    def test_legacy_default_controls_are_safely_recovered_from_voice_candidates(self):
        controls = speech_controls(provider_id='edge-tts', voice='zh-CN-YunyangNeural')
        manifest = {'audio': {'provider_id': 'edge-tts', 'signature': audio_signature(**controls), 'controls': None}}
        recovered = recover_speech_controls(manifest, candidate_voices=['en-US-AriaNeural', 'zh-CN-YunyangNeural'])
        self.assertEqual(recovered, controls)

    def test_legacy_custom_controls_are_not_guessed(self):
        controls = speech_controls(provider_id='edge-tts', voice='voice-a', rate='+17%')
        manifest = {'audio': {'provider_id': 'edge-tts', 'signature': audio_signature(**controls), 'controls': None}}
        self.assertIsNone(recover_speech_controls(manifest, candidate_voices=['voice-a']))


if __name__ == '__main__':
    unittest.main()
