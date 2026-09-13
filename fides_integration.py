"""Integration layer between the existing EASy crawlers and the finalized rule engine.

This module is deliberately thin.  Crawlers collect raw evidence, the adapter
normalizes it, and :class:`OntologyAnalysisEngine` is the only component that
calculates ACCS or decides a verdict.  The API/server layer must not overwrite
those values afterwards.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from analysis_engine import (
    AnalysisResult,
    OntologyAnalysisEngine,
    bundle_to_evidence_records,
)


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
