import unittest
from kr_book_to_audio.text_processing import clean_text, strip_metadata_datetime_tags


class DateTimeCleanupTests(unittest.TestCase):
    def test_metadata_like_bracketed_date_is_removed(self):
        self.assertEqual(strip_metadata_datetime_tags('标题（2019-07-30）正文。'), '标题正文。')

    def test_metadata_like_bracketed_date_time_is_removed(self):
        self.assertEqual(strip_metadata_datetime_tags('标题[2024/06/18 09:30]正文。'), '标题正文。')

    def test_metadata_like_bare_timestamp_is_removed(self):
        self.assertEqual(strip_metadata_datetime_tags('标题2026-06-08 01:45:22正文。'), '标题正文。')

    def test_ordinary_prose_dates_and_times_are_preserved(self):
        text = '公司成立于 1998 年。会议将在下午 3 点召开。2024 年市场发生了明显变化。'
        self.assertEqual(strip_metadata_datetime_tags(text), text)

    def test_cleanup_option_is_applied_inside_clean_text(self):
        cleaned, stats = clean_text('标题（2019-07-30）正文内容完整。', strip_datetime_tags=True)
        self.assertEqual(cleaned, '标题正文内容完整。')
        self.assertTrue(stats['metadata_datetime_cleanup'])


if __name__ == '__main__':
    unittest.main()
