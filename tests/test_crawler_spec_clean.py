import unittest

from logic.crawler import _clean_spec_value


class SpecValueCleanTest(unittest.TestCase):
    def test_link_text_is_removed_from_manufacturer(self):
        # 새 화면 스펙표의 제조회사 칸. 이 글자가 남으면 회사 조회가 전부 실패했다.
        self.assertEqual(_clean_spec_value("삼성전자 (제조사 웹사이트 바로가기)"), "삼성전자")

    def test_certificate_button_text_is_removed(self):
        self.assertEqual(_clean_spec_value("R-R-SEC-WF80H27K2 인증번호 확인"), "R-R-SEC-WF80H27K2")

    def test_plain_value_is_kept(self):
        self.assertEqual(_clean_spec_value(" 세탁:1등급 "), "세탁:1등급")


if __name__ == "__main__":
    unittest.main()
