from pathlib import Path
import ast
import unittest
ROOT = Path(__file__).resolve().parents[1]

class V22SingleCanonicalFixtureWriterTests(unittest.TestCase):
    def test_runtime_visibility_fixture_tracks_current_progress_model(self):
        source = (ROOT / 'tests' / 'test_runtime_visibility.py').read_text(encoding='utf-8')
        self.assertIn("self.assertIn('self.log_progress = ttk.Progressbar', source)", source)
        self.assertIn("self.assertIn('self.status_current_progress = ttk.Progressbar', source)", source)
        self.assertIn("self.assertIn('self.current_progress = self.status_current_progress', source)", source)
        self.assertIn("self.assertNotIn('self.current_progress = ttk.Progressbar', source)", source)
        self.assertNotIn("self.assertNotIn(\"'green':\", source)", source)

    def test_v18_meta_fixture_tracks_current_progress_semantics(self):
        source = (ROOT / 'tests' / 'test_v2971_v18_residual_closure.py').read_text(encoding='utf-8')
        self.assertIn("self.assertIn(\"self.assertIn('self.log_progress = ttk.Progressbar', source)\", source)", source)
        self.assertIn("self.assertIn(\"self.assertIn('self.status_current_progress = ttk.Progressbar', source)\", source)", source)
        self.assertNotIn("self.assertIn('self.assertNotIn(\"\\'green\\':\", source)', source)", source)

    def test_v18_runtime_visibility_meta_fixture_has_no_direct_assert_not_in(self):
        source = (ROOT / 'tests' / 'test_v2971_v18_residual_closure.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        method = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == 'test_runtime_visibility_fixture_uses_windows_default_state_model'
        )
        direct = [
            node for node in ast.walk(method)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'assertNotIn'
        ]
        self.assertEqual([], direct)

if __name__ == '__main__': unittest.main()
