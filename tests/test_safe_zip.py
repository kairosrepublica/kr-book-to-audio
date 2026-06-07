import tempfile
import unittest
import zipfile
from pathlib import Path
from kr_book_to_audio.utils import safe_extract_zip

class SafeZipTests(unittest.TestCase):
    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); zpath = root / 'bad.zip'
            with zipfile.ZipFile(zpath, 'w') as z: z.writestr('../escape.txt', 'bad')
            with self.assertRaises(ValueError): safe_extract_zip(zpath, root / 'out')

if __name__ == '__main__': unittest.main()
