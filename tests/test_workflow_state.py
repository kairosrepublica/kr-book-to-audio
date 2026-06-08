from __future__ import annotations
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest
from kr_book_to_audio.manifest import load_manifest, save_manifest
from kr_book_to_audio.workflow_state import derive_workflow_state
from helpers import approve_fake_audio, make_prepared_job


class WorkflowStateTests(unittest.TestCase):
    def test_new_source_marks_prepare_as_next(self):
        state = derive_workflow_state(None, source_selected=True)
        self.assertEqual(state['prepare'].state, 'next')
        self.assertEqual(state['preview'].state, 'blocked')

    def test_prepared_job_marks_review_as_next_and_cleanup_available(self):
        with TemporaryDirectory() as td:
            job = make_prepared_job(Path(td), '这是一个用于测试工作流状态的完整段落，包含足够多的文字内容，并且能够保留为可朗读文本。' * 8)
            manifest = load_manifest(job)
            manifest['gates']['proofread']['approved_sha256'] = None
            manifest['cleanup']['analysis'] = {'repeated_headers_and_junk': {'status': 'recommended', 'count': 2}}
            save_manifest(job, manifest)
            state = derive_workflow_state(job, source_selected=True)
            self.assertEqual(state['prepare'].state, 'completed')
            self.assertEqual(state['open_cleaned'].state, 'next')
            self.assertEqual(state['cleanup_all'].state, 'optional')
            self.assertEqual(state['preview'].state, 'blocked')

    def test_audio_complete_marks_merge_next_and_export_available(self):
        with TemporaryDirectory() as td:
            job = make_prepared_job(Path(td), '这是一个用于验证音频完成状态的完整句子，包含多个词语和足够长度。' * 30)
            approve_fake_audio(job)
            manifest = load_manifest(job)
            manifest['export'] = {'status': 'verified'}
            save_manifest(job, manifest)
            state = derive_workflow_state(job, source_selected=True)
            self.assertEqual(state['synthesize'].state, 'completed')
            self.assertEqual(state['merge'].state, 'next')
            self.assertEqual(state['open_export'].state, 'next')

    def test_running_overlay_is_operation_derived(self):
        state = derive_workflow_state(None, source_selected=True, running_label='Prepare text')
        self.assertEqual(state['prepare'].state, 'running')


if __name__ == '__main__':
    unittest.main()
