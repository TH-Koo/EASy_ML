"""Optional Suspicious-only correction after the authoritative ontology engine.

Portable JSON trees avoid loading executable pickle files or requiring sklearn
on the serving path. Scores and CEN weights are never changed by this policy.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from .features import CONTEXT_COLUMNS, feature_row, ontology_digest

LABELS = ("washing", "suspicious", "genuine")
FEATURE_COLUMNS = (
    "hes", "tes", "ces", "ecs", "mask_hes", "mask_tes", "mask_ces",
    *CONTEXT_COLUMNS,
)
S_VERDICT = "워싱 의심 상품 / Suspected"
S_RISK = "중간"
ROOT = Path(__file__).resolve().parents[1]


def verdict_label(verdict: Any) -> str:
    """Map explicit engine verdicts without confusing '워싱 의심' with Washing."""
    text = str(verdict or "").strip().lower()
    suffix = text.rsplit("/", 1)[-1].strip()
    if suffix in {"washing", "ai_washing"} or text == "워싱":
        return "washing"
    if suffix in {"suspected", "suspicious"} or text in {"의심", "워싱 의심 상품"}:
        return "suspicious"
    if suffix in {"normal", "credible", "genuine"} or text in {"정상", "정상 상품"}:
        return "genuine"
    return "not_evaluated"


def _integer_array(value, name):
    array = np.asarray(value)
    if array.ndim != 1 or array.dtype.kind not in "iu":
        raise ValueError(f"{name} must be a one-dimensional integer array")
    return array.astype(np.int64)


class PortableSOnlyModel:
    """A validated, read-only forest with sklearn-compatible float32 routing."""

    def __init__(self, path: str | Path):
        path = Path(path)
        if path.is_dir():
            path = path / "model.json"
        raw = path.read_bytes()
        artifact = json.loads(raw)
        if artifact.get("format_version") != 1 or artifact.get("policy") != "suspicious_only":
            raise ValueError("Unsupported S-only model format/policy")
        if artifact.get("labels") != list(LABELS):
            raise ValueError("S-only model label order mismatch")
        if artifact.get("feature_columns") != list(FEATURE_COLUMNS):
            raise ValueError("S-only model feature contract mismatch")
        self.threshold = float(artifact["threshold"])
        if not np.isfinite(self.threshold) or not 0.0 <= self.threshold <= 1.0:
            raise ValueError("Invalid S-only threshold")
        vocabulary = artifact["category_vocabulary"]
        if not isinstance(vocabulary, list) or any(not isinstance(v, str) or not v.strip() for v in vocabulary):
            raise ValueError("Invalid category vocabulary")
        if len(set(vocabulary)) != len(vocabulary):
            raise ValueError("Duplicate category vocabulary entries")
        self.categories = tuple(vocabulary)
        self._category_index = {v: i for i, v in enumerate(self.categories)}
        self.medians = np.asarray(artifact["feature_medians"], dtype=float)
        if self.medians.shape != (len(FEATURE_COLUMNS),) or not np.isfinite(self.medians).all():
            raise ValueError("Invalid training feature medians")
        self.metadata = artifact.get("metadata", {})
        if not isinstance(self.metadata, dict):
            raise ValueError("Model metadata must be an object")
        trees = artifact.get("trees")
        if not isinstance(trees, list) or not trees:
            raise ValueError("S-only model must contain at least one tree")
        self._trees = tuple(self._validate_tree(tree) for tree in trees)
        self.model_version = hashlib.sha256(raw).hexdigest()

    def _validate_tree(self, tree):
        left = _integer_array(tree["children_left"], "children_left")
        right = _integer_array(tree["children_right"], "children_right")
        feature = _integer_array(tree["feature"], "feature")
        thresholds = np.asarray(tree["threshold"], dtype=float)
        probabilities = np.asarray(tree["value"], dtype=float)
        size = len(left)
        if size == 0 or right.shape != (size,) or feature.shape != (size,) or thresholds.shape != (size,):
            raise ValueError("Inconsistent tree node array lengths")
        if probabilities.shape != (size, 3) or not np.isfinite(probabilities).all() or (probabilities < 0).any():
            raise ValueError("Invalid tree node probabilities")
        if not np.allclose(probabilities.sum(axis=1), 1.0, rtol=0, atol=1e-8):
            raise ValueError("Tree node probabilities must sum to one")
        if not np.isfinite(thresholds).all():
            raise ValueError("Tree thresholds must be finite")
        leaves = left == -1
        if not np.array_equal(leaves, right == -1):
            raise ValueError("Each node must have either zero or two children")
        internal = ~leaves
        if ((left[internal] < 0) | (left[internal] >= size) | (right[internal] < 0) | (right[internal] >= size)).any():
            raise ValueError("Tree child index is out of range")
        dimensions = len(FEATURE_COLUMNS) + len(self.categories)
        if ((feature[internal] < 0) | (feature[internal] >= dimensions)).any():
            raise ValueError("Tree feature index is out of range")
        seen = set()
        stack = [0]
        while stack:
            node = stack.pop()
            if node in seen:
                raise ValueError("Tree contains a cycle or shared child")
            seen.add(node)
            if not leaves[node]:
                stack.extend((int(left[node]), int(right[node])))
        if len(seen) != size:
            raise ValueError("Tree contains unreachable nodes")
        return left, right, feature, thresholds, probabilities

    def validate_ontology(self, directory: str | Path) -> None:
        expected = self.metadata.get("ontology_sha256")
        if expected and ontology_digest(directory) != expected:
            raise ValueError("S-only model ontology differs from the current ontology; retrain or disable correction")

    def predict_rows(self, rows: list[dict], categories: list[str]) -> np.ndarray:
        if len(rows) != len(categories):
            raise ValueError("One category is required per feature row")
        if not rows:
            return np.empty((0, 3), dtype=float)
        raw = np.asarray([[row[name] if row[name] is not None else np.nan for name in FEATURE_COLUMNS]
                          for row in rows], dtype=float)
        if np.isinf(raw).any():
            raise ValueError("Infinite S-only feature values are not allowed")
        raw = np.where(np.isnan(raw), self.medians[None, :], raw)
        categorical = np.zeros((len(rows), len(self.categories)), dtype=float)
        for index, category in enumerate(categories):
            position = self._category_index.get(str(category or "").strip())
            if position is not None:
                categorical[index, position] = 1.0
        with np.errstate(over="ignore"):
            inputs = np.column_stack([raw, categorical]).astype(np.float32)
        if not np.isfinite(inputs).all():
            raise ValueError("S-only feature values overflow float32")
        probabilities = np.zeros((len(rows), 3), dtype=float)
        for left, right, feature, thresholds, values in self._trees:
            nodes = np.zeros(len(rows), dtype=np.int64)
            active = left[nodes] != -1
            while active.any():
                indices = np.flatnonzero(active)
                current = nodes[indices]
                nodes[indices] = np.where(inputs[indices, feature[current]] <= thresholds[current],
                                          left[current], right[current])
                active = left[nodes] != -1
            probabilities += values[nodes]
        return probabilities / len(self._trees)

    def predict_result(self, result, product_type: str) -> dict:
        row = feature_row(result, product_type=product_type)
        probabilities = self.predict_rows([row], [product_type])[0]
        return {"probabilities": probabilities.tolist(),
                "category_known": str(product_type or "").strip() in self._category_index}


@lru_cache(maxsize=4)
def _load_model(path: str, modified_ns: int, size: int, ontology_hash: str):
    model = PortableSOnlyModel(path)
    expected = model.metadata.get("ontology_sha256")
    if expected and expected != ontology_hash:
        raise ValueError(
            f"S-only model ontology mismatch: model={path}; "
            f"expected={expected}; actual={ontology_hash}. "
            "Check FIDES_S_ONLY_MODEL and the ontology version used to train that artifact."
        )
    return model


def load_s_only_predictor():
    """Default off. Explicitly enabled but broken artifacts fail startup clearly."""
    enabled = os.environ.get("FIDES_S_ONLY_ENABLED", "0").strip().lower()
    if enabled in {"", "0", "false", "no", "off"}:
        return None
    if enabled not in {"1", "true", "yes", "on"}:
        raise ValueError("FIDES_S_ONLY_ENABLED must be 0 or 1")
    path = Path(os.environ.get("FIDES_S_ONLY_MODEL") or ROOT / "artifacts" / "s_only" / "model.json")
    if path.is_dir():
        path = path / "model.json"
    if not path.is_file():
        raise FileNotFoundError(f"S-only model not found: {path}. Set FIDES_S_ONLY_MODEL or disable correction.")
    stat = path.stat()
    return _load_model(str(path.resolve()), stat.st_mtime_ns, stat.st_size, ontology_digest(ROOT / "ontology"))


def apply_s_only(result, predictor, product_type: str = ""):
    """Keep W/G scores; only eligible W/G verdicts can move to Suspicious."""
    if predictor is None:
        return result
    if result.details is None:
        result.details = {}
    details = result.details
    if details.get("s_only_correction") is not None:
        return result
    original_label = verdict_label(result.verdict)
    trace = {
        "applied": False, "status": "unchanged", "reason_code": "baseline_not_eligible",
        "reason": "기존 의심·평가불가 판정은 S 전용 보정 대상이 아닙니다.",
        "original_verdict": result.verdict, "original_risk_level": result.risk_level,
        "original_label": original_label, "final_label": original_label,
        "final_verdict": result.verdict, "final_risk_level": result.risk_level,
        "threshold": float(predictor.threshold), "suspicious_score": None,
        "model_version": predictor.model_version, "category_known": None,
    }
    details["s_only_correction"] = trace
    if original_label not in {"washing", "genuine"}:
        return result
    try:
        prediction = predictor.predict_result(result, product_type)
        probabilities = np.asarray(prediction["probabilities"], dtype=float)
        if (probabilities.shape != (3,) or not np.isfinite(probabilities).all()
                or (probabilities < 0).any() or not np.isclose(probabilities.sum(), 1.0)):
            raise ValueError("Invalid auxiliary model probabilities")
        trace.update(suspicious_score=float(probabilities[1]),
                     category_known=bool(prediction["category_known"]),
                     probabilities=dict(zip(LABELS, probabilities.tolist())))
    except (ValueError, TypeError, KeyError, OverflowError, FloatingPointError):
        trace.update(reason_code="input_unavailable",
                     reason="보조모델 입력을 확인할 수 없어 기존 엔진 판정을 유지했습니다.")
        return result
    if int(np.argmax(probabilities)) != 1 or probabilities[1] < predictor.threshold:
        trace.update(reason_code="below_threshold",
                     reason="보조모델의 S 판정·확률 기준을 충족하지 않아 기존 판정을 유지했습니다.")
        return result
    audit_reason = (f"S 전용 보정: 기존 판정 '{result.verdict}'에서 보조모델의 의심 점수 "
                   f"{probabilities[1]:.1%}가 기준 {predictor.threshold:.0%} 이상으로 확인되어 "
                   "최종 판정을 '워싱 의심 상품 / Suspected'로 변경했습니다. 기존 ACCS와 가중치는 유지됩니다.")
    explanation = ("분석 결과에서 추가 확인이 필요한 신호가 발견되어 최종 판정을 '워싱 의심 상품'으로 표시했습니다. "
                   "상품의 AI 기능과 공개 근거를 추가 확인해 주세요.")
    trace.update(applied=True, status="corrected", reason_code="corrected_to_s", reason=explanation,
                 audit_reason=audit_reason,
                 final_label="suspicious", final_verdict=S_VERDICT, final_risk_level=S_RISK,
                 original_reasons=list(result.reasons or []))
    result.verdict, result.risk_level = S_VERDICT, S_RISK
    result.reasons = [reason.replace("최종 판정은", "기존 엔진 판정은")
                      for reason in (result.reasons or [])] + [explanation]
    for key in ("dynamic_weight_log", "attention_features"):
        log = details.get(key)
        if isinstance(log, dict):
            for field, original, final in (("verdict", trace["original_verdict"], S_VERDICT),
                                           ("risk_level", trace["original_risk_level"], S_RISK)):
                if field in log:
                    log[f"original_{field}"] = original
                    log[field] = final
    return result
