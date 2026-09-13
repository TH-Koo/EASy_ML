from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from analysis_engine import EvidenceRecord, OntologyAnalysisEngine, bundle_to_evidence_records
from fides_integration import result_consistency_errors


HEADERS = {
    "ai_capability_master.csv": [
        "capability_id", "capability_name_ko", "definition_ko", "distinction_point_ko"
    ],
    "capability_requirement_master.csv": [
        "capability_id", "component_type", "component_name_ko", "required_level"
    ],
    "confusion_rule_master.csv": ["capability_id", "rule_id"],
    "evidence_pattern_master.csv": [
        "capability_id", "pattern_text_ko", "evidence_strength"
    ],
    "requirement_evidence_map_master.csv": [
        "capability_id", "component_type", "component_name_ko", "required_level",
        "acceptable_evidence_source", "evidence_match_type", "minimum_strength",
        "match_scope", "base_weight"
    ],
    "source_credibility_master.csv": [
        "source_type", "credibility_weight", "directness_base_weight",
        "update_reliability_weight", "source_level", "source_name_ko"
    ],
    "negative_pattern_master.csv": [
        "applies_to_capability_id", "pattern_text_ko", "penalty_weight"
    ],
    "capability_scoring_rule_master.csv": [
        "capability_id", "required_fulfillment_weight", "optional_fulfillment_weight",
        "strong_pattern_weight", "weak_pattern_weight", "source_quality_weight",
        "required_threshold_for_positive", "confusion_penalty", "company_only_penalty",
        "product_level_bonus", "model_level_bonus"
    ],
}


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS[path.name])
        writer.writeheader()
        writer.writerows(rows)


def build_ontology(root: Path) -> None:
    write_csv(root / "ai_capability_master.csv", [{
        "capability_id": "object_detection",
        "capability_name_ko": "객체 탐지",
        "definition_ko": "카메라 영상에서 객체 위치와 종류를 탐지",
        "distinction_point_ko": "객체 탐지 모델 기반 추론",
    }])
    write_csv(root / "capability_requirement_master.csv", [{
        "capability_id": "object_detection",
        "component_type": "SW",
        "component_name_ko": "객체 탐지 모델",
        "required_level": "필수",
    }])
    write_csv(root / "confusion_rule_master.csv", [])
    write_csv(root / "evidence_pattern_master.csv", [
        {"capability_id": "object_detection", "pattern_text_ko": "객체를 탐지", "evidence_strength": "strong"},
        {"capability_id": "object_detection", "pattern_text_ko": "객체 탐지", "evidence_strength": "strong"},
    ])
    rows = []
    for source in ("kipris", "dart", "nipa", "kaiac"):
        rows.append({
            "capability_id": "object_detection",
            "component_type": "SW",
            "component_name_ko": "객체 탐지 모델",
            "required_level": "필수",
            "acceptable_evidence_source": source,
            "evidence_match_type": "technical_keyword",
            "minimum_strength": "weak",
            "match_scope": "company",
            "base_weight": 1.0,
        })
    write_csv(root / "requirement_evidence_map_master.csv", rows)
    write_csv(root / "source_credibility_master.csv", [
        {
            "source_type": source,
            "credibility_weight": 0.95,
            "directness_base_weight": 0.90,
            "update_reliability_weight": 0.90,
            "source_level": "external",
            "source_name_ko": source,
        }
        for source in ("kipris", "dart", "nipa", "kaiac")
    ])
    write_csv(root / "negative_pattern_master.csv", [])
    write_csv(root / "capability_scoring_rule_master.csv", [{
        "capability_id": "object_detection",
        "required_fulfillment_weight": 0.60,
        "optional_fulfillment_weight": 0.15,
        "strong_pattern_weight": 0.15,
        "weak_pattern_weight": 0.05,
        "source_quality_weight": 0.10,
        "required_threshold_for_positive": 0.70,
        "confusion_penalty": 20,
        "company_only_penalty": 12,
        "product_level_bonus": 8,
        "model_level_bonus": 12,
    }])


class FinalizedLogicTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.ontology = Path(self.temp.name)
        build_ontology(self.ontology)
        self.engine = OntologyAnalysisEngine(str(self.ontology))
        self.claim = "이 제품은 카메라 영상에서 객체를 탐지합니다"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def analyze(self, records):
        return self.engine.analyze(records, ad_text=self.claim)

    def capability(self, result):
        return next(item for item in result.capability_scores if item["capability_id"] == "object_detection")

    def test_unrelated_company_patent_is_audit_only(self):
        record = EvidenceRecord(
            source_type="kipris",
            source_record_id="P-UNRELATED",
            title="반도체 세정 장치 특허",
            text="웨이퍼 세정액 순환 장치",
            matched_company=True,
            relation_type="company_general",
            status="verified",
        )
        result = self.analyze([record])
        cap = self.capability(result)
        self.assertEqual(cap["required_fulfillment_ratio"], 0.0)
        self.assertFalse(cap["positive_claim"])
        self.assertEqual(result.tes, 0.0)
        self.assertEqual(result.ecs, 0.0)
        self.assertEqual(result.details["evidence_sufficiency"], 0.0)

    def test_single_related_company_patent_contributes_but_is_capped(self):
        record = EvidenceRecord(
            source_type="kipris",
            source_record_id="P-RELATED",
            title="객체 탐지 모델 특허",
            text="영상 객체 탐지 모델을 이용한 추론 기술",
            matched_company=True,
            relation_type="company_general",
            status="verified",
        )
        result = self.analyze([record])
        support = self.capability(result)["required_fulfillment_ratio"]
        self.assertGreater(support, 0.20)
        self.assertLessEqual(support, 0.55)

    def test_multiple_independent_company_sources_can_establish_possession(self):
        records = [
            EvidenceRecord(
                source_type=source,
                source_record_id=f"{source}-1",
                title="객체 탐지 모델 기술 보유",
                text="객체 탐지 모델을 이용한 영상 추론 기술",
                matched_company=True,
                relation_type="company_general",
                status="verified",
            )
            for source in ("kipris", "dart", "nipa", "kaiac")
        ]
        result = self.analyze(records)
        cap = self.capability(result)
        self.assertGreaterEqual(cap["required_fulfillment_ratio"], 0.62)
        self.assertLessEqual(cap["required_fulfillment_ratio"], 0.78)
        self.assertTrue(cap["positive_claim"])
        self.assertGreater(result.tes + result.ces, 0.0)

    def test_exact_model_evidence_is_stronger_than_one_company_source(self):
        direct = EvidenceRecord(
            source_type="kipris",
            source_record_id="P-DIRECT",
            title="모델 X100 객체 탐지 모델 특허",
            text="X100에 적용되는 객체 탐지 모델과 영상 추론",
            matched_company=True,
            matched_product=True,
            matched_model=True,
            relation_type="direct_model",
            status="verified",
        )
        indirect = EvidenceRecord(
            source_type="kipris",
            source_record_id="P-INDIRECT",
            title="객체 탐지 모델 특허",
            text="과거 제품에 적용된 객체 탐지 모델과 영상 추론",
            matched_company=True,
            relation_type="company_general",
            status="verified",
        )
        direct_support = self.capability(self.analyze([direct]))["required_fulfillment_ratio"]
        indirect_support = self.capability(self.analyze([indirect]))["required_fulfillment_ratio"]
        self.assertGreater(direct_support, indirect_support)

    def test_model_scope_without_technical_match_does_not_satisfy_component(self):
        record = EvidenceRecord(
            source_type="kipris",
            source_record_id="P-MODEL-ONLY",
            title="X100 포장 구조 특허",
            text="X100 운송용 포장 상자 구조",
            matched_model=True,
            matched_product=True,
            matched_company=True,
            relation_type="direct_model",
            status="verified",
        )
        cap = self.capability(self.analyze([record]))
        self.assertEqual(cap["required_fulfillment_ratio"], 0.0)

    def test_duplicate_source_record_does_not_inflate(self):
        records = [
            EvidenceRecord(
                source_type="kipris",
                source_record_id="P-SAME",
                title="객체 탐지 모델 특허",
                text="객체 탐지 모델 영상 추론 기술",
                matched_company=True,
                relation_type="company_general",
                status="verified",
            ),
            EvidenceRecord(
                source_type="kipris",
                source_record_id="P-SAME",
                title="동일 특허 검색 결과 복제",
                text="객체 탐지 모델 영상 추론 기술",
                matched_company=True,
                relation_type="company_general",
                status="verified",
            ),
        ]
        result = self.analyze(records)
        self.assertEqual(result.details["evidence_count_before_dedup"], 2)
        self.assertEqual(result.details["evidence_count"], 1)

    def test_bundle_adapter_does_not_force_company_match(self):
        records = bundle_to_evidence_records(
            db_results=[{
                "source_type": "kc",
                "title": "다른 회사 인증",
                "company_name": "Other Corp",
                "model_name": "Z9",
                "status": "verified",
            }],
            target_company_name="Target Corp",
            model_param="X100",
        )
        self.assertTrue(records)
        self.assertFalse(records[0].matched_company)
        self.assertNotEqual(records[0].relation_type, "company_capability")

    def test_final_result_and_dynamic_log_are_consistent(self):
        record = EvidenceRecord(
            source_type="kipris",
            source_record_id="P-DIRECT-2",
            title="X100 객체 탐지 모델 특허",
            text="X100 객체 탐지 모델 영상 추론",
            matched_company=True,
            matched_model=True,
            matched_product=True,
            relation_type="direct_model",
            status="verified",
        )
        result = self.analyze([record])
        self.assertEqual(result_consistency_errors(result), [])


class ClaimTextConstructionTests(unittest.TestCase):
    """스펙표의 기능명이 판정 텍스트까지 살아 도달하는지 확인한다."""

    def test_spec_keys_survive_flattening(self):
        """스펙 키를 버리면 AI 기능명이 통째로 사라진다.

        다나와 스펙표는 기능명이 키에 있고 값은 "지원" 하나뿐이다.
        키를 버리면 {"AI세탁건조": "지원"} 이 "지원" 이 되어, 정작 판정에
        필요한 기능명이 남지 않는다. 캐시 330건 중 3건이 raw_specs 마저
        비어 있어 이 때문에 AI 기능을 하나도 인식하지 못했다.
        """
        from fides_integration import build_claim_inputs

        ad_text, _ocr, _extra = build_claim_inputs(
            {
                "name": "삼성전자 비스포크 AI 콤보",
                "specs": {"AI세탁건조": "지원", "AI에너지절약": "지원", "용량": "25kg"},
                "raw_specs": "",
            },
            {},
        )
        self.assertIn("AI세탁건조", ad_text)
        self.assertIn("AI에너지절약", ad_text)
        self.assertIn("25kg", ad_text)

    def test_top_level_field_names_are_not_injected(self):
        """최상위 키는 필드 이름이라 내용이 아니다 — 텍스트에 섞이면 안 된다."""
        from fides_integration import build_claim_inputs

        ad_text, _ocr, _extra = build_claim_inputs(
            {"name": "테스트 제품", "specs": {"용량": "25kg"}}, {}
        )
        self.assertNotIn("raw_specs", ad_text)
        self.assertNotIn("normalized_model_name", ad_text)


class ProductPageGuardTests(unittest.TestCase):
    """상품 페이지가 아닌 수집 결과를 실제로 걸러내는지 확인한다."""

    def test_news_page_is_rejected(self):
        """본문만 긴 페이지를 통과시키면 안 된다.

        이전 판정은 "스펙 또는 본문이 있으면 통과"였는데, 다나와 뉴스
        페이지는 스펙표가 없는 대신 본문이 3,000자라 그대로 통과했다.
        제품명 "뉴스룸" 으로 분석까지 진행돼 ACCS 0 으로 기록됐다.
        """
        from pipeline_main import _looks_like_product_page

        self.assertFalse(
            _looks_like_product_page(
                {"specs": {}, "raw_specs": "배너닫기 에누리 몰테일 " * 200}
            )
        )

    def test_product_with_spec_table_is_accepted(self):
        from pipeline_main import _looks_like_product_page

        self.assertTrue(
            _looks_like_product_page({"specs": {"용량": "25kg"}, "raw_specs": ""})
        )

    def test_product_without_spec_table_but_with_pairs_is_accepted(self):
        """스펙표가 없는 상품 유형을 놓치지 않는다."""
        from pipeline_main import _looks_like_product_page

        self.assertTrue(
            _looks_like_product_page(
                {"specs": {}, "raw_specs": "제조회사 : LG전자 / 용량 : 25kg / 색상 : 화이트"}
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
