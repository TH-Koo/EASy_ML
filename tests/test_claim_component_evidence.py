import unittest
from types import SimpleNamespace

from analysis_engine import OntologyAnalysisEngine
from server import build_claims


class ClaimComponentEvidenceTest(unittest.TestCase):
    def test_api_keeps_required_components_and_real_source_links(self):
        claim = build_claims([{
            "capability_id": "energy", "capability_name_ko": "AI 에너지 최적화",
            "required_fulfillment_ratio": 0.7, "supporting_sources": ["dart", "kipris"],
            "fulfilled_required_components": ["분석 모델"], "missing_required_components": ["측정 모듈"],
            "component_support": {"분석 모델": 0.9, "측정 모듈": 0.3, "선택 기능": 1.0},
            "source_evidence": [{"source": "kipris", "components": ["분석 모델"], "record_title": "실제 특허 제목", "record_id": "123", "relation_type": "company_capability", "matched_record_count": 2, "used_for_support": True}],
        }])[0]
        self.assertEqual(claim["status"], "partial")
        self.assertEqual(claim["required_support"], 0.7)
        self.assertEqual([c["name"] for c in claim["components"]], ["분석 모델", "측정 모듈"])
        self.assertEqual(claim["evidence"][0]["components"], ["분석 모델"])
        self.assertEqual(claim["evidence"][0]["record_title"], "실제 특허 제목")
        self.assertNotIn("components", claim["evidence"][1])

    def test_legacy_claim_never_invents_a_record_link(self):
        claim = build_claims([{"supporting_sources": ["dart"], "required_fulfillment_ratio": 0.8}])[0]
        self.assertEqual(claim["components"], [])
        self.assertNotIn("record_title", claim["evidence"][0])

    def test_source_example_prefers_actual_required_component_record(self):
        def contribution(ident, name, level, score):
            return SimpleNamespace(evidence_id=ident,component_name=name,required_level=level,
                                   support=score,source_type="kipris",component_relevance=0.8,
                                   relation_type="company_capability",independent_source_key=ident,
                                   capability_relevance=0.8,relation_weight=0.6)
        required = contribution("required", "감지 모델", "required", 0.4)
        optional = contribution("optional", "선택 기능", "optional", 0.9)
        records = [SimpleNamespace(evidence_id="required",title="관련 모델 특허",source_record_id="1"),
                   SimpleNamespace(evidence_id="optional",title="다른 선택 기능 특허",source_record_id="2")]
        engine = object.__new__(OntologyAnalysisEngine)
        row = engine._summarize_capability_sources([optional,required],records)[0]
        self.assertEqual(row["record_title"], "관련 모델 특허")
        self.assertEqual(row["components"], ["감지 모델"])
        self.assertEqual(row["matched_record_count"], 2)
        self.assertTrue(row["used_for_support"])


    def test_relevance_beats_score_and_controls_source_order(self):
        def contribution(ident, source, capability, component, support):
            return SimpleNamespace(evidence_id=ident,component_name="분석 모델",required_level="required",
                                   support=support,source_type=source,component_relevance=component,
                                   capability_relevance=capability,relation_weight=0.6,
                                   relation_type="company_capability",independent_source_key=ident)
        items = [contribution("dart", "dart", 0.6, 0.6, 0.8),
                 contribution("generic", "kipris", 0.5, 0.95, 0.9),
                 contribution("relevant", "kipris", 0.95, 0.85, 0.3)]
        records = [SimpleNamespace(evidence_id=item.evidence_id,title=item.evidence_id,
                                   source_record_id=item.evidence_id) for item in items]
        engine = object.__new__(OntologyAnalysisEngine)
        rows = engine._summarize_capability_sources(items,records)
        self.assertEqual([row["source"] for row in rows], ["kipris", "dart"])
        self.assertEqual(rows[0]["record_title"], "relevant")


if __name__ == "__main__":
    unittest.main()
