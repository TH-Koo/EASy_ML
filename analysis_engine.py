from __future__ import annotations

"""Fides ontology analysis engine – finalized rule-based baseline.

Design goals
------------
1. Preserve company-level related technology as meaningful *indirect* evidence.
2. Keep exact model/product evidence stronger than company capability evidence.
3. Prevent one loosely related record from satisfying every requirement.
4. Deduplicate evidence before score, confidence, and diversity calculation.
5. Calculate ACCS, verdict, reasons, and logs in one place only.
6. Produce structured audit features that can later become attention-model input.

The public classes and helper function names are compatible with the existing
EASy integration where practical:
- EvidenceRecord
- CapabilityScore
- AnalysisResult
- DynamicWeightConfig
- OntologyRepository
- OntologyAnalysisEngine
- bundle_to_evidence_records
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from math import exp, log, log1p
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple
import json
import os
import re

import pandas as pd

from fides_config import (
    DEFAULT_ENGINE_CONFIG,
    DynamicWeightConfig,
    EngineConfig,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class EvidenceRecord:
    """Normalized evidence record.

    Existing fields are kept at the beginning for backwards compatibility.
    New fields provide explicit provenance and relation information required for
    reliable scoring and future attention-model training.
    """

    source_type: str
    text: str = ""
    scope: str = "company"
    title: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)
    matched_company: bool = False
    matched_product: bool = False
    matched_model: bool = False
    matched_components: List[str] = field(default_factory=list)

    evidence_id: str = ""
    source_record_id: str = ""
    status: str = "verified"
    relation_type: str = ""
    match_confidence: float = 0.0
    capability_ids: List[str] = field(default_factory=list)
    published_at: str = ""

    def __post_init__(self) -> None:
        self.source_type = normalize_source_type(self.source_type)
        self.scope = normalize_scope(self.scope)
        self.status = normalize_status(self.status)
        self.text = str(self.text or "")
        self.title = str(self.title or "")
        self.meta = dict(self.meta or {})
        self.matched_components = unique_keep_order(
            [str(x).strip() for x in (self.matched_components or []) if str(x).strip()]
        )
        self.capability_ids = unique_keep_order(
            [str(x).strip() for x in (self.capability_ids or []) if str(x).strip()]
        )
        if not self.source_record_id:
            self.source_record_id = _first_nonempty(
                self.meta,
                [
                    "source_record_id",
                    "record_id",
                    "cert_no",
                    "certification_no",
                    "application_no",
                    "application_number",
                    "patent_no",
                    "registration_no",
                    "id",
                    "url",
                ],
            )
        if not self.evidence_id:
            canonical = "|".join(
                [
                    self.source_type,
                    self.source_record_id,
                    normalize_text(self.title),
                    normalize_text(self.text)[:500],
                ]
            )
            self.evidence_id = sha256(canonical.encode("utf-8")).hexdigest()[:20]

        if not self.relation_type:
            self.relation_type = infer_relation_type(self)
        else:
            self.relation_type = normalize_relation_type(self.relation_type)

        if self.match_confidence <= 0:
            self.match_confidence = default_match_confidence(self.relation_type)
        self.match_confidence = clamp01(float(self.match_confidence))


@dataclass
class EvidenceContribution:
    evidence_id: str
    source_type: str
    capability_id: str
    component_name: str
    component_type: str
    required_level: str
    relation_type: str
    relation_weight: float
    capability_relevance: float
    component_relevance: float
    source_quality: float
    map_base_weight: float
    match_confidence: float
    support: float
    independent_source_key: str
    direct: bool
    explanation: str


@dataclass
class CapabilityScore:
    capability_id: str
    capability_name_ko: str
    base_claim_score: float
    requirement_score: float
    source_quality_score: float
    confusion_penalty: float
    company_only_penalty: float
    scope_bonus: float
    final_score: float
    positive_claim: bool
    required_fulfillment_ratio: float
    optional_fulfillment_ratio: float
    matched_strong_patterns: List[str] = field(default_factory=list)
    matched_weak_patterns: List[str] = field(default_factory=list)
    matched_negative_patterns: List[str] = field(default_factory=list)
    supporting_sources: List[str] = field(default_factory=list)
    fulfilled_required_components: List[str] = field(default_factory=list)
    fulfilled_optional_components: List[str] = field(default_factory=list)
    missing_required_components: List[str] = field(default_factory=list)
    # New audit fields are optional and do not break existing consumers.
    direct_evidence_count: int = 0
    indirect_evidence_count: int = 0
    component_support: Dict[str, float] = field(default_factory=dict)
    evidence_ids: List[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    accs: float
    raw_accs: float
    hes: float
    tes: float
    ces: float
    ecs: float
    conf: float
    verdict: str
    risk_level: str
    top_capabilities: List[Dict[str, Any]]
    reasons: List[str]
    capability_scores: List[Dict[str, Any]]
    details: Dict[str, Any]


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def clamp01(value: float) -> float:
    return clamp(value, 0.0, 1.0)


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def unique_keep_order(items: Iterable[Any]) -> List[Any]:
    seen: Set[Any] = set()
    result: List[Any] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[\u200b\ufeff]", "", text)
    text = re.sub(r"[^0-9a-z가-힣+./_-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact_text(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", normalize_text(value))


def normalize_source_type(value: Any) -> str:
    source = normalize_text(value).replace(" ", "_")
    aliases = {
        "kc_ai_products": "rra",
        "kc인증": "kc",
        "전파인증": "rra",
        "kipris_특허": "kipris",
        "특허": "kipris",
        "공시": "dart",
        "나라장터": "procurement",
        "조달": "procurement",
        "koneps": "procurement",
        "pps": "procurement",
        "tta_gs": "gs",
        "gs인증": "gs",
        "한국인공지능인증센터": "kaiac",
        "ai공급": "nipa",
        "seller": "seller_page",
        "product_page": "seller_page",
    }
    return aliases.get(source, source or "unknown")


def normalize_scope(value: Any) -> str:
    scope = normalize_text(value).replace(" ", "_")
    aliases = {
        "product_or_model": "product_or_model",
        "model_or_product": "product_or_model",
        "company_or_product": "company_or_product",
        "product_or_company": "company_or_product",
        "family": "product_family",
    }
    return aliases.get(scope, scope or "company")


def normalize_relation_type(value: Any) -> str:
    relation = normalize_text(value).replace(" ", "_")
    aliases = {
        "model": "direct_model",
        "product": "direct_product",
        "family": "product_family",
        "company": "company_general",
        "company_tech": "company_capability",
        "company_technology": "company_capability",
    }
    allowed = {
        "direct_model",
        "direct_product",
        "product_family",
        "company_capability",
        "company_general",
        "unmatched",
    }
    relation = aliases.get(relation, relation)
    return relation if relation in allowed else "unmatched"


def normalize_status(value: Any) -> str:
    status = normalize_text(value).replace(" ", "_")
    if not status:
        return "verified"
    positive = {
        "verified",
        "valid",
        "success",
        "registered",
        "found",
        "positive",
        "등록",
        "유효",
        "인증",
        "확인",
    }
    negative = {
        "invalid",
        "error",
        "failed",
        "timeout",
        "skipped",
        "skip",
        "not_found",
        "no_match",
        "empty",
        "미등록",
        "스킵",
        "오류",
        "실패",
    }
    if status in positive:
        return "verified"
    if status in negative:
        return status
    return status


def is_valid_evidence_status(status: str) -> bool:
    normalized = normalize_status(status)
    negative_tokens = {
        "invalid",
        "error",
        "failed",
        "timeout",
        "skipped",
        "skip",
        "not_found",
        "no_match",
        "empty",
        "미등록",
        "오류",
        "실패",
    }
    return normalized not in negative_tokens


def normalize_required_level(value: Any) -> str:
    level = normalize_text(value)
    if level in {"required", "필수", "require", "mandatory"}:
        return "required"
    return "optional"


def infer_relation_type(record: EvidenceRecord) -> str:
    scope = normalize_scope(record.scope)
    if record.matched_model or scope == "model":
        return "direct_model"
    if record.matched_product or scope in {"product", "product_or_model"}:
        return "direct_product"
    if scope == "product_family" or bool(record.meta.get("same_product_family")):
        return "product_family"
    if record.matched_company or scope in {"company", "company_or_product"}:
        if record.capability_ids or bool(record.meta.get("capability_related")):
            return "company_capability"
        return "company_general"
    return "unmatched"


def default_match_confidence(relation_type: str) -> float:
    return {
        "direct_model": 0.98,
        "direct_product": 0.90,
        "product_family": 0.78,
        "company_capability": 0.72,
        "company_general": 0.50,
        "unmatched": 0.0,
    }.get(normalize_relation_type(relation_type), 0.0)


def _first_nonempty(mapping: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, pd.DataFrame):
        return " ".join(_flatten_text(row) for row in value.to_dict(orient="records"))
    if isinstance(value, Mapping):
        return " ".join(_flatten_text(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_text(v) for v in value)
    return str(value)


def _extract_status(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    return _first_nonempty(value, ["status", "state", "result", "message", "msg"])


def _looks_negative_result(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, Mapping) and not value:
        return True
    if isinstance(value, (list, tuple, set)) and not value:
        return True
    text = normalize_text(f"{_extract_status(value)} {_flatten_text(value)}")
    if not text:
        return True
    negative_phrases = [
        "미등록",
        "등록되지",
        "검색 결과 없음",
        "결과 없음",
        "데이터 없음",
        "해당 없음",
        "not found",
        "no result",
        "no match",
        "skipped",
        "skip",
        "timeout",
        "error",
        "failed",
    ]
    return any(phrase in text for phrase in negative_phrases)


def _softmax(logits: Mapping[str, float]) -> Dict[str, float]:
    if not logits:
        return {}
    maximum = max(logits.values())
    values = {key: exp(value - maximum) for key, value in logits.items()}
    total = sum(values.values())
    if total <= 0:
        uniform = 1.0 / len(values)
        return {key: uniform for key in values}
    return {key: value / total for key, value in values.items()}


def _parse_date(value: Any) -> Optional[datetime]:
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip()
    for fmt in (
        "%Y-%m-%d",
        "%Y.%m.%d",
        "%Y/%m/%d",
        "%Y%m%d",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(raw[:19], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(raw, errors="coerce", utc=True)
        if pd.isna(parsed):
            return None
        return parsed.to_pydatetime()
    except Exception:
        return None


def _recency_score(value: Any, now: Optional[datetime] = None) -> float:
    dt = _parse_date(value)
    if dt is None:
        return 0.50
    now = now or datetime.now(timezone.utc)
    age_days = max(0, (now - dt).days)
    if age_days <= 365:
        return 1.0
    if age_days <= 365 * 3:
        return 0.85
    if age_days <= 365 * 5:
        return 0.70
    if age_days <= 365 * 10:
        return 0.55
    return 0.40


GENERIC_COMPONENT_TOKENS = {
    "ai",
    "인공지능",
    "모델",
    "모듈",
    "로직",
    "알고리즘",
    "기능",
    "기술",
    "시스템",
    "장치",
    "센서",
    "분석",
    "제어",
    "기반",
    "및",
    "또는",
    "관련",
    "자동",
    "스마트",
    "engine",
    "module",
    "system",
    "logic",
    "algorithm",
}


def meaningful_tokens(value: Any) -> Set[str]:
    tokens = set(re.findall(r"[a-z0-9]+|[가-힣]{2,}", normalize_text(value)))
    return {token for token in tokens if token not in GENERIC_COMPONENT_TOKENS and len(token) >= 2}


# ---------------------------------------------------------------------------
# Ontology repository
# ---------------------------------------------------------------------------


class OntologyRepository:
    REQUIRED_FILES = {
        "capabilities": "ai_capability_master.csv",
        "requirements": "capability_requirement_master.csv",
        "confusion": "confusion_rule_master.csv",
        "patterns": "evidence_pattern_master.csv",
        "requirement_maps": "requirement_evidence_map_master.csv",
        "sources": "source_credibility_master.csv",
        "negative": "negative_pattern_master.csv",
        "scoring_rules": "capability_scoring_rule_master.csv",
    }

    def __init__(self, ontology_dir: str):
        self.ontology_dir = str(ontology_dir)
        self.load_warnings: List[str] = []
        self._load()

    def _read_csv(self, filename: str) -> pd.DataFrame:
        path = Path(self.ontology_dir) / filename
        if not path.exists():
            raise FileNotFoundError(f"온톨로지 파일을 찾을 수 없습니다: {path}")
        try:
            frame = pd.read_csv(path, encoding="utf-8-sig")
        except pd.errors.ParserError as exc:
            # The current repository contains one malformed requirement-map row.
            # Skip only malformed lines and expose a warning in result details.
            self.load_warnings.append(f"{filename}: malformed row skipped ({exc})")
            frame = pd.read_csv(
                path,
                encoding="utf-8-sig",
                engine="python",
                on_bad_lines="skip",
            )
        frame.columns = [str(column).replace("\ufeff", "").strip() for column in frame.columns]
        return frame.fillna("")

    def _read_optional_csv(self, filename: str) -> pd.DataFrame:
        """Load a supplementary table, tolerating its absence."""
        if not (Path(self.ontology_dir) / filename).exists():
            self.load_warnings.append(f"{filename}: not found, feature disabled")
            return pd.DataFrame()
        return self._read_csv(filename)

    def _load(self) -> None:
        self.cap_df = self._read_csv(self.REQUIRED_FILES["capabilities"])
        self.req_df = self._read_csv(self.REQUIRED_FILES["requirements"])
        self.confusion_df = self._read_csv(self.REQUIRED_FILES["confusion"])
        self.pattern_df = self._read_csv(self.REQUIRED_FILES["patterns"])
        self.req_map_df = self._read_csv(self.REQUIRED_FILES["requirement_maps"])
        self.source_df = self._read_csv(self.REQUIRED_FILES["sources"])
        self.neg_df = self._read_csv(self.REQUIRED_FILES["negative"])
        self.rule_df = self._read_csv(self.REQUIRED_FILES["scoring_rules"])
        # Optional: certification records name a device class, never a parts
        # list, so this table bridges "certified as \uacf5\uae30\uccad\uc815\uae30" to the components
        # such a device necessarily contains.  Absent file = feature disabled.
        self.device_implication_df = self._read_optional_csv(
            "device_component_implication_master.csv"
        )

        # Normalize a known mixed-language field before grouping/scoring.
        if "required_level" in self.req_df:
            self.req_df["required_level"] = self.req_df["required_level"].map(
                normalize_required_level
            )
        if "required_level" in self.req_map_df:
            self.req_map_df["required_level"] = self.req_map_df["required_level"].map(
                normalize_required_level
            )
        if "acceptable_evidence_source" in self.req_map_df:
            self.req_map_df["acceptable_evidence_source"] = self.req_map_df[
                "acceptable_evidence_source"
            ].map(normalize_source_type)

        self.capability_map = {
            str(row["capability_id"]): row.to_dict()
            for _, row in self.cap_df.iterrows()
            if str(row.get("capability_id", "")).strip()
        }
        self.requirements_by_cap = self._group(self.req_df, "capability_id")
        self.patterns_by_cap = self._group(self.pattern_df, "capability_id")
        self.negative_by_cap = self._group(self.neg_df, "applies_to_capability_id")
        self.confusion_by_cap = self._group(self.confusion_df, "capability_id")
        self.req_map_by_cap = self._group(self.req_map_df, "capability_id")
        self.source_rule_map = {
            normalize_source_type(row["source_type"]): row.to_dict()
            for _, row in self.source_df.iterrows()
            if str(row.get("source_type", "")).strip()
        }
        self.scoring_rule_map = {
            str(row["capability_id"]): row.to_dict()
            for _, row in self.rule_df.iterrows()
            if str(row.get("capability_id", "")).strip()
        }
        # (compact device pattern, compact component name) -> implication strength.
        # Longer device patterns are preferred at lookup time so that a specific
        # class ("특정소출력 무선기기") outranks a generic one ("무선기기").
        self.device_implications: List[Tuple[str, str, float]] = []
        for _, row in self.device_implication_df.iterrows():
            device = compact_text(row.get("device_pattern_ko", ""))
            component = compact_text(row.get("component_name_ko", ""))
            if not device or not component:
                continue
            try:
                strength = clamp01(float(row.get("implication_strength", 0.0) or 0.0))
            except (TypeError, ValueError):
                continue
            if strength > 0:
                self.device_implications.append((device, component, strength))
        self.device_implications.sort(key=lambda item: len(item[0]), reverse=True)

    @staticmethod
    def _group(frame: pd.DataFrame, key: str) -> Dict[str, List[Dict[str, Any]]]:
        if key not in frame.columns:
            return {}
        result: Dict[str, List[Dict[str, Any]]] = {}
        for group_key, group in frame.groupby(key):
            if str(group_key).strip():
                result[str(group_key)] = group.to_dict(orient="records")
        return result

    def get_capability_ids(self) -> List[str]:
        return list(self.capability_map.keys())

    def get_capability(self, capability_id: str) -> Dict[str, Any]:
        return self.capability_map.get(capability_id, {})

    def get_capability_name(self, capability_id: str) -> str:
        return str(
            self.get_capability(capability_id).get("capability_name_ko", capability_id)
        )

    def get_requirements(self, capability_id: str) -> List[Dict[str, Any]]:
        return self.requirements_by_cap.get(capability_id, [])

    def get_patterns(self, capability_id: str) -> List[Dict[str, Any]]:
        return self.patterns_by_cap.get(capability_id, [])

    def get_negative_patterns(self, capability_id: str) -> List[Dict[str, Any]]:
        return self.negative_by_cap.get(capability_id, [])

    def get_requirement_maps(self, capability_id: str) -> List[Dict[str, Any]]:
        return self.req_map_by_cap.get(capability_id, [])

    def get_source_rule(self, source_type: str) -> Dict[str, Any]:
        return self.source_rule_map.get(
            normalize_source_type(source_type),
            {
                "source_type": normalize_source_type(source_type),
                "credibility_weight": 0.50,
                "directness_base_weight": 0.50,
                "update_reliability_weight": 0.50,
                "source_level": "unknown",
                "source_name_ko": source_type,
            },
        )

    def get_device_implication(self, device_text: str, component_name: str) -> float:
        """Strength with which a certified device class implies a component."""
        if not self.device_implications:
            return 0.0
        device_compact = compact_text(device_text)
        component_compact = compact_text(component_name)
        if not device_compact or not component_compact:
            return 0.0
        for device, component, strength in self.device_implications:
            if component == component_compact and device in device_compact:
                return strength
        return 0.0

    def get_scoring_rule(self, capability_id: str) -> Dict[str, Any]:
        return self.scoring_rule_map.get(
            capability_id,
            {
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
            },
        )


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------


class OntologyAnalysisEngine:
    HES_SOURCES = {"kc", "rra", "seller_page"}
    TES_SOURCES = {"kipris", "dart", "nipa", "kaiac", "tipa", "koraia", "seller_page", "ntis", "iitp"}
    CES_SOURCES = {"gs", "nep", "procurement", "tta", "kaiac", "nipa", "tipa", "koraia", "net", "sandbox"}

    def __init__(
        self,
        ontology_dir: str,
        dynamic_weight_config: Optional[DynamicWeightConfig] = None,
        enable_dynamic_weighting: bool = True,
        engine_config: Optional[EngineConfig] = None,
    ):
        self.repo = OntologyRepository(ontology_dir)
        self.engine_config = engine_config or DEFAULT_ENGINE_CONFIG
        if dynamic_weight_config is not None:
            self.dynamic_weight_config = dynamic_weight_config
        else:
            self.dynamic_weight_config = self.engine_config.dynamic_weights
        self.enable_dynamic_weighting = bool(enable_dynamic_weighting)
        self._contributions_by_cap: Dict[str, List[EvidenceContribution]] = {}

    def analyze(
        self,
        evidence_records: List[EvidenceRecord],
        ad_text: str = "",
        ocr_text: str = "",
        extra_texts: Optional[List[str]] = None,
    ) -> AnalysisResult:
        validated = [
            record if isinstance(record, EvidenceRecord) else EvidenceRecord(**record)
            for record in (evidence_records or [])
        ]
        validated = [record for record in validated if is_valid_evidence_status(record.status)]
        records = self._dedup_evidence(validated)

        claim_text = self._build_claim_text(ad_text, ocr_text, extra_texts, records)
        capability_scores = self._score_all_capabilities(records, claim_text)
        positive_caps = [score for score in capability_scores if score.positive_claim]
        used_caps = positive_caps if positive_caps else []

        channel_details = self._calculate_channel_scores(used_caps, records)
        hes = channel_details["hes"]["score"]
        tes = channel_details["tes"]["score"]
        ces = channel_details["ces"]["score"]
        ecs = self._calculate_ecs(channel_details, records)

        legacy = self._calculate_legacy_accs(hes, tes, ces, ecs)
        dynamic = self._calculate_dynamic_weighting(
            hes=hes,
            tes=tes,
            ces=ces,
            ecs=ecs,
            channel_details=channel_details,
        )
        accs = dynamic["dynamic_accs"] if self.enable_dynamic_weighting else legacy["legacy_accs"]

        confidence_details = self._calculate_confidence(
            used_caps=used_caps,
            records=records,
            channel_details=channel_details,
            claim_text=claim_text,
        )
        conf = confidence_details["score"]
        sufficiency = self._calculate_evidence_sufficiency(
            used_caps, records, channel_details, confidence_details
        )
        verdict, risk_level = self._decide_verdict(
            accs=accs,
            confidence=conf,
            sufficiency=sufficiency,
            positive_caps=used_caps,
        )

        top_caps = sorted(used_caps, key=lambda item: item.final_score, reverse=True)[:5]
        evidence_audit = self._build_evidence_audit(records)
        reasons = self._build_reasons(
            accs=accs,
            legacy_accs=legacy["legacy_accs"],
            hes=hes,
            tes=tes,
            ces=ces,
            ecs=ecs,
            confidence=conf,
            sufficiency=sufficiency,
            verdict=verdict,
            risk_level=risk_level,
            top_caps=top_caps,
            records=records,
            dynamic=dynamic,
        )

        details: Dict[str, Any] = {
            "engine_version": "2.0.1-claim-detection-hotfix",
            "claim_text": claim_text,
            "claim_detection": {
                "detected": bool(positive_caps),
                "detected_count": len(positive_caps),
                "capability_ids": [item.capability_id for item in positive_caps],
                "matched_patterns": {
                    item.capability_id: {
                        "strong": item.matched_strong_patterns,
                        "weak": item.matched_weak_patterns,
                    }
                    for item in positive_caps
                },
            },
            "legacy_accs": legacy["legacy_accs"],
            "legacy_details": legacy,
            "dynamic_weighting": dynamic,
            "dynamic_weight_log": {
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "method": dynamic["method"],
                "base_scores": dynamic["base_scores"],
                "weights": dynamic["weights"],
                "logits": dynamic["logits"],
                "dynamic_evidence_score": dynamic["dynamic_evidence_score"],
                "dynamic_accs": dynamic["dynamic_accs"],
                "legacy_accs": legacy["legacy_accs"],
                "delta_vs_legacy": round(dynamic["dynamic_accs"] - legacy["legacy_accs"], 2),
                "verdict": verdict,
                "risk_level": risk_level,
            },
            "channel_details": channel_details,
            "channel_presence": {
                "hardware": int(channel_details["hes"]["active"]),
                "technical": int(channel_details["tes"]["active"]),
                "certification": int(channel_details["ces"]["active"]),
            },
            "confidence_details": confidence_details,
            "evidence_sufficiency": round(sufficiency, 4),
            "evidence_count_before_dedup": len(validated),
            "evidence_count": len(records),
            "evidence_by_source": self._count_evidence_by_source(records),
            "evidence_by_relation": self._count_evidence_by_relation(records),
            "evidence_audit": evidence_audit,
            "ontology_load_warnings": self.repo.load_warnings,
            "thresholds": asdict(self.engine_config.thresholds),
            "attention_features": self._build_attention_features(
                records, capability_scores, channel_details, confidence_details, sufficiency
            ),
        }

        return AnalysisResult(
            accs=round(accs, 2),
            raw_accs=round(legacy["raw_accs"], 2),
            hes=round(hes, 2),
            tes=round(tes, 2),
            ces=round(ces, 2),
            ecs=round(ecs, 2),
            conf=round(conf, 2),
            verdict=verdict,
            risk_level=risk_level,
            top_capabilities=[asdict(item) for item in top_caps],
            reasons=reasons,
            capability_scores=[
                asdict(item)
                for item in sorted(capability_scores, key=lambda item: item.final_score, reverse=True)
            ],
            details=details,
        )

    # ------------------------------------------------------------------
    # Claim and capability scoring
    # ------------------------------------------------------------------

    def _build_claim_text(
        self,
        ad_text: str,
        ocr_text: str,
        extra_texts: Optional[List[str]],
        records: List[EvidenceRecord],
    ) -> str:
        parts: List[str] = [ad_text or "", ocr_text or ""]
        parts.extend(extra_texts or [])
        # Only first-party/product content may create a claim. External patents,
        # certifications, and company reports support a claim but never invent it.
        for record in records:
            if record.source_type in {"seller_page", "ocr_text", "product_text", "review"}:
                parts.extend([record.title, record.text])
        return normalize_text(" ".join(parts))

    def _score_all_capabilities(
        self, records: List[EvidenceRecord], claim_text: str
    ) -> List[CapabilityScore]:
        self._contributions_by_cap = {}
        return [
            self._score_one_capability(capability_id, records, claim_text)
            for capability_id in self.repo.get_capability_ids()
        ]

    def _score_one_capability(
        self, capability_id: str, records: List[EvidenceRecord], claim_text: str
    ) -> CapabilityScore:
        strong_patterns, weak_patterns = self._match_positive_patterns(
            capability_id, claim_text
        )
        negative_patterns = self._match_negative_patterns(capability_id, claim_text)

        claim_score = self._claim_score(strong_patterns, weak_patterns)
        requirement_info = self._calculate_requirement_support(capability_id, records)
        contributions = requirement_info["contributions"]
        self._contributions_by_cap[capability_id] = contributions

        source_quality = self._average_contribution_quality(contributions)
        negative_penalty = self._negative_penalty(capability_id, negative_patterns)

        required_ratio = requirement_info["required_ratio"]
        optional_ratio = requirement_info["optional_ratio"]
        final_score = clamp(
            claim_score * 0.30
            + required_ratio * 100.0 * 0.55
            + optional_ratio * 100.0 * 0.10
            + source_quality * 0.05
            - negative_penalty
        )

        scoring_rule = self.repo.get_scoring_rule(capability_id)
        # Claim detection and evidence validation are deliberately separated.
        # A product claim with no supporting evidence is precisely the case that
        # the washing detector must score as low-confidence/washing; it must not
        # be converted into "Not Evaluated".  Requirement support is retained in
        # required_fulfillment_ratio and affects HES/TES/CES/ACCS separately.
        positive_claim = bool(claim_score >= 25.0)

        direct_count = len({c.evidence_id for c in contributions if c.direct})
        indirect_count = len({c.evidence_id for c in contributions if not c.direct})
        evidence_ids = unique_keep_order(c.evidence_id for c in contributions)
        supporting_sources = unique_keep_order(c.source_type for c in contributions)

        return CapabilityScore(
            capability_id=capability_id,
            capability_name_ko=self.repo.get_capability_name(capability_id),
            base_claim_score=round(claim_score, 2),
            requirement_score=round(required_ratio * 100.0, 2),
            source_quality_score=round(source_quality, 2),
            confusion_penalty=round(negative_penalty, 2),
            company_only_penalty=0.0,
            scope_bonus=0.0,
            final_score=round(final_score, 2),
            positive_claim=positive_claim,
            required_fulfillment_ratio=round(required_ratio, 4),
            optional_fulfillment_ratio=round(optional_ratio, 4),
            matched_strong_patterns=strong_patterns,
            matched_weak_patterns=weak_patterns,
            matched_negative_patterns=[
                str(item.get("pattern_text_ko", "")) for item in negative_patterns
            ],
            supporting_sources=supporting_sources,
            fulfilled_required_components=requirement_info["fulfilled_required"],
            fulfilled_optional_components=requirement_info["fulfilled_optional"],
            missing_required_components=requirement_info["missing_required"],
            direct_evidence_count=direct_count,
            indirect_evidence_count=indirect_count,
            component_support=requirement_info["component_support"],
            evidence_ids=evidence_ids,
        )

    def _match_positive_patterns(
        self, capability_id: str, claim_text: str
    ) -> Tuple[List[str], List[str]]:
        strong: List[str] = []
        weak: List[str] = []
        for row in self.repo.get_patterns(capability_id):
            pattern = normalize_text(row.get("pattern_text_ko", ""))
            if pattern and pattern in claim_text:
                original = str(row.get("pattern_text_ko", "")).strip()
                if normalize_text(row.get("evidence_strength", "")) == "strong":
                    strong.append(original)
                else:
                    weak.append(original)
        return unique_keep_order(strong), unique_keep_order(weak)

    def _match_negative_patterns(
        self, capability_id: str, claim_text: str
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for row in self.repo.get_negative_patterns(capability_id):
            pattern = normalize_text(row.get("pattern_text_ko", ""))
            if pattern and pattern in claim_text:
                result.append(row)
        return result

    @staticmethod
    def _claim_score(strong_patterns: List[str], weak_patterns: List[str]) -> float:
        strong_score = 0.0
        if strong_patterns:
            strong_score = min(100.0, 72.0 + 10.0 * (len(strong_patterns) - 1))
        weak_score = min(55.0, 25.0 * len(weak_patterns))
        return clamp(max(strong_score, weak_score, strong_score + weak_score * 0.20))

    def _negative_penalty(
        self, capability_id: str, negative_patterns: List[Dict[str, Any]]
    ) -> float:
        if not negative_patterns:
            return 0.0
        rule = self.repo.get_scoring_rule(capability_id)
        base = float(rule.get("confusion_penalty", 20.0) or 20.0)
        ratio = 0.0
        for item in negative_patterns:
            try:
                ratio += float(item.get("penalty_weight", 0.5) or 0.5)
            except (TypeError, ValueError):
                ratio += 0.5
        return min(base, base * min(1.0, ratio))

    # ------------------------------------------------------------------
    # Requirement support
    # ------------------------------------------------------------------

    def _calculate_requirement_support(
        self, capability_id: str, records: List[EvidenceRecord]
    ) -> Dict[str, Any]:
        requirements = self.repo.get_requirements(capability_id)
        maps = self.repo.get_requirement_maps(capability_id)

        required_scores: List[float] = []
        optional_scores: List[float] = []
        fulfilled_required: List[str] = []
        fulfilled_optional: List[str] = []
        missing_required: List[str] = []
        component_support: Dict[str, float] = {}
        all_contributions: List[EvidenceContribution] = []

        for requirement in requirements:
            component_name = str(requirement.get("component_name_ko", "")).strip()
            component_type = normalize_text(requirement.get("component_type", "")).upper()
            required_level = normalize_required_level(requirement.get("required_level", ""))
            component_maps = [
                row
                for row in maps
                if compact_text(row.get("component_name_ko", ""))
                == compact_text(component_name)
            ]
            contributions = self._find_requirement_contributions(
                capability_id=capability_id,
                component_name=component_name,
                component_type=component_type,
                required_level=required_level,
                maps=component_maps,
                records=records,
            )
            support = self._aggregate_component_support(contributions)
            component_support[component_name] = round(support, 4)
            all_contributions.extend(contributions)

            if required_level == "required":
                required_scores.append(support)
                if support >= self.engine_config.fulfilled_component_threshold:
                    fulfilled_required.append(component_name)
                else:
                    missing_required.append(component_name)
            else:
                optional_scores.append(support)
                if support >= self.engine_config.fulfilled_component_threshold:
                    fulfilled_optional.append(component_name)

        required_ratio = sum(required_scores) / len(required_scores) if required_scores else 0.0
        optional_ratio = sum(optional_scores) / len(optional_scores) if optional_scores else 0.0
        return {
            "required_ratio": clamp01(required_ratio),
            "optional_ratio": clamp01(optional_ratio),
            "fulfilled_required": fulfilled_required,
            "fulfilled_optional": fulfilled_optional,
            "missing_required": missing_required,
            "component_support": component_support,
            "contributions": self._dedup_contributions(all_contributions),
        }

    def _find_requirement_contributions(
        self,
        capability_id: str,
        component_name: str,
        component_type: str,
        required_level: str,
        maps: List[Dict[str, Any]],
        records: List[EvidenceRecord],
    ) -> List[EvidenceContribution]:
        result: List[EvidenceContribution] = []
        if not maps:
            return result

        for mapping in maps:
            source = normalize_source_type(mapping.get("acceptable_evidence_source", ""))
            try:
                base_weight = clamp01(float(mapping.get("base_weight", 0.5) or 0.5))
            except (TypeError, ValueError):
                base_weight = 0.5
            minimum_strength = normalize_text(mapping.get("minimum_strength", "weak"))
            match_scope = normalize_scope(mapping.get("match_scope", "any"))
            evidence_match_type = normalize_text(mapping.get("evidence_match_type", ""))

            for record in records:
                if record.source_type != source and not (
                    (record.source_type == "ntis" and source in {"kipris", "dart", "nipa"})
                    or (record.source_type in {"net", "sandbox"} and source in {"gs", "nep", "kc", "rra"})
                ):
                    continue
                relation_type = self._effective_relation_type(record, capability_id)
                if not self._scope_compatible(match_scope, relation_type):
                    continue

                capability_relevance = self._capability_relevance(
                    capability_id, record
                )
                component_relevance = self._component_relevance(
                    capability_id=capability_id,
                    component_name=component_name,
                    component_type=component_type,
                    record=record,
                    evidence_match_type=evidence_match_type,
                    capability_relevance=capability_relevance,
                )

                threshold = (
                    self.engine_config.strong_component_threshold
                    if minimum_strength == "strong"
                    else self.engine_config.weak_component_threshold
                )
                if component_relevance < threshold:
                    continue
                if component_type == "SW" and capability_relevance < 0.40:
                    continue
                #if relation_type == "company_general":
                    # General company existence is not technical evidence. It may be
                    # retained in the audit but does not satisfy requirements.
                    #continue

                relation_weight = self._relation_weight(relation_type)
                source_quality = self._source_quality(record)
                effective_match_confidence = record.match_confidence
                if (
                    record.relation_type == "company_general"
                    and relation_type == "company_capability"
                ):
                    # The API/search context established company identity and the
                    # evidence text established capability relevance.  Promote only
                    # the confidence appropriate to an indirect company-capability
                    # relationship, never to product/model confidence.
                    effective_match_confidence = max(
                        effective_match_confidence,
                        default_match_confidence("company_capability"),
                    )
                capability_factor = max(0.35, capability_relevance)
                if component_type == "HW" and relation_type in {
                    "direct_model",
                    "direct_product",
                    "product_family",
                }:
                    # Direct hardware specifications need less semantic capability
                    # wording than software/algorithm evidence.
                    capability_factor = max(0.65, capability_factor)

                context_score = (relation_weight + effective_match_confidence + source_quality) / 3.0
                relevance_score = (component_relevance + capability_factor) / 2.0

                support = context_score * relevance_score * max(0.8, base_weight)
                support = clamp01(support)

                if record.source_type in {"kipris", "dart", "ntis"} and component_relevance >= 0.50:
                    if record.meta.get("relevance_type") == "product_ai":
                        support = max(support, component_relevance * 0.92) 
                    else:
                        support = max(support, component_relevance * 0.46)
                elif record.source_type in {"net", "nep"} and component_relevance >= 0.50:
                    support = max(support, component_relevance * 0.98)
                elif record.source_type in {"gs", "rra", "sandbox"} and component_relevance >= 0.50:
                    support = max(support, component_relevance * 0.88)
                support = clamp01(support)


                direct = relation_type in {"direct_model", "direct_product"}
                result.append(
                    EvidenceContribution(
                        evidence_id=record.evidence_id,
                        source_type=record.source_type,
                        capability_id=capability_id,
                        component_name=component_name,
                        component_type=component_type,
                        required_level=required_level,
                        relation_type=relation_type,
                        relation_weight=round(relation_weight, 4),
                        capability_relevance=round(capability_relevance, 4),
                        component_relevance=round(component_relevance, 4),
                        source_quality=round(source_quality, 4),
                        map_base_weight=round(base_weight, 4),
                        match_confidence=round(effective_match_confidence, 4),
                        support=round(support, 4),
                        independent_source_key=f"{record.source_type}:{record.source_record_id or record.evidence_id}",
                        direct=direct,
                        explanation=(
                            f"{record.source_type} / {relation_type} / "
                            f"cap={capability_relevance:.2f}, component={component_relevance:.2f}"
                        ),
                    )
                )
        return self._dedup_contributions(result)

    def _capability_relevance(
        self, capability_id: str, record: EvidenceRecord
    ) -> float:
        if capability_id in record.capability_ids:
            return 1.0
        text = normalize_text(f"{record.title} {record.text}")
        if not text:
            return 0.0

        strong, weak = self._match_positive_patterns(capability_id, text)
        if strong:
            return min(1.0, 0.92 + 0.03 * (len(strong) - 1))
        if weak:
            return min(0.82, 0.62 + 0.05 * (len(weak) - 1))

        capability = self.repo.get_capability(capability_id)
        name = normalize_text(capability.get("capability_name_ko", ""))
        if name and name in text:
            return 0.88

        definition_tokens = meaningful_tokens(
            f"{capability.get('definition_ko', '')} {capability.get('distinction_point_ko', '')}"
        )
        evidence_tokens = meaningful_tokens(text)
        overlap = len(definition_tokens & evidence_tokens)
        if overlap >= 3:
            return 0.72
        if overlap == 2:
            return 0.58
        if overlap == 1:
            return 0.32
        if record.source_type in {"kipris", "dart", "ntis", "tta", "gs", "rra", "net", "sandbox", "nep"}:
            return 0.50
        return 0.0

    def _component_relevance(
        self,
        capability_id: str,
        component_name: str,
        component_type: str,
        record: EvidenceRecord,
        evidence_match_type: str,
        capability_relevance: float,
    ) -> float:
        normalized_component = compact_text(component_name)
        explicit_components = {compact_text(item) for item in record.matched_components}
        if normalized_component and normalized_component in explicit_components:
            return 1.0

        text = normalize_text(f"{record.title} {record.text}")
        compact = compact_text(text)
        if normalized_component and normalized_component in compact:
            return 0.96

        # A certification record states a device class ("공기청정기", "특정소출력
        # 무선기기"), never a parts list, so no amount of token matching against a
        # component name such as "공기질 센서(PM2.5·VOC·CO2)" can ever succeed.
        # Bridge the two levels explicitly, but only for evidence tied to this
        # product or its model family -- an unrelated company certification must
        # not imply anything about this product's hardware.
        if self._effective_relation_type(record, capability_id) in {
            "direct_model",
            "direct_product",
            "product_family",
        }:
            device_text = _first_nonempty(
                record.meta, ["equip_name", "product_name", "device_name", "기자재명칭"]
            )
            implication = self.repo.get_device_implication(
                device_text or record.title, component_name
            )
            if implication > 0:
                return implication

        component_tokens = meaningful_tokens(component_name)
        evidence_tokens = meaningful_tokens(text)
        overlap = component_tokens & evidence_tokens
        if component_tokens:
            overlap_ratio = len(overlap) / len(component_tokens)
            if overlap_ratio >= 0.66:
                return 0.90
            if len(overlap) >= 2:
                return 0.82
            if len(overlap) == 1:
                return 0.62

        relation = self._effective_relation_type(record, capability_id)
        direct_relation = relation in {"direct_model", "direct_product", "product_family"}

        # Structured evidence-type fallbacks are deliberately conservative. They
        # never allow model/product/company matching alone to satisfy all parts.
        if evidence_match_type == "technical_keyword" and capability_relevance >= 0.80:
            return 0.76
        if evidence_match_type == "business_technical_keyword" and capability_relevance >= 0.75:
            return 0.68
        if evidence_match_type in {"certification_text", "registered_function_text"}:
            if capability_relevance >= 0.75:
                return 0.68
        if evidence_match_type == "solution_capability_text" and capability_relevance >= 0.75:
            return 0.66
        if evidence_match_type == "claim_text" and direct_relation and capability_relevance >= 0.70:
            return 0.64
        if evidence_match_type == "spec_text" and direct_relation:
            # A first-party spec can weakly support a named hardware/software
            # component but does not become an independent external proof.
            return 0.58 if component_type == "HW" else 0.48
        if evidence_match_type == "hardware_spec" and direct_relation:
            hardware_terms = {
                "카메라",
                "마이크",
                "센서",
                "lidar",
                "라이다",
                "tof",
                "wifi",
                "wi-fi",
                "블루투스",
                "통신",
                "프로세서",
                "칩",
                "보드",
            }
            if any(term in text for term in hardware_terms):
                return 0.60
        if record.source_type in {"kipris", "dart", "ntis", "tta", "gs", "rra", "net", "sandbox"}:
            return 0.50
        
        return 0.0

    def _aggregate_component_support(
        self, contributions: List[EvidenceContribution]
    ) -> float:
        if not contributions:
            return 0.0
        contributions = sorted(contributions, key=lambda item: item.support, reverse=True)
        independent: Dict[str, EvidenceContribution] = {}
        for item in contributions:
            current = independent.get(item.independent_source_key)
            if current is None or item.support > current.support:
                independent[item.independent_source_key] = item
        selected = sorted(independent.values(), key=lambda item: item.support, reverse=True)[:10]

        # Probabilistic union with diminishing returns: multiple independent
        # company-level sources can jointly establish technology possession, while
        # duplicate search rows cannot inflate the result.
        product = 1.0
        for rank, item in enumerate(selected):
            diminishing = max(0.6, 1.0 - (rank * 0.05))
            product *= 1.0 - clamp01(item.support * diminishing)
        combined = 1.0 - product

        company_only = all(
            item.relation_type in {"company_capability", "company_general"}
            for item in selected
        )
        if company_only:
            independent_sources = len({item.source_type for item in selected})
            cap = (
                self.engine_config.company_multi_source_cap
                if independent_sources >= 2
                else self.engine_config.company_single_source_cap
            )
            combined = min(combined, cap)
        return clamp01(combined)

    @staticmethod
    def _dedup_contributions(
        contributions: List[EvidenceContribution],
    ) -> List[EvidenceContribution]:
        best: Dict[Tuple[str, str, str], EvidenceContribution] = {}
        for item in contributions:
            key = (item.evidence_id, item.capability_id, item.component_name)
            current = best.get(key)
            if current is None or item.support > current.support:
                best[key] = item
        return list(best.values())

    # Compatibility methods retained for legacy callers. They no longer accept
    # scope alone as component proof.
    def _match_requirement_strong(
        self, component_name: str, record: EvidenceRecord, evidence_text: str
    ) -> bool:
        if compact_text(component_name) in {
            compact_text(item) for item in record.matched_components
        }:
            return True
        tokens = meaningful_tokens(component_name)
        return bool(tokens and len(tokens & meaningful_tokens(evidence_text)) >= max(1, len(tokens) // 2))

    def _match_requirement_weak(
        self, component_name: str, record: EvidenceRecord, evidence_text: str
    ) -> bool:
        if self._match_requirement_strong(component_name, record, evidence_text):
            return True
        return bool(meaningful_tokens(component_name) & meaningful_tokens(evidence_text))

    def _scope_compatible(self, required_scope: str, evidence_scope_or_relation: str) -> bool:
        required = normalize_scope(required_scope)
        relation = normalize_relation_type(evidence_scope_or_relation)
        if relation == "unmatched":
            # Legacy callers may pass an old scope string instead of relation.
            old_scope = normalize_scope(evidence_scope_or_relation)
            relation = {
                "model": "direct_model",
                "product": "direct_product",
                "product_or_model": "direct_product",
                "product_family": "product_family",
                "company": "company_capability",
                "company_or_product": "company_capability",
            }.get(old_scope, "unmatched")
        if required in {"", "any"}:
            return relation != "unmatched"
        if required == "model":
            return relation == "direct_model"
        if required == "product":
            return relation in {"direct_model", "direct_product"}
        if required == "product_or_model":
            return relation in {"direct_model", "direct_product", "product_family"}
        if required in {"company", "company_or_product"}:
            return relation in {
                "direct_model",
                "direct_product",
                "product_family",
                "company_capability",
            }
        return relation != "unmatched"

    # ------------------------------------------------------------------
    # Evidence and source quality
    # ------------------------------------------------------------------

    def _effective_relation_type(
        self, record: EvidenceRecord, capability_id: str
    ) -> str:
        relation = normalize_relation_type(record.relation_type)
        if relation == "company_general" and self._capability_relevance(capability_id, record) >= 0.60:
            # This is the intended route for related technology from another
            # product: company-level, capability-related, indirect evidence.
            return "company_capability"
        return relation

    def _relation_weight(self, relation_type: str) -> float:
        return float(
            getattr(
                self.engine_config.relation_weights,
                normalize_relation_type(relation_type),
                0.0,
            )
        )

    def _source_quality(self, record: EvidenceRecord) -> float:
        rule = self.repo.get_source_rule(record.source_type)
        try:
            credibility = float(rule.get("credibility_weight", 0.5) or 0.5)
            directness = float(rule.get("directness_base_weight", 0.5) or 0.5)
            update_reliability = float(
                rule.get("update_reliability_weight", 0.5) or 0.5
            )
        except (TypeError, ValueError):
            credibility = directness = update_reliability = 0.5
        quality = credibility * 0.50 + directness * 0.30 + update_reliability * 0.20
        quality *= 0.85 + 0.15 * _recency_score(record.published_at or record.meta.get("date"))
        if record.source_type == "seller_page":
            quality = min(quality, self.engine_config.seller_page_quality_cap)
        return clamp01(quality)

    @staticmethod
    def _average_contribution_quality(contributions: List[EvidenceContribution]) -> float:
        if not contributions:
            return 0.0
        best_by_evidence: Dict[str, EvidenceContribution] = {}
        for item in contributions:
            current = best_by_evidence.get(item.evidence_id)
            if current is None or item.support > current.support:
                best_by_evidence[item.evidence_id] = item
        values = [item.source_quality * 100.0 for item in best_by_evidence.values()]
        return sum(values) / len(values)

    def _dedup_evidence(self, records: List[EvidenceRecord]) -> List[EvidenceRecord]:
        best: Dict[Tuple[str, str], EvidenceRecord] = {}
        for record in records:
            key_id = record.source_record_id or record.evidence_id
            key = (record.source_type, key_id)
            current = best.get(key)
            if current is None:
                best[key] = record
                continue
            current_strength = self._relation_weight(current.relation_type) * current.match_confidence
            new_strength = self._relation_weight(record.relation_type) * record.match_confidence
            if new_strength > current_strength:
                winner, loser = record, current
            else:
                winner, loser = current, record
            winner.matched_components = unique_keep_order(
                winner.matched_components + loser.matched_components
            )
            winner.capability_ids = unique_keep_order(
                winner.capability_ids + loser.capability_ids
            )
            if len(loser.text) > len(winner.text):
                winner.text = loser.text
            best[key] = winner
        return list(best.values())

    # ------------------------------------------------------------------
    # Channel scores and ACCS
    # ------------------------------------------------------------------

    def _calculate_channel_scores(
        self, used_caps: List[CapabilityScore], records: List[EvidenceRecord]
    ) -> Dict[str, Dict[str, Any]]:
        cap_by_id = {item.capability_id: item for item in used_caps}
        record_by_id = {record.evidence_id: record for record in records}
        all_contributions = [
            contribution
            for cap in used_caps
            for contribution in self._contributions_by_cap.get(cap.capability_id, [])
        ]

        result: Dict[str, Dict[str, Any]] = {}
        for channel in ("hes", "tes", "ces"):
            channel_contributions = [
                item for item in all_contributions if self._contribution_channel(item) == channel
            ]
            best_by_evidence: Dict[str, EvidenceContribution] = {}
            for item in channel_contributions:
                current = best_by_evidence.get(item.evidence_id)
                if current is None or item.support > current.support:
                    best_by_evidence[item.evidence_id] = item
            selected = sorted(
                best_by_evidence.values(), key=lambda item: item.support, reverse=True
            )[: self.engine_config.max_channel_evidence]

            if selected:
                rank_weights = [1.0, 0.75, 0.55, 0.40, 0.30, 0.20]
                numerator = sum(
                    item.support * 100.0 * rank_weights[index]
                    for index, item in enumerate(selected)
                )
                denominator = sum(rank_weights[: len(selected)])
                evidence_score = numerator / denominator
                supporting_cap_ids = unique_keep_order(item.capability_id for item in selected)
                cap_scores = [
                    cap_by_id[cap_id].final_score
                    for cap_id in supporting_cap_ids
                    if cap_id in cap_by_id
                ]
                capability_score = sum(cap_scores) / len(cap_scores) if cap_scores else 0.0
                
                bonus = 0.0

                # 1. 출처 다양성
                unique_sources = len({x.source_type for x in selected})
                bonus += min(unique_sources, 4) * 3

                # 2. 제품과의 직접 관련성
                avg_relation = sum(x.relation_weight for x in selected) / len(selected)
                bonus += avg_relation * 10

                # 3. 근거 개수(로그 스케일)
                bonus += min(log1p(len(selected)) * 3.0, 6)

                # 4. 서로 다른 출처 보상
                bonus += min(unique_sources * 2, 8)

                # Saturation
                bonus = 15 * (1 - exp(-bonus / 12))
                score = clamp(evidence_score * 0.55 + capability_score * 0.30 + bonus)
            else:
                supporting_cap_ids = []

                # Capability와 연결되지 않았더라도
                # 해당 채널의 근거가 존재하면 기본 점수 부여

                if channel == "ces":
                    fallback = [
                        r for r in records
                        if r.source_type in self.CES_SOURCES
                    ]

                elif channel == "hes":
                    fallback = [
                        r for r in records
                        if r.source_type in self.HES_SOURCES
                    ]

                elif channel == "tes":
                    fallback = [
                        r for r in records
                        if r.source_type in self.TES_SOURCES
                    ]

                else:
                    fallback = []

                # used_caps 가 비어 있다는 것은 이 제품 전체에서 AI 기능
                # 주장이 단 하나도 온톨로지 패턴과 매칭되지 않았다는 뜻이다
                # (positive_claim 이 어디에도 없음). 그런 경우까지 KC/RRA
                # 인증 개수만으로 기본 점수를 주면, "AI"라고만 쓰고 실제
                # 기능은 특정하지 않은 제품(모니터 등 인증형 워싱)이 인증
                # 많은 정상 제품과 같은 자리에서 36~43점을 받는다. 이 채널이
                # 아니라 다른 채널에서라도 최소 한 capability 가 positive_claim
                # 이면(=이 제품이 뭔가 구체적 AI 기능을 주장한 게 맞으면)
                # 이 채널의 커버리지 공백은 기존처럼 fallback 으로 메운다.
                if fallback and used_caps:
                    evidence_score = min(
                        35 + log1p(len(fallback)) * 12,
                        65
                    )

                    capability_score = 25

                    score = clamp(
                        evidence_score * 0.7 +
                        capability_score * 0.3
                    )

                else:
                    evidence_score = 0
                    capability_score = 0
                    score = 0

            source_counts: Dict[str, int] = {}
            relation_counts: Dict[str, int] = {}
            for item in selected:
                source_counts[item.source_type] = source_counts.get(item.source_type, 0) + 1
                relation_counts[item.relation_type] = relation_counts.get(item.relation_type, 0) + 1
            total = len(selected)
            directness = (
                sum(item.relation_weight for item in selected) / total if total else 0.0
            )
            max_source_share = max(source_counts.values()) / total if total else 0.0
            recency_values = [
                _recency_score(
                    record_by_id[item.evidence_id].published_at
                    or record_by_id[item.evidence_id].meta.get("date")
                )
                for item in selected
                if item.evidence_id in record_by_id
            ]
            avg_recency = (
                sum(recency_values) / len(recency_values) if recency_values else 0.50
            )
            result[channel] = {
                "score": round(score, 2),
                "active": bool(selected and score > 0),
                "evidence_score": round(evidence_score, 2),
                "capability_score": round(capability_score, 2),
                "evidence_count": total,
                "source_types": sorted(source_counts),
                "source_counts": source_counts,
                "relation_counts": relation_counts,
                "avg_directness": round(directness, 4),
                "max_source_share": round(max_source_share, 4),
                "avg_recency": round(avg_recency, 4),
                "supporting_capabilities": supporting_cap_ids,
                "evidence_ids": [item.evidence_id for item in selected],
            }
        return result

    def _contribution_channel(self, item: EvidenceContribution) -> str:
        if item.source_type in self.CES_SOURCES:
            return "ces"
        if item.component_type == "HW" and item.source_type in self.HES_SOURCES:
            return "hes"
        if item.component_type == "SW" and item.source_type in self.TES_SOURCES:
            return "tes"
        if item.component_type == "SW" and item.source_type == "seller_page":
            # A first-party page is already accepted into HES for hardware specs,
            # so silently dropping its software description left a hole: a product
            # whose only match was a seller-described SW component scored ACCS 0.0
            # -- identical to a product with no evidence whatsoever.  Its weight is
            # already held down by seller_page_quality_cap, and Normal still
            # requires external corroboration (see _decide_verdict).
            return "tes"
        return "other"

    def _calculate_ecs(
        self,
        channel_details,
        records
    ):

        record_by_id = {
            r.evidence_id: r
            for r in records
        }

        contributing_ids = {
            evidence_id
            for channel in ("hes", "tes", "ces")
            for evidence_id in channel_details[channel].get("evidence_ids", [])
        }

        external_records = [
            r
            for r in records
            if r.evidence_id in contributing_ids
            and r.source_type not in {"seller_page", "review"}
        ]

        if not external_records:
            return 0

        external_channels = {
            ch
            for ch in ("hes", "tes", "ces")
            if any(
                e_id in record_by_id and record_by_id[e_id].source_type not in {"seller_page", "review"}
                for e_id in channel_details[ch].get("evidence_ids", [])
            )
        }

        active_channels = sum(
            int(ch in external_channels)
            for ch in ("hes", "tes", "ces")
        )

        coverage = active_channels / 3.0

        unique_sources = {
            r.source_type
            for r in external_records
        }

        diversity = min(
            len(unique_sources)/5,1)

        volume = min(
            log1p(len(external_records))/2, 1)

        directness = (
            sum(self._relation_weight(r.relation_type) for r in external_records)
            / len(external_records)
            if external_records else 0
        )

        ecs = (
            coverage*40
            + diversity*30
            + volume*15
            + directness*15
        )

        return clamp(ecs)

    def _calculate_legacy_accs(
        self, hes: float, tes: float, ces: float, ecs: float
    ) -> Dict[str, Any]:
        base_weights = {"hes": 0.35, "tes": 0.40, "ces": 0.25}
        scores = {"hes": hes, "tes": tes, "ces": ces}
        active = {key: value for key, value in scores.items() if value > 0}
        denominator = sum(base_weights[key] for key in active)
        raw = (
            sum(base_weights[key] * active[key] for key in active) / denominator
            if denominator
            else 0.0
        )
        alpha = self.dynamic_weight_config.evidence_alpha
        ecs_alpha = self.dynamic_weight_config.ecs_alpha
        total_alpha = alpha + ecs_alpha
        if total_alpha <= 0:
            alpha, ecs_alpha = 0.85, 0.15
        else:
            alpha, ecs_alpha = alpha / total_alpha, ecs_alpha / total_alpha
        final = clamp(alpha * raw + ecs_alpha * ecs)
        return {
            "method": "fixed_weighting_existing_channels",
            "weights": base_weights,
            "raw_accs": round(raw, 2),
            "legacy_accs": round(final, 2),
            "evidence_alpha": round(alpha, 4),
            "ecs_alpha": round(ecs_alpha, 4),
        }

    def _calculate_dynamic_weighting(
        self,
        hes: float,
        tes: float,
        ces: float,
        ecs: float,
        channel_details: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        cfg = self.dynamic_weight_config
        scores = {"hes": hes, "tes": tes, "ces": ces}
        active = {key: value for key, value in scores.items() if value > 0}
        logits: Dict[str, float] = {}
        for channel in active:
            prior = max(1e-6, cfg.base_channel_priors.get(channel, 1.0 / 3.0))
            detail = channel_details[channel]
            diversity = min(len(detail["source_types"]) / 3.0, 1.0)
            count_signal = min(detail["evidence_count"] / 4.0, 1.0)
            avg_recency = float(detail.get("avg_recency", 0.5))
            logits[channel] = (
                log(prior)
                + cfg.directness_signal * detail["avg_directness"]
                + cfg.diversity_signal * diversity
                + cfg.count_signal * count_signal
                + cfg.recency_signal * avg_recency
                - cfg.concentration_penalty * detail["max_source_share"]
            )
        weights = _softmax(logits)
        dynamic_evidence_score = sum(weights[key] * active[key] for key in active)

        evidence_alpha = cfg.evidence_alpha
        ecs_alpha = cfg.ecs_alpha
        alpha_sum = evidence_alpha + ecs_alpha
        if alpha_sum <= 0:
            evidence_alpha, ecs_alpha = 0.85, 0.15
        else:
            evidence_alpha /= alpha_sum
            ecs_alpha /= alpha_sum
            
        BASE = 20.0
        dynamic_accs = clamp(
            evidence_alpha * dynamic_evidence_score 
            + ecs_alpha * ecs
        )
        complete_weights = {key: round(weights.get(key, 0.0), 4) for key in ("hes", "tes", "ces")}
        return {
            "enabled": self.enable_dynamic_weighting,
            "method": "quality_context_softmax_hes_tes_ces_with_ecs_blend",
            "weights": complete_weights,
            "logits": {key: round(value, 4) for key, value in logits.items()},
            "active_channels": list(active),
            "excluded_channels": [key for key in scores if key not in active],
            "dynamic_evidence_score": round(dynamic_evidence_score, 2),
            "dynamic_accs": round(dynamic_accs, 2),
            "base_scores": {
                "hes": round(hes, 2),
                "tes": round(tes, 2),
                "ces": round(ces, 2),
                "ecs": round(ecs, 2),
            },
            "formula": {
                "dynamic_evidence_score": "sum(dynamic_channel_weight * channel_score)",
                "dynamic_accs": "evidence_alpha * dynamic_evidence_score + ecs_alpha * ECS",
                "evidence_alpha": round(evidence_alpha, 4),
                "ecs_alpha": round(ecs_alpha, 4),
                "weight_signals": [
                    "base_prior",
                    "relation_directness",
                    "source_diversity",
                    "deduplicated_evidence_count",
                    "source_concentration",
                ],
                "note": "Channel score itself is not used to increase its own dynamic weight.",
            },
        }

    # ------------------------------------------------------------------
    # Confidence, sufficiency, verdict
    # ------------------------------------------------------------------

    def _calculate_confidence(
        self,
        used_caps: List[CapabilityScore],
        records: List[EvidenceRecord],
        channel_details: Dict[str, Dict[str, Any]],
        claim_text: str,
    ) -> Dict[str, Any]:
        if not used_caps:
            return {
                "score": 0.0,
                "direct_evidence_ratio": 0.0,
                "source_diversity": 0.0,
                "channel_coverage": 0.0,
                "claim_evidence_consistency": 0.0,
                "source_independence": 0.0,
            }

        contributing_ids = {
            contribution.evidence_id
            for cap in used_caps
            for contribution in self._contributions_by_cap.get(cap.capability_id, [])
        }
        contributing_records = [record for record in records if record.evidence_id in contributing_ids]
        external_records = [
            record
            for record in contributing_records
            if record.source_type not in {"seller_page", "review"}
        ]
        if external_records:
            direct_count = sum(
                normalize_relation_type(record.relation_type)
                in {"direct_model", "direct_product"}
                for record in external_records
            )
            direct_ratio = direct_count / len(external_records)
            sources = {record.source_type for record in external_records}
            source_diversity = min(len(sources) / 4.0, 1.0)
            counts = self._count_evidence_by_source(external_records)
            max_share = max(counts.values()) / len(external_records)
            source_independence = 1.0 - max_share
        else:
            direct_ratio = source_diversity = source_independence = 0.0

        record_by_id = {record.evidence_id: record for record in records}
        def channel_has_external(channel: str) -> bool:
            return any(
                evidence_id in record_by_id
                and record_by_id[evidence_id].source_type not in {"seller_page", "review"}
                for evidence_id in channel_details[channel].get("evidence_ids", [])
            )
        channel_coverage = (
            int(channel_has_external("hes"))
            + int(channel_has_external("tes"))
        ) / 2.0
        top_required = sorted(
            (cap.required_fulfillment_ratio for cap in used_caps), reverse=True
        )[:3]
        requirement_consistency = sum(top_required) / len(top_required) if top_required else 0.0
        top_claims = sorted((cap.base_claim_score for cap in used_caps), reverse=True)[:3]
        claim_strength = (sum(top_claims) / len(top_claims) / 100.0) if top_claims else 0.0
        claim_evidence_consistency = min(claim_strength, requirement_consistency) + 0.5 * abs(
            claim_strength - requirement_consistency
        )
        claim_evidence_consistency = clamp01(1.0 - claim_evidence_consistency + min(claim_strength, requirement_consistency))

        score = 100.0 * (
            direct_ratio * 0.30
            + source_diversity * 0.22
            + channel_coverage * 0.22
            + requirement_consistency * 0.16
            + source_independence * 0.10
        )
        return {
            "score": round(clamp(score), 2),
            "direct_evidence_ratio": round(direct_ratio, 4),
            "source_diversity": round(source_diversity, 4),
            "channel_coverage": round(channel_coverage, 4),
            "claim_evidence_consistency": round(claim_evidence_consistency, 4),
            "requirement_consistency": round(requirement_consistency, 4),
            "source_independence": round(source_independence, 4),
        }

    def _calculate_evidence_sufficiency(
        self,
        used_caps: List[CapabilityScore],
        records: List[EvidenceRecord],
        channel_details: Dict[str, Dict[str, Any]],
        confidence_details: Dict[str, Any],
    ) -> float:
        if not used_caps:
            return 0.0
            
        used_contributions = [
            contribution
            for cap in used_caps
            for contribution in self._contributions_by_cap.get(cap.capability_id, [])
        ]
        external_contributions = [
            contribution
            for contribution in used_contributions
            if contribution.source_type not in {"seller_page", "review"}
        ]
        
        external_count = len(external_contributions)
        count_score = 1.0 - exp(-external_count / 4.0)

        direct_present = any(contribution.direct for contribution in external_contributions)

        external_channels = {
            self._contribution_channel(contribution)
            for contribution in external_contributions
        }

        active_channels = sum(
            1
            for ch in ("hes", "tes", "ces")
            if ch in external_channels
        )

        core_coverage = active_channels / 3.0

        source_diversity = min(
            len({c.source_type for c in external_contributions}) / 5.0,
            1.0
        )

        sufficiency = (
            count_score * 0.40
            + (1.0 if direct_present else 0.20) * 0.20
            + core_coverage * 0.25
            + source_diversity * 0.15
        )
        
        return clamp01(sufficiency)

    def _record_is_company_capability_for_any(
        self, record: EvidenceRecord, used_caps: List[CapabilityScore]
    ) -> bool:
        return any(
            self._effective_relation_type(record, cap.capability_id) == "company_capability"
            and self._capability_relevance(cap.capability_id, record) >= 0.60
            for cap in used_caps
        )

    def _decide_verdict(
        self,
        accs: float,
        confidence: float,
        sufficiency: float,
        positive_caps: List[CapabilityScore],
    ) -> Tuple[str, str]:
        thresholds = self.engine_config.thresholds
        if not positive_caps:
            return "AI 기능 주장 미확인 / Not Evaluated", "판정 제외"
        if (
            accs >= thresholds.credible
            and sufficiency >= thresholds.minimum_sufficiency_for_credible
        ):
            return "높은 신뢰 상품 / Credible", "매우 낮음"
        if (
            accs >= thresholds.normal
            and sufficiency >= thresholds.minimum_sufficiency_for_normal
        ):
            return "신뢰 상품 / Normal", "낮음"
        if accs >= thresholds.suspected or confidence >= 35.0:
            return "워싱 의심 상품 / Suspected", "중간"
        return "AI 워싱 상품 / Washing", "높음"

    # ------------------------------------------------------------------
    # Explanations and future attention features
    # ------------------------------------------------------------------

    def _build_reasons(
        self,
        accs: float,
        legacy_accs: float,
        hes: float,
        tes: float,
        ces: float,
        ecs: float,
        confidence: float,
        sufficiency: float,
        verdict: str,
        risk_level: str,
        top_caps: List[CapabilityScore],
        records: List[EvidenceRecord],
        dynamic: Dict[str, Any],
    ) -> List[str]:
        reasons = [
            f"최종 ACCS는 {accs:.1f}점이며 동일 입력의 고정 가중치 점수는 {legacy_accs:.1f}점입니다.",
            f"HES {hes:.1f}, TES {tes:.1f}, CES {ces:.1f}, ECS {ecs:.1f}, CONF {confidence:.1f}로 계산되었습니다.",
        ]
        if top_caps:
            descriptions = ", ".join(
                f"{cap.capability_name_ko}({cap.final_score:.1f})" for cap in top_caps[:3]
            )
            reasons.append(f"주요 AI capability는 {descriptions}입니다.")

        direct = sum(
            record.relation_type in {"direct_model", "direct_product"} for record in records
        )
        indirect = sum(
            record.relation_type in {"company_capability", "product_family"}
            for record in records
        )
        reasons.append(
            f"중복 제거 후 직접 제품·모델 근거 {direct}건, 관련 회사·제품군 간접 근거 {indirect}건을 사용했습니다."
        )
        if indirect:
            reasons.append(
                "회사가 다른 제품에서 보유한 관련 기술은 간접 근거로 유지하되, 정확한 모델 근거보다 낮은 기여 상한을 적용했습니다."
            )
        if sufficiency < self.engine_config.thresholds.minimum_sufficiency_for_normal:
            reasons.append(
                f"근거 충분도({sufficiency:.2f})가 정상 판정 최소 기준보다 낮아 높은 ACCS만으로 정상 판정하지 않았습니다."
            )
        missing = [
            f"{cap.capability_name_ko}: {', '.join(cap.missing_required_components[:2])}"
            for cap in top_caps
            if cap.missing_required_components
        ]
        if missing:
            reasons.append("미충족 필수 구성요소: " + " / ".join(missing[:3]))
        weights = dynamic.get("weights", {})
        reasons.append(
            "동적 가중치는 채널 점수 자체가 아니라 직접성·출처 다양성·중복 제거 근거 수를 사용했습니다: "
            f"HES {weights.get('hes', 0):.3f}, TES {weights.get('tes', 0):.3f}, CES {weights.get('ces', 0):.3f}."
        )
        reasons.append(f"최종 판정은 '{verdict}', 위험도는 '{risk_level}'입니다.")
        return unique_keep_order(reasons)

    def _build_evidence_audit(self, records: List[EvidenceRecord]) -> List[Dict[str, Any]]:
        contributions_by_evidence: Dict[str, List[EvidenceContribution]] = {}
        for items in self._contributions_by_cap.values():
            for item in items:
                contributions_by_evidence.setdefault(item.evidence_id, []).append(item)
        audit: List[Dict[str, Any]] = []
        for record in records:
            contributions = sorted(
                contributions_by_evidence.get(record.evidence_id, []),
                key=lambda item: item.support,
                reverse=True,
            )
            audit.append(
                {
                    "evidence_id": record.evidence_id,
                    "source_record_id": record.source_record_id,
                    "source_type": record.source_type,
                    "title": record.title,
                    "status": record.status,
                    "relation_type": record.relation_type,
                    "match_confidence": record.match_confidence,
                    "matched_company": record.matched_company,
                    "matched_product": record.matched_product,
                    "matched_model": record.matched_model,
                    "capability_ids": record.capability_ids,
                    "matched_components": record.matched_components,
                    "top_contributions": [asdict(item) for item in contributions[:8]],
                }
            )
        return audit

    def _build_attention_features(
        self,
        records: List[EvidenceRecord],
        capability_scores: List[CapabilityScore],
        channel_details: Dict[str, Dict[str, Any]],
        confidence_details: Dict[str, Any],
        sufficiency: float,
    ) -> Dict[str, Any]:
        """Structured features suitable for a later attention model.

        This does not train or infer with an attention model yet. It fixes a
        stable, auditable feature contract so the next stage can learn weights
        without changing data collection and labeling formats again.
        """
        return {
            "schema_version": "attention-input-v1",
            "evidence_nodes": [
                {
                    "evidence_id": record.evidence_id,
                    "source_type": record.source_type,
                    "relation_type": record.relation_type,
                    "match_confidence": round(record.match_confidence, 4),
                    "source_quality": round(self._source_quality(record), 4),
                    "recency": round(_recency_score(record.published_at), 4),
                    "capability_ids": record.capability_ids,
                    "component_ids": record.matched_components,
                }
                for record in records
            ],
            "capability_nodes": [
                {
                    "capability_id": score.capability_id,
                    "claim_score": score.base_claim_score,
                    "required_support": score.required_fulfillment_ratio,
                    "optional_support": score.optional_fulfillment_ratio,
                    "final_rule_score": score.final_score,
                    "positive_claim": score.positive_claim,
                    "evidence_ids": score.evidence_ids,
                }
                for score in capability_scores
            ],
            "global_features": {
                "hes": channel_details["hes"]["score"],
                "tes": channel_details["tes"]["score"],
                "ces": channel_details["ces"]["score"],
                "confidence": confidence_details["score"],
                "sufficiency": round(sufficiency, 4),
                "evidence_count": len(records),
                "source_count": len({record.source_type for record in records}),
            },
        }

    @staticmethod
    def _count_evidence_by_source(records: List[EvidenceRecord]) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for record in records:
            result[record.source_type] = result.get(record.source_type, 0) + 1
        return dict(sorted(result.items()))

    @staticmethod
    def _count_evidence_by_relation(records: List[EvidenceRecord]) -> Dict[str, int]:
        result: Dict[str, int] = {}
        for record in records:
            result[record.relation_type] = result.get(record.relation_type, 0) + 1
        return dict(sorted(result.items()))


# ---------------------------------------------------------------------------
# Existing crawler/API bundle adapter
# ---------------------------------------------------------------------------


def _model_match(model: str, text: str) -> bool:
    model_compact = compact_text(model)
    text_compact = compact_text(text)
    if len(model_compact) < 4:
        return False
    return model_compact in text_compact


def _company_match(company: str, text: str) -> bool:
    company_compact = compact_text(company)
    text_compact = compact_text(text)
    if len(company_compact) < 2:
        return False
    return company_compact in text_compact


def _status_from_result(value: Any) -> str:
    if _looks_negative_result(value):
        return "no_match"
    return "verified"


def _record_from_mapping(
    row: Mapping[str, Any],
    source_type: str,
    target_company_name: str,
    model_param: str,
    default_title: str,
    assume_company_filtered: bool = False,
) -> EvidenceRecord:
    text = _flatten_text(row)
    title = _first_nonempty(
        row,
        [
            "title",
            "name",
            "발명의명칭",
            "발명의명칭(한글)",
            "invention_title",
            "product_name",
            "equip_name",
            "model_name",
            "solution_name",
        ],
    ) or default_title
    matched_model = _model_match(model_param, text)
    explicit_company = _first_nonempty(
        row,
        [
            "company_name",
            "manufacturer",
            "manufacturer_name",
            "applicant",
            "applicant_name",
            "기업명",
            "회사명",
            "제조사",
            "출원인",
        ],
    )
    if explicit_company:
        # A filtered API response may still contain a different company.  An
        # explicit mismatch always wins over the search-context assumption.
        matched_company = _company_match(target_company_name, explicit_company)
    else:
        matched_company = _company_match(target_company_name, text) or (
            assume_company_filtered and bool(target_company_name)
        )
    matched_product = matched_model or bool(row.get("matched_product", False))
    relation = (
        "direct_model"
        if matched_model
        else "direct_product"
        if matched_product
        else "company_general"
        if matched_company
        else "unmatched"
    )
    return EvidenceRecord(
        source_type=source_type,
        text=text,
        title=title,
        scope="model" if matched_model else "product" if matched_product else "company",
        meta=dict(row),
        matched_company=matched_company,
        matched_product=matched_product,
        matched_model=matched_model,
        matched_components=list(row.get("matched_components", []) or []),
        capability_ids=list(row.get("capability_ids", []) or []),
        status=normalize_status(row.get("status", "verified")),
        relation_type=relation,
        match_confidence=float(row.get("match_confidence", 0.0) or 0.0),
        source_record_id=_first_nonempty(
            row,
            [
                "source_record_id",
                "record_id",
                "cert_no",
                "application_no",
                "application_number",
                "출원번호",
                "일련번호",
                "registration_no",
                "id",
                "url",
            ],
        ),
        published_at=_first_nonempty(
            row, ["published_at", "date", "cert_date", "application_date", "출원일자", "공개일자", "등록일"]
        ),
    )


def bundle_to_evidence_records(
    product_json: Optional[Dict[str, Any]] = None,
    norm_info: Optional[Dict[str, Any]] = None,
    db_results: Optional[List[Dict[str, Any]]] = None,
    jodale_result: Optional[Any] = None,
    tipa_result: Optional[Any] = None,
    koraia_result: Optional[Any] = None,
    kaiac_result: Optional[Any] = None,
    nipa_result: Optional[Any] = None,
    ntis_result: Optional[Any] = None,
    iitp_result: Optional[Any] = None,
    patent_items_df: Optional[Any] = None,
    cert_results: Optional[List[Dict[str, Any]]] = None,
    dart_result: Optional[Dict[str, Any]] = None,
    target_company_name: str = "",
    model_param: str = "",
) -> List[EvidenceRecord]:
    """Convert current EASy crawler outputs to normalized evidence records.

    Crucially, this function never sets every record's matched_company flag to
    True and never injects synthetic baseline claims.
    """
    records: List[EvidenceRecord] = []
    product_json = product_json or {}

    # First-party product page: it is the analyzed product, therefore product
    # relation is valid. Exact model relation still requires the model token.
    seller_text = _flatten_text(
        {
            "name": product_json.get("name") or product_json.get("product_name"),
            "description": product_json.get("description"),
            "specs": product_json.get("specs"),
            "raw_specs": product_json.get("raw_specs"),
            "ocr_text": product_json.get("ocr_text") or product_json.get("ocr_extracted_text"),
        }
    )
    if seller_text.strip():
        matched_model = _model_match(model_param, seller_text)
        records.append(
            EvidenceRecord(
                source_type="seller_page",
                text=seller_text,
                title=str(product_json.get("name") or product_json.get("product_name") or "상품 페이지"),
                scope="model" if matched_model else "product",
                matched_company=bool(target_company_name),
                matched_product=True,
                matched_model=matched_model,
                relation_type="direct_model" if matched_model else "direct_product",
                match_confidence=0.98 if matched_model else 0.90,
                status="verified",
                source_record_id=str(product_json.get("url") or product_json.get("pcode") or "seller-page"),
                meta={"first_party_claim": True},
            )
        )

    # KC/RRA local DB rows.
    for row in db_results or []:
        if not isinstance(row, Mapping):
            continue
        source = normalize_source_type(
            row.get("source_type") or row.get("cert_type") or "rra"
        )
        if source not in {"kc", "rra"}:
            source = "rra"
        record = _record_from_mapping(
            row,
            source,
            target_company_name,
            model_param,
            "KC/RRA 인증",
            assume_company_filtered=True,
        )
        if is_valid_evidence_status(record.status):
            records.append(record)

    def append_single_result(value: Any, source: str, title: str) -> None:
        if value is None or _looks_negative_result(value):
            return
        if isinstance(value, Mapping):
            row = value
        else:
            row = {"detail": value, "status": "verified"}
        record = _record_from_mapping(
            row,
            source,
            target_company_name,
            model_param,
            title,
            assume_company_filtered=True,
        )
        if record.relation_type == "company_general":
            record.match_confidence = min(record.match_confidence, 0.72)
        records.append(record)

    append_single_result(jodale_result, "procurement", "조달/나라장터 결과")
    append_single_result(tipa_result, "tipa", "TIPA 결과")
    append_single_result(koraia_result, "koraia", "KORAIA 결과")
    append_single_result(kaiac_result, "kaiac", "KAIAC 결과")
    append_single_result(nipa_result, "nipa", "NIPA 결과")
    append_single_result(ntis_result, "ntis", "NTIS R&D 과제 실적")

    # Patents are often searched by company. That makes company matching valid,
    # but not product/model matching. Capability relevance is evaluated later.
    patent_rows: List[Dict[str, Any]] = []
    if patent_items_df is not None:
        if isinstance(patent_items_df, pd.DataFrame):
            patent_rows = patent_items_df.to_dict(orient="records")
        elif isinstance(patent_items_df, list):
            patent_rows = [row for row in patent_items_df if isinstance(row, Mapping)]
    for row in patent_rows:
        record = _record_from_mapping(
            row,
            "kipris",
            target_company_name,
            model_param,
            "KIPRIS 특허",
            assume_company_filtered=True,
        )
        if record.matched_model:
            record.relation_type = "direct_model"
        elif record.matched_product:
            record.relation_type = "direct_product"
        else:
            is_product_ai = row.get("relevance_type") == "product_ai"
            if is_product_ai:
                record.relation_type = "product_family" 
                record.match_confidence = 0.88
            else:
                record.relation_type = "company_capability"
                record.match_confidence = 0.45
        records.append(record)

    for row in cert_results or []:
        if not isinstance(row, Mapping) or _looks_negative_result(row):
            continue
        raw_source = normalize_text(
            row.get("source_type") or row.get("cert_type") or row.get("type")
        )
        if "nep" in raw_source:
            source = "nep"
        elif "net" in raw_source or "신기술" in raw_source:
            source = "net"    
        elif "sandbox" in raw_source or "실증" in raw_source or "특례" in raw_source:
            source = "sandbox" 
        elif "tta" in raw_source:
            source = "tta"
        elif "kaiac" in raw_source:
            source = "kaiac"
        else:
            source = "gs"
        records.append(
            _record_from_mapping(
                row,
                source,
                target_company_name,
                model_param,
                "인증 결과",
                assume_company_filtered=True,
            )
        )

    if dart_result is not None and not _looks_negative_result(dart_result):
        if isinstance(dart_result, Mapping):
            row = dart_result
        else:
            row = {"detail": dart_result, "status": "verified"}
        record = _record_from_mapping(
            row,
            "dart",
            target_company_name,
            model_param,
            "DART 공시",
            assume_company_filtered=True,
        )
        if not record.matched_model and not record.matched_product:
            record.relation_type = "company_general"
            record.match_confidence = min(record.match_confidence, 0.78)
        records.append(record)


    if iitp_result and isinstance(iitp_result, dict):
        for row in iitp_result.get("records", []) or iitp_result.get("items", []):
            if isinstance(row, dict) and row:
                is_product_ai = row.get("relevance_type") == "product_ai"
                records.append(
                    EvidenceRecord(
                        evidence_id=str(row.get("source_record_id") or row.get("과제번호") or f"iitp_{len(records)}"),
                        source_type="iitp",
                        relation_type="product_family" if is_product_ai else "company_capability",
                        match_confidence=0.88 if is_product_ai else 0.45,
                        raw_data=row,
                    )
                )

    return records
