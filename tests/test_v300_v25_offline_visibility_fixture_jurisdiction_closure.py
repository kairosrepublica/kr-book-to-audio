from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'tests' / 'test_v292_offline_visibility_closure.py'
GUI = ROOT / 'src' / 'kr_book_to_audio' / 'gui.py'
METHOD = 'test_gui_uses_local_model_language_and_activity_heartbeat'


class V300V25OfflineVisibilityFixtureJurisdictionClosureTests(unittest.TestCase):
    def target_method(self):
        tree = ast.parse(TARGET.read_text(encoding='utf-8'), filename=str(TARGET))
        methods = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == METHOD]
        self.assertEqual(len(methods), 1)
        return methods[0]

    def test_runtime_keeps_semantic_ocr_heartbeat_contract(self):
        gui = GUI.read_text(encoding='utf-8')
        for token in (
            'language: {analysis.language}',
            'def _ocr_progress_tick(self, token: int) -> None:',
            'heartbeat_due = from_tick',
            'KR_B2A_OCR_HEARTBEAT_SECONDS',
            "getattr(self, '_last_ocr_heartbeat_at'",
            'Full OCR | page {source_page} / {source_total}',
            'current page {current_pct}%',
            'whole book {overall_pct:.1f}%',
        ):
            self.assertIn(token, gui)

    def test_migrated_fixture_asserts_semantics_not_retired_display_wording(self):
        method = self.target_method()
        constants = {node.value for node in ast.walk(method) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        self.assertNotIn('OCR activity', constants)
        self.assertIn('heartbeat_due = from_tick', constants)
        self.assertIn('KR_B2A_OCR_HEARTBEAT_SECONDS', constants)
        self.assertIn('Full OCR | page {source_page} / {source_total}', constants)
        self.assertIn('current page {current_pct}%', constants)
        self.assertIn('whole book {overall_pct:.1f}%', constants)

    def test_validator_jurisdiction_is_method_scoped(self):
        source = TARGET.read_text(encoding='utf-8')
        self.assertIn(METHOD, source)
        method = self.target_method()
        constants = {node.value for node in ast.walk(method) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        self.assertNotIn('OCR activity', constants)


if __name__ == '__main__':
    unittest.main()
