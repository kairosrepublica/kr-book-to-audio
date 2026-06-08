from pathlib import Path
import unittest
from PIL import Image
from kr_book_to_audio.gui import apply_window_icon, branding_asset_path


ROOT = Path(__file__).resolve().parents[1]
BRANDING = ROOT / 'assets' / 'branding'


class FakeRoot:
    def __init__(self):
        self.bitmaps = []
        self.photos = []
    def iconbitmap(self, *, default):
        self.bitmaps.append(default)
    def iconphoto(self, default, image):
        self.photos.append((default, image))


class BrandingAssetTests(unittest.TestCase):
    def test_branding_assets_exist(self):
        self.assertTrue((BRANDING / 'ba_roundcorner_square_fill.svg').is_file())
        self.assertTrue((BRANDING / 'ba_round_corner_small_square_fill-800.png').is_file())
        self.assertTrue((BRANDING / 'kr_book_to_audio.ico').is_file())

    def test_ico_contains_required_windows_sizes(self):
        with Image.open(BRANDING / 'kr_book_to_audio.ico') as image:
            sizes = set(image.ico.sizes())
        required = {(16,16),(20,20),(24,24),(32,32),(40,40),(48,48),(64,64),(128,128),(256,256)}
        self.assertTrue(required.issubset(sizes), (required, sizes))

    def test_asset_resolver_finds_frozen_source_assets(self):
        self.assertEqual(branding_asset_path('kr_book_to_audio.ico'), BRANDING / 'kr_book_to_audio.ico')

    def test_icon_setup_uses_ico_and_png(self):
        root = FakeRoot()
        image = object()
        self.assertTrue(apply_window_icon(root, image_loader=lambda _path: image))
        self.assertEqual(len(root.bitmaps), 1)
        self.assertEqual(root.photos, [(True, image)])
        self.assertIs(root._kr_book_to_audio_icon, image)

    def test_missing_assets_do_not_block_startup(self):
        root = FakeRoot()
        self.assertFalse(apply_window_icon(root, resolver=lambda _name: None, image_loader=lambda _path: object()))
        self.assertFalse(root.bitmaps)
        self.assertFalse(root.photos)


if __name__ == '__main__':
    unittest.main()
