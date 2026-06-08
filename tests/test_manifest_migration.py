import unittest
from kr_book_to_audio.manifest import ensure_manifest_defaults


class ManifestMigrationTests(unittest.TestCase):
    def test_legacy_prepare_options_are_retired_and_schema_is_upgraded(self):
        payload = {'schema_version': 1, 'options': {'strip_dates': True, 'strip_datetime_tags': True, 'convert_config': 't2s', 't2s': True}}
        migrated = ensure_manifest_defaults(payload)
        self.assertEqual(migrated['schema_version'], 3)
        self.assertNotIn('strip_dates', migrated['options'])
        self.assertNotIn('strip_datetime_tags', migrated['options'])
        self.assertNotIn('convert_config', migrated['options'])
        self.assertNotIn('t2s', migrated['options'])
        self.assertEqual(migrated['migration']['ignored_legacy_options'], ['convert_config', 'strip_dates', 'strip_datetime_tags', 't2s'])
        self.assertEqual(migrated['audio']['provider_id'], 'edge-tts')


if __name__ == '__main__':
    unittest.main()
