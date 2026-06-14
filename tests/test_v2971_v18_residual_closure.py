from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]

class V18ResidualClosureTests(unittest.TestCase):
    def test_owner_ui_fixture_uses_existing_source_helper(self):
        source = (ROOT / 'tests' / 'test_v296_owner_ui_shell_contract.py').read_text(encoding='utf-8')
        self.assertIn('def source(self) -> str:', source)
        self.assertNotIn('self.gui()', source)

    def test_v16_reload_fixture_tracks_workspace_placement(self):
        source = (ROOT / 'tests' / 'test_v2962_v16_residual_fixture_domain.py').read_text(encoding='utf-8')
        self.assertIn('self.assertIn("self.reload_button = button(workspace, \'Reload book\'", source)', source)
        self.assertIn('self.assertNotIn("self.reload_button = button(paths, \'Reload book\'", source)', source)

    def test_runtime_visibility_fixture_uses_windows_default_state_model(self):
        source = (ROOT / 'tests' / 'test_runtime_visibility.py').read_text(encoding='utf-8')
        self.assertIn("self.assertIn('self.log_progress = ttk.Progressbar', source)", source)
        self.assertIn("self.assertIn('self.status_current_progress = ttk.Progressbar', source)", source)
        self.assertIn("self.assertIn('self.current_progress = self.status_current_progress', source)", source)
        self.assertIn("self.assertNotIn('self.current_progress = ttk.Progressbar', source)", source)

if __name__ == '__main__': unittest.main()
