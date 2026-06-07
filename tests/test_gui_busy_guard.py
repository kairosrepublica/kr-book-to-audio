import unittest
from kr_book_to_audio.gui import BusyGuard

class GuiBusyGuardTests(unittest.TestCase):
    def test_busy_guard_rejects_second_background_operation(self):
        guard = BusyGuard()
        self.assertTrue(guard.start('first'))
        self.assertFalse(guard.start('second'))
        self.assertEqual(guard.label, 'first')
        guard.finish()
        self.assertTrue(guard.start('third'))

if __name__ == '__main__': unittest.main()
