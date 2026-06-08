import unittest
from kr_book_to_audio.config import _migrate_config


class ConfigMigrationTests(unittest.TestCase):
    def test_retired_options_are_removed_from_local_config(self):
        migrated = _migrate_config({'strip_dates': True, 'strip_datetime_tags': True, 't2s': True, 'voice': 'voice'})
        self.assertNotIn('strip_dates', migrated)
        self.assertNotIn('strip_datetime_tags', migrated)
        self.assertNotIn('t2s', migrated)
        self.assertEqual(migrated['voice'], 'voice')
        self.assertEqual(migrated['tts_engine'], 'edge-tts')
        self.assertEqual(migrated['processing_profile'], 'auto')


if __name__ == '__main__':
    unittest.main()
