import errno
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from kr_book_to_audio.durable_io import cleanup_stale_partials, replace_with_retry, unique_partial_path, write_text


class DurableIoTests(unittest.TestCase):
    def test_transient_permission_error_retries_and_preserves_commit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root / 'state.tmp'; destination = root / 'state.json'
            source.write_text('new', encoding='utf-8'); destination.write_text('old', encoding='utf-8')
            import os
            real_replace = os.replace
            calls = {'count': 0}
            def flaky(src, dst):
                calls['count'] += 1
                if calls['count'] < 3:
                    raise PermissionError('transient lock')
                return real_replace(src, dst)
            with patch('kr_book_to_audio.durable_io.os.replace', side_effect=flaky):
                replace_with_retry(source, destination, initial_delay=0)
            self.assertEqual(destination.read_text(encoding='utf-8'), 'new')
            self.assertEqual(calls['count'], 3)

    def test_persistent_permission_error_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); source = root / 'state.tmp'; destination = root / 'state.json'
            source.write_text('new', encoding='utf-8'); destination.write_text('old', encoding='utf-8')
            with patch('kr_book_to_audio.durable_io.os.replace', side_effect=PermissionError('permanent lock')):
                with self.assertRaises(PermissionError):
                    replace_with_retry(source, destination, attempts=2, initial_delay=0)
            self.assertEqual(destination.read_text(encoding='utf-8'), 'old')
            self.assertFalse(source.exists())

    def test_same_path_concurrent_writes_are_serialized(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / '中文目录' / 'state.json'
            errors=[]
            def worker(value):
                try: write_text(target, value)
                except Exception as exc: errors.append(exc)
            threads=[threading.Thread(target=worker,args=(f'value-{i}',)) for i in range(8)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            self.assertFalse(errors)
            self.assertTrue(target.read_text(encoding='utf-8').startswith('value-'))
            self.assertEqual(list(target.parent.glob('*.partial')), [])

    def test_stale_unique_partial_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / 'manifest.json'
            partial = unique_partial_path(target); partial.write_text('stale', encoding='utf-8')
            removed = cleanup_stale_partials(target, older_than_seconds=0)
            self.assertIn(partial.name, removed)
            self.assertFalse(partial.exists())

    def test_disk_full_write_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / 'state.json'
            target.write_text('old', encoding='utf-8')
            with patch('pathlib.Path.open', side_effect=OSError(errno.ENOSPC, 'disk full')):
                with self.assertRaises(OSError):
                    write_text(target, 'new')
            self.assertEqual(target.read_text(encoding='utf-8'), 'old')

    def test_unique_temp_file_avoids_fixed_partial_collision(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / 'job_manifest.json'
            first = unique_partial_path(target)
            second = unique_partial_path(target)
            self.assertNotEqual(first, second)
            self.assertTrue(first.name.startswith('job_manifest.json.'))
            self.assertTrue(first.name.endswith('.partial'))
