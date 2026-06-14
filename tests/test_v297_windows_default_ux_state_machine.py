from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]

class V297WindowsDefaultUxStateMachineTests(unittest.TestCase):
    def gui(self) -> str:
        return (ROOT / 'src' / 'kr_book_to_audio' / 'gui.py').read_text(encoding='utf-8')

    def test_shell_starts_with_source_and_uses_default_windows_visual_language(self):
        source = self.gui()
        self.assertNotIn("'Local-first audiobook production workspace'", source)
        self.assertNotIn("'ANALYSIS REQUIRED AFTER RELOAD'", source)
        self.assertIn("card(content, 'Source and storage'", source)
        self.assertIn("card(upper, 'Current workspace'", source)
        self.assertIn("'Reload book'", source)
        self.assertIn("'Refresh voice samples'", source)
        self.assertIn("'Keep computer awake during OCR or TTS'", source)
        self.assertIn("'SystemButtonFace'", source)
        self.assertIn("'SystemHighlight'", source)

    def test_cleanup_state_machine_and_sliders_are_present(self):
        source = self.gui()
        self.assertIn('junk_ready or datetime_ready', source)
        self.assertIn('self.rate_scale = tk.Scale', source)
        self.assertIn('self.volume_scale = tk.Scale', source)

    def test_log_status_progress_and_audio_controls_are_present(self):
        source = self.gui()
        self.assertIn('self.log_progress = ttk.Progressbar', source)
        self.assertIn('self.status_current_progress = ttk.Progressbar', source)
        self.assertIn('self.overall_progress = self.log_progress', source)
        self.assertIn('self.current_progress = self.status_current_progress', source)
        self.assertIn("'Part 1 playback'", source)
        for token in ('play_part_one_audio', 'pause_audio_playback', 'stop_audio_playback'):
            self.assertIn(token, source)

if __name__ == '__main__': unittest.main()
