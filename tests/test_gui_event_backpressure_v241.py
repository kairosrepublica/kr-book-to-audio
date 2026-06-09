from __future__ import annotations
import inspect
import queue
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from kr_book_to_audio import gui


class FakeWidget:
    def __init__(self):
        self.values = {}
    def config(self, **kwargs):
        self.values.update(kwargs)
    configure = config
    def cget(self, name):
        return self.values.get(name, 'normal')


class FakeRoot:
    def __init__(self):
        self.after_calls = []
    def after(self, delay, callback):
        self.after_calls.append((delay, callback))


class FakeVar:
    def __init__(self, value): self.value = value
    def get(self): return self.value


class LatestTelemetryMailboxTests(unittest.TestCase):
    def test_one_hundred_thousand_updates_keep_fixed_memory_latest_only(self):
        mailbox = gui.LatestTelemetryMailbox()
        for seq in range(100_000):
            self.assertTrue(mailbox.publish({'index': 1, 'state': 'provider-status', 'bytes_received': seq}))
        self.assertEqual(mailbox.pending_count(), 1)
        snapshots = mailbox.take_latest(limit=8)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]['bytes_received'], 99_999)
        self.assertEqual(mailbox.pending_count(), 0)

    def test_terminal_part_rejects_stale_telemetry_until_reopened(self):
        mailbox = gui.LatestTelemetryMailbox()
        mailbox.publish({'index': 3, 'state': 'provider-status', 'bytes_received': 1})
        mailbox.mark_terminal(3)
        self.assertFalse(mailbox.publish({'index': 3, 'state': 'provider-status', 'bytes_received': 2}))
        self.assertEqual(mailbox.pending_count(), 0)
        mailbox.reopen(3)
        self.assertTrue(mailbox.publish({'index': 3, 'state': 'provider-status', 'bytes_received': 3}))
        self.assertEqual(mailbox.take_latest()[0]['bytes_received'], 3)


class AppBackpressureTests(unittest.TestCase):
    def make_bare_app(self):
        app = gui.App.__new__(gui.App)
        app.events = queue.Queue()
        app.telemetry_mailbox = gui.LatestTelemetryMailbox()
        app.root = FakeRoot()
        return app

    def test_provider_status_is_coalesced_outside_control_queue(self):
        app = self.make_bare_app()
        for seq in range(10_000):
            app._progress_event({'index': 1, 'state': 'provider-status', 'bytes_received': seq})
        self.assertEqual(app.events.qsize(), 0)
        self.assertEqual(app.telemetry_mailbox.pending_count(), 1)

    def test_terminal_control_event_discards_stale_telemetry(self):
        app = self.make_bare_app()
        app._progress_event({'index': 1, 'state': 'provider-status', 'bytes_received': 99})
        app._progress_event({'index': 1, 'state': 'done'})
        self.assertEqual(app.telemetry_mailbox.pending_count(), 0)
        self.assertEqual(app.events.qsize(), 1)

    def test_drain_has_hard_event_budget_and_yields(self):
        app = self.make_bare_app()
        seen = []
        app._update_part_progress = lambda payload: seen.append(payload)
        app._update_provider_telemetry = lambda payload: None
        app._handle_process_trace = lambda payload: None
        for index in range(gui.CONTROL_EVENTS_PER_DRAIN + 20):
            app.events.put(('progress', 'Synthesis', {'index': index + 1, 'state': 'queued'}, None))
        app._drain()
        self.assertEqual(len(seen), gui.CONTROL_EVENTS_PER_DRAIN)
        self.assertEqual(app.events.qsize(), 20)
        self.assertEqual(app.root.after_calls[-1][0], gui.GUI_DRAIN_INTERVAL_MS)

    def test_drain_has_time_budget_and_yields(self):
        app = self.make_bare_app()
        seen = []
        app._update_part_progress = lambda payload: seen.append(payload)
        app._update_provider_telemetry = lambda payload: None
        app._handle_process_trace = lambda payload: None
        for index in range(10):
            app.events.put(('progress', 'Synthesis', {'index': index + 1, 'state': 'queued'}, None))
        values = iter([0.0, 0.0, gui.CONTROL_DRAIN_TIME_BUDGET_SECONDS + 0.001, gui.CONTROL_DRAIN_TIME_BUDGET_SECONDS + 0.002])
        with patch('kr_book_to_audio.gui.time.monotonic', side_effect=lambda: next(values, 1.0)):
            app._drain()
        self.assertLessEqual(len(seen), 1)
        self.assertGreaterEqual(app.events.qsize(), 9)

    def test_provider_telemetry_update_is_lightweight(self):
        app = self.make_bare_app()
        app.current_index = 1
        app.current_started_monotonic = time.monotonic()
        app.current_estimate = 5
        app.provider_runtime = {}
        app.current_label = FakeWidget()
        app.status = FakeWidget()
        rendered = []
        app._set_part_state = lambda *args, **kwargs: rendered.append((args, kwargs))
        app._tts_engine_id = lambda: 'edge-tts'
        app._refresh_job_view = lambda: self.fail('telemetry-only update must not refresh full job view')
        app._update_part_progress({'index': 1, 'state': 'provider-status', 'provider_id': 'edge-tts', 'stage': 'receiving-audio', 'bytes_received': 1024, 'last_audio_seconds_ago': 0.0})
        self.assertTrue(rendered)
        self.assertIn('receiving audio', app.status.values['text'])

    def test_speech_request_snapshot_contains_plain_values(self):
        app = gui.App.__new__(gui.App)
        app.tts_engine_labels = {'Edge': 'edge-tts'}
        app.tts_engine = FakeVar('Edge')
        app.voice = FakeVar('voice')
        app.rate = FakeVar('+0%')
        app.pitch = FakeVar('+0Hz')
        app.volume = FakeVar('+0%')
        app.keep_awake = FakeVar(True)
        snapshot = app._speech_request_snapshot()
        self.assertEqual(snapshot, {'provider_id': 'edge-tts', 'voice': 'voice', 'rate': '+0%', 'pitch': '+0Hz', 'volume': '+0%', 'keep_awake': True})
        self.assertTrue(all(not hasattr(value, 'get') for value in snapshot.values()))

    def test_preview_playback_runs_only_from_gui_success_callback(self):
        app = gui.App.__new__(gui.App)
        job = type('Job', (), {'parts_audio': Path('/tmp')})()
        app._job_required = lambda: job
        app._speech_request_snapshot = lambda: {'provider_id': 'edge-tts', 'voice': 'voice', 'rate': '+0%', 'pitch': '+0Hz', 'volume': '+0%', 'keep_awake': False}
        app._progress_event = lambda payload: None
        captured = {}
        played = []
        def capture_run(label, fn, on_success=None):
            captured.update(label=label, fn=fn, on_success=on_success)
        app._run = capture_run
        app._play = lambda path: played.append(Path(path))
        app.preview_playback_token = 0
        app.last_played_preview_token = 0
        with patch('kr_book_to_audio.gui.synthesize_parts', return_value={'failures': []}):
            app.preview()
            result = captured['fn']()
            self.assertEqual(played, [])
            captured['on_success'](result)
            captured['on_success'](result)
        self.assertEqual(played, [Path('/tmp') / 'part-0001.mp3'])

    def test_audio_worker_actions_snapshot_before_background_execution(self):
        for name in ('audition', 'preview', 'approve_part_one', 'synthesize', 'retry_failed', '_resume_from_part'):
            source = inspect.getsource(getattr(gui.App, name))
            self.assertNotIn('self.voice.get()', source, name)
            self.assertNotIn('self.rate.get()', source, name)
            self.assertNotIn('self.pitch.get()', source, name)
            self.assertNotIn('self.volume.get()', source, name)
            self.assertNotIn('self.keep_awake.get()', source, name)


if __name__ == '__main__':
    unittest.main()
