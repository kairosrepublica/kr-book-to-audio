from pathlib import Path
import unittest
from kr_book_to_audio.gui import branding_asset_path

class PackageDataTests(unittest.TestCase):
    def test_branding_assets_live_inside_importable_package(self):
        package_dir = Path(__import__('kr_book_to_audio').__file__).resolve().parent
        expected = package_dir / 'assets' / 'branding' / 'kr_book_to_audio.ico'
        self.assertTrue(expected.is_file(), expected)
        self.assertEqual(branding_asset_path('kr_book_to_audio.ico'), expected)

if __name__ == '__main__': unittest.main()
