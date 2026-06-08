import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kr_book_to_audio import gui
from kr_book_to_audio.models import JobPaths


class GuiOpenPathTests(unittest.TestCase):
    def test_open_existing_directory_uses_platform_file_manager(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            if os.name == 'nt':
                with patch.object(gui.os, 'startfile') as startfile, patch.object(gui.subprocess, 'Popen') as popen:
                    gui.open_in_file_manager(folder)
                startfile.assert_called_once_with(folder)
                popen.assert_not_called()
            else:
                with patch.object(gui.subprocess, 'Popen') as popen:
                    gui.open_in_file_manager(folder)
                popen.assert_called_once_with(['xdg-open', str(folder)])

    def test_open_existing_directory_windows_branch_uses_startfile(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            # gui.Path is patched so this Windows-branch fixture remains safe on a POSIX test host.
            with patch.object(gui, 'Path', return_value=folder), \
                 patch.object(gui.os, 'name', 'nt'), \
                 patch.object(gui.os, 'startfile', create=True) as startfile, \
                 patch.object(gui.subprocess, 'Popen') as popen:
                gui.open_in_file_manager(folder)
            startfile.assert_called_once_with(folder)
            popen.assert_not_called()

    def test_open_missing_path_is_actionable_and_does_not_create_it(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / 'missing'
            with self.assertRaisesRegex(RuntimeError, 'does not exist yet'):
                gui.open_in_file_manager(missing)
            self.assertFalse(missing.exists())

    def test_open_selected_output_does_not_create_misleading_empty_export(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            job = JobPaths.from_root(root / 'job', root / 'exports' / 'job-export')
            job.ensure()
            app = object.__new__(gui.App)
            app._selected_recent = lambda: {'job_root': str(job.root)}
            app._log_event = lambda _text: None
            with patch.object(gui.messagebox, 'askyesno', return_value=False):
                app.open_selected_output()
            self.assertFalse(job.export.exists())

    def test_open_selected_output_offers_working_audio_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            job = JobPaths.from_root(root / 'job', root / 'exports' / 'job-export')
            job.ensure()
            app = object.__new__(gui.App)
            app._selected_recent = lambda: {'job_root': str(job.root)}
            app._log_event = lambda _text: None
            with patch.object(gui.messagebox, 'askyesno', return_value=True), patch.object(gui, 'open_in_file_manager') as opened:
                app.open_selected_output()
            opened.assert_called_once_with(job.parts_audio)
            self.assertFalse(job.export.exists())


if __name__ == '__main__':
    unittest.main()
