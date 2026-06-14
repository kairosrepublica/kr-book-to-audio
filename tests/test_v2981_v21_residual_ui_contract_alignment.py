from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]

class V21ResidualUiContractAlignmentTests(unittest.TestCase):
    def test_progress_fixtures_track_v20_current_item_bar(self):
        for relative in (
            'tests/test_runtime_visibility.py',
            'tests/test_v296_owner_ui_shell_contract.py',
            'tests/test_v297_windows_default_ux_state_machine.py',
        ):
            source = (ROOT / relative).read_text(encoding='utf-8')
            self.assertIn('self.status_current_progress = ttk.Progressbar', source)
            self.assertNotIn("self.assertIn('self.status_overall_progress = ttk.Progressbar', source)", source)

    def test_owner_footer_fixture_is_advisory_only(self):
        source = (ROOT / 'tests' / 'test_v296_owner_ui_shell_contract.py').read_text(encoding='utf-8')
        self.assertIn('test_cosmetic_footer_is_advisory_non_blocking', source)
        self.assertNotIn("self.assertIn('COPYRIGHT", source)

if __name__ == '__main__': unittest.main()
