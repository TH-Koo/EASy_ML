import unittest
from pathlib import Path
from types import SimpleNamespace

from analysis_engine import EvidenceRecord, OntologyAnalysisEngine
from server import build_claims


class PatentDisplayEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = OntologyAnalysisEngine(str(Path(__file__).resolve().parents[1] / "ontology"))

    def item(self, ident, support=0.5):
        return SimpleNamespace(
            evidence_id=ident, component_name="바닥재/오염도 분석 모델", required_level="required",
            capability_id="CAP_AI_FLOOR_DETECTION", support=support, source_type="kipris",
            component_relevance=0.5, capability_relevance=0.5, relation_weight=0.6,
            relation_type="company_capability", independent_source_key=ident,
        )

    def record(self, ident, title, abstract="", **metadata):
        return EvidenceRecord(source_type="kipris", evidence_id=ident, title=title,
                              text=f"{title} {abstract} AI바닥인식",
                              meta={"초록": abstract, **metadata}, source_record_id=ident)

    def test_vehicle_title_and_search_query_never_prove_floor_relevance(self):
        record = self.record("car", "차량에 장착된 전자 장치 및 이를 통해 차량을 제어하는 방법",
                             search_query="AI바닥인식 오염도")
        row = self.engine._summarize_capability_sources([self.item("car")], [record])[0]
        self.assertIsNone(row["display_record_title"])
        self.assertEqual(row["related_record_count"], 0)
        self.assertEqual(row["matched_record_count"], 1)

    def test_relevant_title_wins_over_a_higher_scoring_unrelated_title(self):
        records = [self.record("car", "차량 제어 장치"),
                   self.record("floor", "바닥재를 판별하는 로봇 청소기 및 제어 방법")]
        row = self.engine._summarize_capability_sources(
            [self.item("car", 0.9), self.item("floor", 0.4)], records)[0]
        self.assertEqual(row["record_id"], "floor")
        self.assertEqual(row["display_record_title"], records[1].title)
        self.assertEqual(row["related_record_count"], 1)

    def test_abstract_match_keeps_count_without_showing_a_generic_title(self):
        record = self.record("abstract", "전자 장치 및 그의 제어 방법", "오염도를 분석하여 청소 강도를 바꾼다")
        row = self.engine._summarize_capability_sources([self.item("abstract")], [record])[0]
        self.assertIsNone(row["display_record_title"])
        self.assertEqual(row["related_record_count"], 1)

    def test_related_count_deduplicates_component_links(self):
        record = self.record("floor", "오염도를 감지하는 청소기")
        row = self.engine._summarize_capability_sources(
            [self.item("floor"), self.item("floor")], [record])[0]
        self.assertEqual(row["related_record_count"], 1)

    def test_speech_function_does_not_accept_ai_keyboard_or_cooling_titles(self):
        items = [self.item("keyboard"), self.item("cooling")]
        for item in items:
            item.capability_id = "CAP_SPEECH_RECOGNITION"
            item.component_name = "음성 인식 엔진(ASR)"
        records = [self.record("keyboard", "AI 키보드를 이용한 사용자 피로도 분석 및 완화 시스템"),
                   self.record("cooling", "펠티어 소자 수냉 냉각수단이 구비되는 액침 냉각시스템")]
        row = self.engine._summarize_capability_sources(items, records)[0]
        self.assertIsNone(row["display_record_title"])
        self.assertEqual(row["related_record_count"], 0)

    def non_patent(self, source, ident, title, **row):
        item = self.item(ident)
        item.source_type = source
        record = EvidenceRecord(source_type=source, evidence_id=ident, title=title,
                                text=f"{title} AI바닥인식", meta={"title": title, **row},
                                source_record_id=ident)
        return item, record

    def test_rra_and_gs_hide_unrelated_titles_like_kipris(self):
        for source in ("rra", "gs"):
            item, record = self.non_patent(source, "x", "특정소출력 무선기기",
                                           search_query="AI바닥인식 오염도")
            row = self.engine._summarize_capability_sources([item], [record])[0]
            self.assertIsNone(row["display_record_title"], source)
            self.assertEqual(row["related_record_count"], 0, source)
            self.assertEqual(row["matched_record_count"], 1, source)

    def test_rra_shows_title_when_it_names_the_function(self):
        item, record = self.non_patent("rra", "floor", "바닥재 판별 로봇 청소기")
        row = self.engine._summarize_capability_sources([item], [record])[0]
        self.assertEqual(row["display_record_title"], "바닥재 판별 로봇 청소기")
        self.assertEqual(row["related_record_count"], 1)

    def test_api_preserves_explicit_zero_and_hidden_title(self):
        claim = build_claims([{
            "positive_claim": True, "supporting_sources": ["kipris"],
            "source_evidence": [{"source": "kipris", "related_record_count": 0,
                                 "display_record_title": None, "matched_record_count": 179}],
        }])[0]
        self.assertEqual(claim["evidence"][0]["related_record_count"], 0)
        self.assertIsNone(claim["evidence"][0]["display_record_title"])


if __name__ == "__main__":
    unittest.main()
