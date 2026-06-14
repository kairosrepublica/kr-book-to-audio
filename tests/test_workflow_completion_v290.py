import unittest
from kr_book_to_audio.workflow_completion_ui import derive_audio_action_plan, derive_cleanup_action_plan, single_part_export_receipt


class WorkflowCompletionV290Tests(unittest.TestCase):
    def test_cleanup_recommendation_enables_apply_all(self):
        plan=derive_cleanup_action_plan({'repeated_headers_and_junk':{'status':'recommended'},'metadata_datetime_tags':{'status':'not-recommended'}})
        self.assertTrue(plan.apply_all_enabled); self.assertEqual(plan.roles['cleanup_junk'],'recommended')

    def test_cleanup_without_recommendation_blocks_apply_all(self):
        plan=derive_cleanup_action_plan({'repeated_headers_and_junk':{'status':'not-recommended'},'metadata_datetime_tags':{'status':'not-recommended'}})
        self.assertFalse(plan.apply_all_enabled)

    def test_part1_preview_requires_explicit_approve_or_reject(self):
        plan=derive_audio_action_plan(source_selected=True,job_ready=True,proofread_approved=True,parts_total=2,part1_ready=True,preview_approved=False,all_parts_ready=False,export_verified=False,failed_parts=False,running=False,settings_locked=True)
        self.assertEqual(plan.roles['approve_preview'],'approve'); self.assertEqual(plan.roles['reject_preview'],'reject'); self.assertEqual(plan.reload_role,'next'); self.assertTrue(plan.settings_locked)

    def test_single_part_export_skips_synthesize_and_merge_ui(self):
        plan=derive_audio_action_plan(source_selected=True,job_ready=True,proofread_approved=True,parts_total=1,part1_ready=True,preview_approved=True,all_parts_ready=True,export_verified=True,failed_parts=False,running=False,settings_locked=True)
        self.assertEqual(plan.roles['synthesize'],'skipped'); self.assertEqual(plan.roles['merge'],'skipped'); self.assertEqual(plan.roles['open_export'],'next')

    def test_multi_part_approval_highlights_synthesize(self):
        plan=derive_audio_action_plan(source_selected=True,job_ready=True,proofread_approved=True,parts_total=3,part1_ready=True,preview_approved=True,all_parts_ready=False,export_verified=False,failed_parts=False,running=False,settings_locked=True)
        self.assertEqual(plan.roles['synthesize'],'next')

    def test_audio_preview_is_blocked_until_reviewed_text_is_approved(self):
        plan=derive_audio_action_plan(source_selected=True,job_ready=True,proofread_approved=False,parts_total=2,part1_ready=False,preview_approved=False,all_parts_ready=False,export_verified=False,failed_parts=False,running=False,settings_locked=False)
        self.assertEqual(plan.roles['preview'],'blocked'); self.assertIn('Approve reviewed text',plan.banner)

    def test_cleanup_is_blocked_until_job_exists(self):
        plan=derive_cleanup_action_plan({'repeated_headers_and_junk':{'status':'recommended'}},available=False)
        self.assertEqual(plan.roles['cleanup_junk'],'blocked'); self.assertFalse(plan.apply_all_enabled)

    def test_single_part_receipt_is_explicit(self):
        receipt=single_part_export_receipt(parts_total=1)
        self.assertEqual(receipt,{'single_part_direct_export':True,'synthesize_all_skipped':True,'merge_ui_skipped':True,'source_part':1})

if __name__=='__main__': unittest.main()
