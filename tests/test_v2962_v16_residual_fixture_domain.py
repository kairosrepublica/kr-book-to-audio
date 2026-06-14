from __future__ import annotations
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]

class V16ResidualFixtureDomainTests(unittest.TestCase):
    def test_root_definitions_exist_for_migrated_fixtures(self):
        for relative in (
            'tests/test_fixed_shell_wheel_scroll.py',
            'tests/test_gui_surface.py',
            'tests/test_v292_local_production_closure.py',
        ):
            source = (ROOT / relative).read_text(encoding='utf-8')
            self.assertIn('ROOT = Path(__file__).resolve().parents[1]', source)

    def test_final_reload_assertion_is_html_approved(self):
        source = (ROOT / 'tests' / 'test_v292_local_production_closure.py').read_text(encoding='utf-8')
        self.assertIn("self.reload_button = button(workspace, 'Reload book'", source)
        self.assertNotIn("self.reload_button = tk.Button(recent, text='Reload'", source)
        self.assertNotIn("self.reload_button = button(paths, 'Reload book'", source)

if __name__ == '__main__':
    unittest.main()
