from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / 'src' / 'kr_book_to_audio' / 'gui.py'
CONFIG = ROOT / 'src' / 'kr_book_to_audio' / 'config.py'


class V310PrepareModeUiTests(unittest.TestCase):
    def gui(self) -> str:
        return GUI.read_text(encoding='utf-8')

    def test_prepare_mode_selector_replaces_extra_minimal_button(self):
        source = self.gui()
        self.assertIn("'Auto smart cleanup': 'auto'", source)
        self.assertIn("'Minimal preserve layout': 'minimal'", source)
        self.assertIn("'Aggressive OCR cleanup': 'standard'", source)
        self.assertIn("ttk.Radiobutton(prepare_modes, text=label, variable=self.prepare_layout_mode, value=mode_id)", source)
        self.assertIn("self._workflow_button(text_process, 'prepare', 'Prepare text', self.prepare", source)
        self.assertNotIn("Prepare text (minimal)", source)
        self.assertNotIn("prepare_minimal", source)

    def test_each_prepare_mode_has_triangle_hover_help(self):
        source = self.gui()
        self.assertIn("def add_triangle_help", source)
        self.assertIn("text='▸'", source)
        self.assertIn('PREPARE_MODE_TOOLTIPS', source)
        self.assertIn('Default. Use this for most TXT, Markdown and DOCX books.', source)
        self.assertIn('Use only when the TXT has already been manually or AI-cleaned.', source)
        self.assertIn('Use for PDF/OCR/extracted text with many bad line breaks or spacing defects.', source)
        self.assertIn('add_triangle_help(prepare_modes, PREPARE_MODE_TOOLTIPS[mode_id]', source)

    def test_prepare_uses_selected_mode_and_persists_it(self):
        source = self.gui()
        self.assertIn("configured_prepare_mode = str(cfg.get('prepare_layout_mode', 'auto'))", source)
        self.assertIn("self.prepare_layout_mode = tk.StringVar(value=configured_prepare_mode)", source)
        self.assertIn("def _prepare_layout_mode(self) -> str:", source)
        self.assertIn("layout_mode = layout_mode or self._prepare_layout_mode()", source)
        self.assertIn("'prepare_layout_mode': self._prepare_layout_mode()", source)
        self.assertIn("Prepare text ·", source)
        config = CONFIG.read_text(encoding='utf-8')
        self.assertIn("migrated.setdefault('prepare_layout_mode', 'auto')", config)


if __name__ == '__main__':
    unittest.main()
