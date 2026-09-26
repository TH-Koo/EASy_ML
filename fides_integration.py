"""Integration layer between the existing EASy crawlers and the finalized rule engine.

This module is deliberately thin.  Crawlers collect raw evidence, the adapter
normalizes it, and :class:`OntologyAnalysisEngine` is the only component that
calculates ACCS or decides a verdict.  The API/server layer must not overwrite
those values afterwards.
"""
from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from analysis_engine import (
    AnalysisResult,
    OntologyAnalysisEngine,
    bundle_to_evidence_records,
)
from fides_config import DEFAULT_ENGINE_CONFIG, EngineConfig
from fides_scoring import CHANNELS, calculate_accs

DEFAULT_WEIGHT_CHECKPOINT = Path(__file__).resolve().parent / "artifacts" / "cen_senn_run"


def load_weight_predictor(checkpoint_dir: Optional[str] = None) -> Optional[Any]:
    """학습된 CEN 가중치 모델을 한 번 불러온다. 서버·파이프라인 시작 시 호출한다.

    경로 우선순위: 인자 → 환경변수 FIDES_WEIGHT_CHECKPOINT → artifacts/cen_senn_run.
    체크포인트나 torch 가 없으면 None 을 돌려주고, 엔진은 기존 규칙 기반
    동적 가중치로 동작한다. 어느 쪽인지는 결과의 model_version 으로 확인한다.

    체크포인트는 있는데 엔진 점수 설정(ECS 계수·판정 경계)과 다르면 여기서
    바로 실패시킨다. 그냥 넘기면 분석 요청마다 엔진 생성 단계에서 터진다.
    """
    path = Path(checkpoint_dir or os.environ.get("FIDES_WEIGHT_CHECKPOINT") or DEFAULT_WEIGHT_CHECKPOINT)
    if not ((path / "model.pt").is_file() and (path / "metadata.json").is_file()):
        print(f"[WeightPredictor] 체크포인트 없음({path}) → 규칙 기반 가중치 사용")
        return None
    try:
        from fides_ml.predict import WeightPredictor
    except ImportError as exc:
        print(f"[WeightPredictor] ML 패키지 없음({exc}) → 규칙 기반 가중치 사용. "
              "pip install -r requirements-ml.txt 필요")
        return None

    predictor = WeightPredictor(path)
    predictor.validate_engine_config(DEFAULT_ENGINE_CONFIG, DEFAULT_ENGINE_CONFIG.dynamic_weights)
    print(f"[WeightPredictor] 로드 완료: {path} ({predictor.model_version}, mode={predictor.config.mode})")
    return predictor


def infer_product_type(product_json: Optional[Mapping[str, Any]]) -> str:
    """가중치 모델에 넘길 제품군. category 가 없으면 다나와 스펙 첫 항목을 쓴다.

    학습 라벨의 product_type(예: "노트북")과 표기가 다르면 모델은 처음 보는
    제품군으로 취급한다(영벡터). 오류는 아니지만 제품군 정보가 빠진다.
    """
    product_json = product_json or {}
    category = str(product_json.get("category") or product_json.get("product_type") or "").strip()
    if category:
        return category
    raw_specs = str(product_json.get("raw_specs") or "")
    return raw_specs.split("/")[0].strip() if raw_specs else ""


def _flatten_text(value: Any, keep_keys: bool = False) -> str:
    """중첩된 값을 판정용 텍스트 한 덩어리로 편다.

    `keep_keys` 는 중첩 매핑의 키를 값과 함께 남길지 정한다. 스펙표는
    기능명이 키에 있고 값은 "지원" 하나뿐이라(`{"AI세탁건조": "지원"}`),
    키를 버리면 정작 판정에 필요한 기능명이 통째로 사라진다. 실제로
    캐시 330건 중 3건이 이 때문에 AI 기능을 하나도 인식하지 못했다.

    바깥에서 넘기는 최상위 매핑의 키는 "title"·"specs" 같은 필드 이름이라
    내용이 아니므로 기본값은 False 다. 그 안의 중첩 매핑부터 키를 살린다.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        parts = []
        for key, item in value.items():
            text = _flatten_text(item, keep_keys=True)
            if keep_keys and str(key).strip():
                parts.append(f"{key} {text}".strip())
            elif text:
                parts.append(text)
        return " ".join(part for part in parts if part)
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        return " ".join(
            part for part in (_flatten_text(item, keep_keys=keep_keys) for item in value) if part
        )
    return str(value)


def _get_first(mapping: Optional[Mapping[str, Any]], *keys: str, default: Any = None) -> Any:
    if not isinstance(mapping, Mapping):
        return default
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def build_claim_inputs(
    product_json: Optional[Dict[str, Any]],
    norm_info: Optional[Dict[str, Any]],
    ocr_result: Optional[Any] = None,
) -> tuple[str, str, List[str]]:
    """Build product-claim text without dropping raw title/spec fields.

    External patents, disclosures and certifications are not inserted into the
    claim text. They may validate a product claim, but cannot create one.
    """
    product_json = product_json or {}
    norm_info = norm_info or {}

    # Keep both structured specs and raw_specs.  The previous _get_first based
    # construction silently discarded raw_specs whenever specs was non-empty,
    # which caused labels such as "AI노트북" or "Copilot+ PC" to disappear.
    ad_text = _flatten_text(
        {
            "title": product_json.get("title"),
            "name": product_json.get("name"),
            "product_name": product_json.get("product_name"),
            "model_name": product_json.get("model_name"),
            "description": product_json.get("description"),
            "summary": product_json.get("summary"),
            "detail": product_json.get("detail"),
            "category": product_json.get("category") or product_json.get("product_category"),
            "specs": product_json.get("specs"),
            "raw_specs": product_json.get("raw_specs"),
            "specifications": product_json.get("specifications"),
            "product_ocr_text": product_json.get("ocr_text")
            or product_json.get("ocr_extracted_text"),
            "normalized_product_name": norm_info.get("product_name") or norm_info.get("name"),
            "normalized_model_name": norm_info.get("model_name") or norm_info.get("model"),
        }
    )

    if isinstance(ocr_result, Mapping):
        ocr_text = _flatten_text(
            _get_first(
                ocr_result,
                "text",
                "ocr_text",
                "extracted_text",
                "full_text",
                "result",
                default="",
            )
        )
    else:
        ocr_text = _flatten_text(ocr_result)

    extra_texts: List[str] = []
    for candidate in (
        product_json.get("feature_text"),
        product_json.get("features"),
        product_json.get("review_summary"),
        product_json.get("reviews"),
    ):
        text = _flatten_text(candidate).strip()
        if text:
            extra_texts.append(text)
    return ad_text, ocr_text, extra_texts


def secure_analyze_bundle(
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
    ocr_result: Optional[Any] = None,
    ontology_dir: Optional[str] = None,
    enable_dynamic_weighting: bool = True,
    weight_predictor: Optional[Any] = None,
    product_type: str = "",
    engine_config: Optional[EngineConfig] = None,
    **_: Any,
) -> AnalysisResult:
    """Normalize one crawler bundle and return one authoritative analysis result.

    Backward-compatible keyword arguments are accepted and ignored so this
    function can replace the former ``secure_analyze_bundle`` without forcing
    crawler changes.  It does **not** inject synthetic hardware/technology
    baselines, force company matching, or post-process ACCS.
    """
    norm_info = norm_info or {}
    product_json = product_json or {}

    if not target_company_name:
        target_company_name = str(
            _get_first(
                norm_info,
                "company_name",
                "manufacturer",
                "brand",
                default=_get_first(product_json, "manufacturer", "brand", default=""),
            )
            or ""
        )
    if not model_param:
        model_param = str(
            _get_first(
                norm_info,
                "model_name",
                "model",
                default=_get_first(product_json, "model_name", "model", default=""),
            )
            or ""
        )

    ontology_path = Path(ontology_dir or Path(__file__).resolve().parent / "ontology")
    engine = OntologyAnalysisEngine(
        str(ontology_path),
        enable_dynamic_weighting=enable_dynamic_weighting,
        weight_predictor=weight_predictor,
        engine_config=engine_config,
    )

    evidence_records = bundle_to_evidence_records(
        product_json=product_json,
        norm_info=norm_info,
        db_results=db_results,
        jodale_result=jodale_result,
        tipa_result=tipa_result,
        koraia_result=koraia_result,
        kaiac_result=kaiac_result,
        nipa_result=nipa_result,
        ntis_result=ntis_result,
        iitp_result=iitp_result,
        patent_items_df=patent_items_df,
        cert_results=cert_results,
        dart_result=dart_result,
        target_company_name=target_company_name,
        model_param=model_param,
    )
    ad_text, ocr_text, extra_texts = build_claim_inputs(
        product_json=product_json,
        norm_info=norm_info,
        ocr_result=ocr_result,
    )

    result = engine.analyze(
        evidence_records=evidence_records,
        ad_text=ad_text,
        ocr_text=ocr_text,
        extra_texts=extra_texts,
        product_type=str(product_type or product_json.get("category") or product_json.get("product_type") or ""),
    )
    # These fields are useful for benchmark/debugging and do not change scoring.
    result.details["integration"] = {
        "company": target_company_name,
        "model": model_param,
        "ontology_dir": str(ontology_path),
        "authoritative_score_source": "OntologyAnalysisEngine.analyze",
        "post_score_override": False,
    }
    return result


def analysis_result_to_dict(result: AnalysisResult) -> Dict[str, Any]:
    """Convert the result to a JSON-serializable mapping without altering it."""
    if is_dataclass(result):
        return asdict(result)
    if isinstance(result, Mapping):
        return dict(result)
    raise TypeError(f"Unsupported analysis result type: {type(result)!r}")


def weighting_summary(result: AnalysisResult) -> Dict[str, Any]:
    """API·DB·화면에 넘길 가중치 요약. 값은 엔진 결과를 그대로 옮긴다."""
    dynamic = (result.details or {}).get("dynamic_weighting") or {}
    weights = dynamic.get("weights", {})
    formula = dynamic.get("formula", {})
    contributions = dynamic.get("contributions")
    if contributions is None and weights:
        # 규칙 기반 경로는 엔진이 기여도를 따로 남기지 않는다. 엔진과 같은
        # 산식(fides_scoring)으로 되살려 화면이 두 경로를 같은 모양으로 그린다.
        base = dynamic.get("base_scores", {})
        contributions = calculate_accs(
            {c: base.get(c, 0.0) for c in CHANNELS},
            {c: weights.get(c, 0.0) for c in CHANNELS},
            base.get("ecs", 0.0),
            evidence_alpha=formula.get("evidence_alpha", 0.85),
            ecs_alpha=formula.get("ecs_alpha", 0.15),
        )["contributions"]
    return {
        "method": dynamic.get("method"),
        # 학습 모델을 거쳤을 때만 채워진다. None 이면 규칙 기반 경로.
        "model_version": dynamic.get("model_version"),
        "weight_status": dynamic.get("weight_status"),
        "weights": weights,
        "contributions": contributions,
        "active_channels": dynamic.get("active_channels", []),
        "evidence_alpha": formula.get("evidence_alpha"),
        "ecs_alpha": formula.get("ecs_alpha"),
    }


def result_consistency_errors(result: AnalysisResult) -> List[str]:
    """Return audit errors when logs and the public result disagree."""
    errors: List[str] = []
    details = result.details or {}
    dynamic_log = details.get("dynamic_weight_log") or {}
    dynamic_accs = dynamic_log.get("dynamic_accs")
    if dynamic_accs is not None and round(float(dynamic_accs), 2) != round(result.accs, 2):
        errors.append(
            f"final accs({result.accs}) != dynamic log accs({dynamic_accs})"
        )
    if dynamic_log.get("verdict") and dynamic_log.get("verdict") != result.verdict:
        errors.append(
            f"final verdict({result.verdict}) != dynamic log verdict({dynamic_log.get('verdict')})"
        )
    return errors
