import unittest
from kr_book_to_audio.manifest import ensure_manifest_defaults


class ManifestMigrationTests(unittest.TestCase):
    def test_legacy_script_conversion_is_retired_and_date_cleanup_is_migrated(self):
        payload = {'options': {'strip_dates': True, 'convert_config': 't2s', 't2s': True}}
        migrated = ensure_manifest_defaults(payload)
        self.assertTrue(migrated['options']['strip_datetime_tags'])
        self.assertNotIn('strip_dates', migrated['options'])
        self.assertNotIn('convert_config', migrated['options'])
        self.assertNotIn('t2s', migrated['options'])
        self.assertEqual(migrated['migration']['ignored_legacy_options'], ['convert_config', 'strip_dates', 't2s'])


if __name__ == '__main__':
    unittest.main()
