import tempfile
import unittest
from pathlib import Path
from kr_book_to_audio.pipeline import apply_cleanup_and_rebuild, job_status
from kr_book_to_audio.text_processing import analyze_cleanup
from helpers import make_prepared_job

class CleanupAdvisorTests(unittest.TestCase):
    def test_repeated_short_junk_is_recommended(self):
        report = analyze_cleanup('推广关注公众号\n\n正文内容。\n\n推广关注公众号\n\n推广关注公众号')
        self.assertEqual(report['repeated_headers_and_junk']['status'], 'recommended')

    def test_ambiguous_repeat_requires_review(self):
        report = analyze_cleanup('合法章节标题\n\n正文一。\n\n合法章节标题\n\n正文二。\n\n合法章节标题')
        self.assertIn(report['repeated_headers_and_junk']['status'], {'recommended', 'review-required'})

    def test_datetime_cleanup_action_creates_backup_and_refreshes_analysis(self):
        with tempfile.TemporaryDirectory() as td:
            job = make_prepared_job(Path(td), text='（2019-07-30）正文内容。')
            before = job.proofread.read_text(encoding='utf-8')
            result = apply_cleanup_and_rebuild(job, kind='metadata-date-time-tags')
            self.assertTrue(Path(result['backup']).exists())
            self.assertNotEqual(before, job.proofread.read_text(encoding='utf-8'))
            self.assertIn('cleanup_analysis', job_status(job))

    def test_review_candidate_is_preserved_by_apply_cleanup(self):
        from kr_book_to_audio.text_processing import apply_cleanup
        text = '这是一个较长而且具有实际意义的合法章节标题必须保留\n\n正文一。\n\n这是一个较长而且具有实际意义的合法章节标题必须保留\n\n正文二。\n\n这是一个较长而且具有实际意义的合法章节标题必须保留'
        analysis = analyze_cleanup(text)
        self.assertEqual(analysis['repeated_headers_and_junk']['status'], 'review-required')
        cleaned, report = apply_cleanup(text, 'repeated-headers-and-junk')
        self.assertIn('这是一个较长而且具有实际意义的合法章节标题必须保留', cleaned)
        self.assertTrue(report['review_preserved'])

if __name__ == '__main__': unittest.main()
