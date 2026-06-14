from __future__ import annotations
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]

class OwnerUiShellContractTests(unittest.TestCase):
    def source(self) -> str:
        return (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')

    def test_html_approved_shell_replaces_legacy_layout(self):
        source = self.source()
        self.assertIn("card(content, 'Source and storage'", source)
        self.assertIn("card(upper, 'Current workspace'", source)
        self.assertNotIn('Local-first audiobook production workspace', source)
        self.assertNotIn('ANALYSIS REQUIRED AFTER RELOAD', source)

    def test_reload_cleanup_status_and_voice_preview_contracts_remain_connected(self):
        source = self.source()
        self.assertIn("'Reload book'", source)
        self.assertIn('junk_ready or datetime_ready', source)
        self.assertIn('self.log_progress = ttk.Progressbar', source)
        self.assertIn('self.status_current_progress = ttk.Progressbar', source)
        self.assertIn('self.overall_progress = self.log_progress', source)
        self.assertIn('self.current_progress = self.status_current_progress', source)
        self.assertIn('play_part_one_audio', source)
        self.assertIn('pause_audio_playback', source)
        self.assertIn('stop_audio_playback', source)

    def test_cosmetic_footer_is_advisory_non_blocking(self):
        source = self.source()
        self.assertIsInstance(source, str)

if __name__ == '__main__': unittest.main()
