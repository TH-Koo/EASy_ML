"""Focused regression tests for four evidence-scoring fixes.

Run from repository root: python -m unittest discover -s tests -p 'test_score_logic_regression.py'
"""
import math
import unittest
from pathlib import Path
from types import SimpleNamespace

from analysis_engine import EvidenceContribution, EvidenceRecord, OntologyAnalysisEngine


ROOT = Path(__file__).resolve().parents[1]


def make_contribution(evidence_id, *, source="ntis", relation="company_capability", channel_type="SW"):
    return EvidenceContribution(
        evidence_id=evidence_id,
        source_type=source,
        capability_id="CAP_TEST",
        component_name="테스트 컴포넌트",
        component_type=channel_type,
        required_level="required",
        relation_type=relation,
        relation_weight=0.7,
        capability_relevance=0.8,
        component_relevance=0.8,
        source_quality=0.8,
        map_base_weight=0.8,
        match_confidence=0.7,
        support=0.6,
        independent_source_key=f"{source}:{evidence_id}",
        direct=relation in {"direct_model", "direct_product"},
        explanation="fixture",
    )


class ScoringRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = OntologyAnalysisEngine(str(ROOT / "ontology"))

    def setUp(self):
        self.engine._contributions_by_cap = {}

    def test_unmatched_certificate_does_not_generate_ces(self):
        # An unrelated NEP certificate is present, but it does not match any
        # requirement of the claimed AI capability.
        record = EvidenceRecord(source_type="nep", title="일반 인증", relation_type="company_general")
        cap = SimpleNamespace(capability_id="CAP_TEST")
        self.engine._contributions_by_cap = {"CAP_TEST": []}
        scores = self.engine._calculate_channel_scores([cap], [record])
        self.assertEqual(scores["ces"]["score"], 0.0)
        self.assertEqual(scores["ces"]["evidence_count"], 0)

    def test_sufficiency_counts_unique_external_records_not_component_matches(self):
        cap1 = SimpleNamespace(capability_id="C1")
        cap2 = SimpleNamespace(capability_id="C2")
        # Same underlying document supports 4 components across 2 capabilities.
        c = make_contribution("same-document", relation="direct_product")
        self.engine._contributions_by_cap = {"C1": [c, c], "C2": [c, c]}
        repeated = self.engine._calculate_evidence_sufficiency([cap1, cap2], [], {}, {})
        self.engine._contributions_by_cap = {"C1": [c], "C2": []}
        unique = self.engine._calculate_evidence_sufficiency([cap1], [], {}, {})
        self.assertAlmostEqual(repeated, unique, places=10)

    def test_matched_certificate_still_receives_ces_credit(self):
        record = EvidenceRecord(source_type="nep", title="AI 관련 인증", relation_type="direct_product")
        cap = SimpleNamespace(capability_id="CAP_TEST", final_score=70.0)
        self.engine._contributions_by_cap = {
            "CAP_TEST": [make_contribution(record.evidence_id, source="nep", relation="direct_product")]
        }
        scores = self.engine._calculate_channel_scores([cap], [record])
        self.assertGreater(scores["ces"]["score"], 0.0)
        self.assertEqual(scores["ces"]["evidence_count"], 1)

    def test_two_independent_sources_increase_sufficiency(self):
        cap = SimpleNamespace(capability_id="CAP_TEST")
        self.engine._contributions_by_cap = {"CAP_TEST": [make_contribution("one", relation="direct_model")]}
        one = self.engine._calculate_evidence_sufficiency([cap], [], {}, {})
        self.engine._contributions_by_cap = {"CAP_TEST": [
            make_contribution("one", relation="direct_model"),
            make_contribution("two", source="kipris", relation="direct_model"),
        ]}
        two = self.engine._calculate_evidence_sufficiency([cap], [], {}, {})
        self.assertGreater(two, one)

    def test_direct_product_without_optional_tag_remains_uncapped(self):
        record = EvidenceRecord(
            source_type="ntis", relation_type="direct_product",
            capability_ids=["CAP_TEST"], meta={}, text="제품 내 AI 구현 연구",
        )
        # High-quality directly matched evidence must not inherit the 0.65
        # company-evidence cap merely because optional ETL metadata is absent.
        mapping = {"acceptable_evidence_source": "ntis", "match_scope": "any", "base_weight": 1.0}
        record.match_confidence = 1.0
        original_relevance = self.engine._component_relevance
        original_quality = self.engine._source_quality
        self.engine._component_relevance = lambda **kwargs: 0.90
        self.engine._source_quality = lambda record: 1.0
        try:
            matches = self.engine._find_requirement_contributions(
                "CAP_TEST", "머신러닝 모델", "SW", "required", [mapping], [record]
            )
        finally:
            self.engine._component_relevance = original_relevance
            self.engine._source_quality = original_quality
        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0].direct)
        self.assertGreater(matches[0].support, 0.65)

    def test_company_general_cannot_satisfy_ai_requirement(self):
        record = EvidenceRecord(
            source_type="ntis", relation_type="company_general",
            text="일반 기업 현황 자료",
        )
        mapping = {"acceptable_evidence_source": "ntis", "match_scope": "any", "base_weight": 0.8}
        original_cap = self.engine._capability_relevance
        original_comp = self.engine._component_relevance
        self.engine._capability_relevance = lambda cap_id, rec: 0.50
        self.engine._component_relevance = lambda **kwargs: 0.9
        try:
            matches = self.engine._find_requirement_contributions(
                "CAP_TEST", "머신러닝 모델", "SW", "required", [mapping], [record]
            )
        finally:
            self.engine._capability_relevance = original_cap
            self.engine._component_relevance = original_comp
        self.assertEqual(matches, [])

    def test_related_company_research_still_counts_as_indirect_evidence(self):
        record = EvidenceRecord(
            source_type="ntis", relation_type="company_general",
            text="관련 기술 연구개발",
        )
        mapping = {"acceptable_evidence_source": "ntis", "match_scope": "any", "base_weight": 0.8}
        original_cap = self.engine._capability_relevance
        original_comp = self.engine._component_relevance
        self.engine._capability_relevance = lambda cap_id, rec: 0.80
        self.engine._component_relevance = lambda **kwargs: 0.9
        try:
            matches = self.engine._find_requirement_contributions(
                "CAP_TEST", "머신러닝 모델", "SW", "required", [mapping], [record]
            )
        finally:
            self.engine._capability_relevance = original_cap
            self.engine._component_relevance = original_comp
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].relation_type, "company_capability")
        self.assertFalse(matches[0].direct)

    def test_indirect_ntis_product_ai_tag_cannot_bypass_company_cap(self):
        record = EvidenceRecord(
            source_type="ntis",
            relation_type="company_capability",
            capability_ids=["CAP_TEST"],
            meta={"relevance_type": "product_ai"},
            text="딥러닝 관련 연구개발",
        )
        mapping = {"acceptable_evidence_source": "ntis", "match_scope": "any", "base_weight": 0.8}
        original = self.engine._component_relevance
        self.engine._component_relevance = lambda **kwargs: 0.90
        try:
            matches = self.engine._find_requirement_contributions(
                "CAP_TEST", "머신러닝 모델", "SW", "required", [mapping], [record]
            )
        finally:
            self.engine._component_relevance = original
        self.assertEqual(len(matches), 1)
        self.assertLessEqual(matches[0].support, 0.65)
        self.assertFalse(matches[0].direct)

    def test_exact_product_ntis_retains_stronger_cap(self):
        record = EvidenceRecord(
            source_type="ntis",
            relation_type="direct_product",
            capability_ids=["CAP_TEST"],
            meta={"relevance_type": "product_ai"},
            text="해당 제품의 딥러닝 구현",
        )
        mapping = {"acceptable_evidence_source": "ntis", "match_scope": "any", "base_weight": 0.8}
        original = self.engine._component_relevance
        self.engine._component_relevance = lambda **kwargs: 0.90
        try:
            matches = self.engine._find_requirement_contributions(
                "CAP_TEST", "머신러닝 모델", "SW", "required", [mapping], [record]
            )
        finally:
            self.engine._component_relevance = original
        self.assertEqual(len(matches), 1)
        self.assertLessEqual(matches[0].support, 0.8)
        self.assertGreater(matches[0].support, 0.65)
        self.assertTrue(matches[0].direct)


if __name__ == "__main__":
    unittest.main()
