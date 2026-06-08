from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CIReleaseContractTests(unittest.TestCase):
    def test_workflow_uses_clean_test_extra_main_only_push_and_node24_actions(self):
        workflow = (ROOT / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
        self.assertIn('actions/checkout@v6', workflow)
        self.assertIn('actions/setup-python@v6', workflow)
        self.assertIn('python -m pip install -e .[test]', workflow)
        self.assertIn('branches:\n      - main', workflow)
        self.assertIn('workflow_dispatch:', workflow)
        self.assertNotIn('push:\n  pull_request:', workflow)

    def test_pyproject_declares_pillow_test_extra_and_packaged_branding_assets(self):
        pyproject = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
        self.assertIn('test = ["Pillow>=10"]', pyproject)
        self.assertIn('[tool.setuptools.package-data]', pyproject)
        self.assertIn('kr_book_to_audio = ["assets/branding/*"]', pyproject)


if __name__ == '__main__':
    unittest.main()
