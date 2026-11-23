import os
import sys
import unittest
from unittest import mock

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "logic"))
import dart_scraper  # noqa: E402
from analysis_engine import bundle_to_evidence_records  # noqa: E402

SAMPLE_XML = (
    "<DOCUMENT><TITLE>I. 회사의 개요</TITLE><P>회사 개요 문장입니다.</P>"
    "<TITLE>II. 사업의 내용</TITLE>"
    "<P>ㆍAI 맞춤세탁 기능 등을 강화한 Bespoke AI 콤보 출시</P>"
    "<P>업계 최초 온디바이스 AI 최적화 UFS 5.0 개발</P>"
    "<P>TV 업계는 AI 기술을 적극 도입하고 있습니다.냉장고 원가가 올랐습니다.</P>"
    "<TITLE>III. 재무에 관한 사항</TITLE><P>재무 AI 문장은 넣지 않습니다.</P></DOCUMENT>"
)


class BusinessSentenceTest(unittest.TestCase):
    def test_only_business_section_is_split(self):
        sentences = dart_scraper._business_section_sentences(SAMPLE_XML)
        self.assertIn("AI 맞춤세탁 기능 등을 강화한 Bespoke AI 콤보 출시", sentences)
        # 마침표 뒤 띄어쓰기가 없어도 문장이 갈린다
        self.assertIn("TV 업계는 AI 기술을 적극 도입하고 있습니다.", sentences)
        self.assertFalse(any("재무" in s for s in sentences))
        self.assertFalse(any("회사 개요" in s for s in sentences))

    def _cached_text(self):
        sentences = dart_scraper._business_section_sentences(SAMPLE_XML)
        return ("공시 목록\n" + dart_scraper._REPORT_MARKER + "20261116001482|분기보고서 (2026.09)\n"
                + dart_scraper._BUSINESS_MARKER + "\n" + "\n".join(sentences))

    def test_category_keeps_only_matching_feature_sentences(self):
        picked = dart_scraper._extract_feature_sentences(self._cached_text(), "드럼세탁기", "WF80H24ADS")
        self.assertEqual(picked, ["AI 맞춤세탁 기능 등을 강화한 Bespoke AI 콤보 출시"])

    def test_unknown_category_keeps_all_feature_sentences(self):
        picked = dart_scraper._extract_feature_sentences(self._cached_text(), "", "")
        self.assertEqual(len(picked), 3)  # AI 문장 3개, AI 가 없는 냉장고 문장은 빠진다

    def test_report_meta(self):
        self.assertEqual(dart_scraper._report_meta(self._cached_text()),
                         ("20261116001482", "분기보고서 (2026.09)"))

    def test_check_returns_sentence_records(self):
        codes = pd.DataFrame({"corp_code": ["00126380"], "corp_name": ["삼성전자"], "stock_code": ["005930"]})
        reader = mock.Mock(corp_codes=codes)
        with mock.patch.object(dart_scraper, "DART_KEY", "k"), \
                mock.patch.object(dart_scraper, "_open_dart_reader", return_value=reader), \
                mock.patch.object(dart_scraper, "_load_dart_text_cache", return_value=self._cached_text()):
            result = dart_scraper.check_dart_ai_washing(["삼성전자"], "WF80H24ADS", "드럼세탁기")
        self.assertEqual(result["status"], "공시 실적 검증 완료")
        self.assertEqual(len(result["records"]), 1)
        self.assertIn("rcpNo=20261116001482", result["records"][0]["url"])


class DartRecordsInEngineTest(unittest.TestCase):
    def test_each_sentence_becomes_one_record(self):
        dart_result = {
            "status": "공시 실적 검증 완료",
            "records": [
                {"title": "AI 맞춤세탁 기능 강화", "text": "AI 맞춤세탁 기능 강화"},
                {"title": "스마트싱스 연동 세탁기", "text": "스마트싱스 연동 세탁기"},
            ],
        }
        records = bundle_to_evidence_records(dart_result=dart_result, target_company_name="삼성전자")
        dart = [r for r in records if r.source_type == "dart"]
        self.assertEqual(len(dart), 2)
        self.assertTrue(all(r.relation_type == "company_general" for r in dart))


if __name__ == "__main__":
    unittest.main()
