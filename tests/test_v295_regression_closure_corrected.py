from __future__ import annotations
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]


class V295RegressionClosureCorrectedTests(unittest.TestCase):
    def test_ocr_failure_receipt_imports_datetime_timezone(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'ocr.py').read_text(encoding='utf-8')
        self.assertIn('from datetime import datetime, timezone', source)
        self.assertIn('datetime.now(timezone.utc)', source)

    def test_edge_sample_cache_uses_central_durable_replace(self):
        source = (ROOT / 'src' / 'kr_book_to_audio' / 'edge_voice_samples.py').read_text(encoding='utf-8')
        self.assertIn('from .durable_io import replace_with_retry', source)
        self.assertNotIn('os.replace(', source)
        self.assertGreaterEqual(source.count('replace_with_retry('), 2)

    def test_stale_assertions_are_removed(self):
        local = (ROOT / 'tests' / 'test_v292_local_production_closure.py').read_text(encoding='utf-8')
        self.assertIn("self.reload_button = button(workspace, 'Reload book'", local)
        self.assertNotIn("self.reload_button = tk.Button(recent, text='Reload'", local)
        self.assertNotIn("self.reload_button = button(paths, 'Reload book'", local)

    def test_repaired_fixture_assertions_are_not_self_contradictory(self):
        targets = (
            (ROOT / 'tests' / 'test_v292_local_production_closure.py', 'test_reload_is_top_level'),
            (ROOT / 'tests' / 'test_v292_offline_visibility_closure.py', 'test_prejob_diagnostics_and_top_level_reload_remain_present'),
            (ROOT / 'tests' / 'test_v292_regression_closure_finalizer.py', 'test_tesseract_attempt_label_is_current'),
        )
        for path, function_name in targets:
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name]
            self.assertEqual(len(functions), 1, f'{path.name}::{function_name}')
            positive = set()
            negative = set()
            for node in ast.walk(functions[0]):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or not node.args:
                    continue
                if node.func.attr not in {'assertIn', 'assertNotIn'}:
                    continue
                token = node.args[0]
                if isinstance(token, ast.Constant) and isinstance(token.value, str):
                    (positive if node.func.attr == 'assertIn' else negative).add(token.value)
            self.assertFalse(positive & negative, f'{path.name}::{function_name}: {sorted(positive & negative)}')


if __name__ == '__main__':
    unittest.main()
