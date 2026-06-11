import unittest
from unittest.mock import patch

from kr_book_to_audio.gui import App


class DirectSynthesizeV250Tests(unittest.TestCase):
    def test_synthesize_all_starts_immediately_without_confirmation_dialog(self):
        calls = []
        class Dummy:
            def _job_required(self): return object()
            def _speech_request_snapshot(self): return {'keep_awake': False}
            def _progress_event(self, payload): return None
            def _run(self, label, fn): calls.append((label, fn))
        with patch('kr_book_to_audio.gui.messagebox.askyesno', side_effect=AssertionError('confirmation must not run')):
            App.synthesize(Dummy())
        self.assertEqual(calls[0][0], 'Synthesize all parts')


if __name__ == '__main__':
    unittest.main()
