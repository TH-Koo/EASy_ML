import unittest

from analysis_engine import capability_fits_category


class CategoryScopeTest(unittest.TestCase):
    def test_out_of_category_capability_is_not_a_claim(self):
        # TV 상세페이지의 "맞춤"이 세탁 코스 패턴에 걸리던 사례
        self.assertFalse(capability_fits_category("CAP_AI_WASH_COURSE", "LED TV"))
        self.assertFalse(capability_fits_category("CAP_AI_WASH_COURSE", "공기청정기"))
        self.assertFalse(capability_fits_category("CAP_DRY_COURSE", "스탠드 에어컨"))

    def test_matching_category_keeps_claim(self):
        self.assertTrue(capability_fits_category("CAP_AI_WASH_COURSE", "올인원 세탁건조기"))
        self.assertTrue(capability_fits_category("CAP_DRY_COURSE", "의류건조기"))
        self.assertTrue(capability_fits_category("CAP_DISPLAY_OPTIMIZATION", "QLED TV"))
        self.assertTrue(capability_fits_category("CAP_DISHWASH_COURSE", "식기세척기"))

    def test_unscoped_capability_is_never_filtered(self):
        self.assertTrue(capability_fits_category("CAP_SPEECH_RECOGNITION", "LED TV"))

    def test_unknown_category_does_not_filter(self):
        # 카테고리가 없거나, 예전 크롤러처럼 메뉴 글자가 들어온 경우
        self.assertTrue(capability_fits_category("CAP_AI_WASH_COURSE", ""))
        self.assertTrue(capability_fits_category("CAP_AI_WASH_COURSE", "다나와 홈 가전 메뉴"))


if __name__ == "__main__":
    unittest.main()
