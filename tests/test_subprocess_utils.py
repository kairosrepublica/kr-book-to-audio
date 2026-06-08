from __future__ import annotations
from pathlib import Path
from unittest.mock import patch
import inspect
import subprocess
import unittest
from kr_book_to_audio import subprocess_utils


class DummyStartupInfo:
    def __init__(self):
        self.dwFlags = 0
        self.wShowWindow = 99


class HiddenSubprocessTests(unittest.TestCase):
    def test_non_windows_kwargs_are_unchanged(self):
        with patch.object(subprocess_utils.os, 'name', 'posix'):
            self.assertEqual(subprocess_utils.hidden_subprocess_kwargs({'text': True}), {'text': True})

    def test_windows_kwargs_suppress_console(self):
        with patch.object(subprocess_utils.os, 'name', 'nt'), \
             patch.object(subprocess_utils.subprocess, 'STARTUPINFO', DummyStartupInfo, create=True), \
             patch.object(subprocess_utils.subprocess, 'CREATE_NO_WINDOW', 0x08000000, create=True), \
             patch.object(subprocess_utils.subprocess, 'STARTF_USESHOWWINDOW', 0x1, create=True), \
             patch.object(subprocess_utils.subprocess, 'SW_HIDE', 0, create=True):
            kwargs = subprocess_utils.hidden_subprocess_kwargs({'text': True})
        self.assertEqual(kwargs['creationflags'] & 0x08000000, 0x08000000)
        self.assertEqual(kwargs['startupinfo'].dwFlags & 0x1, 0x1)
        self.assertEqual(kwargs['startupinfo'].wShowWindow, 0)

    def test_run_hidden_cli_emits_operation_scoped_trace(self):
        events = []
        result = subprocess.CompletedProcess(['demo'], 0, stdout='ok', stderr='')
        with patch.object(subprocess_utils.subprocess, 'run', return_value=result):
            with subprocess_utils.process_trace(events.append, operation='Prepare text'):
                actual = subprocess_utils.run_hidden_cli(['demo', '--flag'], text=True)
        self.assertIs(actual, result)
        self.assertEqual(events[0]['phase'], 'start')
        self.assertEqual(events[0]['tool'], 'demo')
        self.assertEqual(events[0]['operation'], 'Prepare text')
        self.assertEqual(events[-1]['phase'], 'finish')


    def test_cleanup_pipeline_does_not_spawn_child_processes(self):
        package_root = Path(__file__).resolve().parents[1] / 'src' / 'kr_book_to_audio'
        text = (package_root / 'pipeline.py').read_text(encoding='utf-8')
        self.assertNotIn('subprocess.run(', text)
        self.assertNotIn('subprocess.Popen(', text)
        self.assertNotIn('run_hidden_cli(', text)

    def test_governed_modules_do_not_call_raw_subprocess(self):
        package_root = Path(__file__).resolve().parents[1] / 'src' / 'kr_book_to_audio'
        governed = ['audio.py', 'extractors.py', 'ocr.py', 'providers.py']
        for name in governed:
            text = (package_root / name).read_text(encoding='utf-8')
            self.assertNotIn('subprocess.run(', text, name)
            self.assertNotIn('subprocess.Popen(', text, name)
        adapter = inspect.getsource(subprocess_utils)
        self.assertIn('subprocess.run(', adapter)
        self.assertIn('subprocess.Popen(', adapter)


if __name__ == '__main__':
    unittest.main()
