import unittest
from unittest.mock import patch
from kr_book_to_audio.power import ES_CONTINUOUS, ES_SYSTEM_REQUIRED, keep_computer_awake


class PowerTests(unittest.TestCase):
    def test_windows_keep_awake_enters_and_releases(self):
        calls=[]
        with patch('kr_book_to_audio.power.os.name', 'nt'):
            with keep_computer_awake(True, setter=lambda flags: calls.append(flags) or 1):
                pass
        self.assertEqual(calls, [ES_CONTINUOUS | ES_SYSTEM_REQUIRED, ES_CONTINUOUS])

    def test_windows_keep_awake_releases_after_exception(self):
        calls=[]
        with patch('kr_book_to_audio.power.os.name', 'nt'):
            with self.assertRaisesRegex(RuntimeError, 'boom'):
                with keep_computer_awake(True, setter=lambda flags: calls.append(flags) or 1):
                    raise RuntimeError('boom')
        self.assertEqual(calls[-1], ES_CONTINUOUS)


if __name__ == '__main__': unittest.main()
