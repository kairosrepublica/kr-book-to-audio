from __future__ import annotations
import ast
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]

class V19MetaFixtureFalsePositiveClosureTests(unittest.TestCase):
    def _v18_method(self, method_name: str) -> ast.FunctionDef:
        source = (ROOT / 'tests' / 'test_v2971_v18_residual_closure.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == method_name:
                return node
        raise AssertionError(f'missing V18 meta-fixture method: {method_name}')

    def _assert_no_direct_assert_not_in(self, method_name: str) -> None:
        method = self._v18_method(method_name)
        calls = [
            node for node in ast.walk(method)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'assertNotIn'
        ]
        self.assertEqual([], calls)

    def test_v18_reload_meta_fixture_has_no_self_referential_absence_scan(self):
        self._assert_no_direct_assert_not_in('test_v16_reload_fixture_tracks_workspace_placement')

    def test_v18_runtime_visibility_meta_fixture_has_no_self_referential_absence_scan(self):
        self._assert_no_direct_assert_not_in('test_runtime_visibility_fixture_uses_windows_default_state_model')

if __name__ == '__main__':
    unittest.main()
