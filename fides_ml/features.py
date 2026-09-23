"""Versioned feature contract shared by offline training and live inference."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from fides_scoring import CHANNELS

SCHEMA_VERSION = "fides-cen-senn-v1"
SIGNALS = ("count", "diversity", "directness", "recency", "concentration")
CONTEXT_COLUMNS = tuple(f"ctx_{c}_{s}" for c in CHANNELS for s in SIGNALS)
MASK_COLUMNS = tuple(f"mask_{c}" for c in CHANNELS)
PRIORS = (0.35, 0.40, 0.25)


def read_csv(path: str | Path) -> pd.DataFrame:
    """Keep identifiers as strings, including numeric-looking model IDs."""
    try:
        return pd.read_csv(path, encoding="utf-8-sig", dtype=str).fillna("")
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="cp949", dtype=str).fillna("")


def write_json(path: str | Path, value: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def normalize_label(value: Any) -> str | None:
    """No pseudo-labels: targets come only from the supplied reference label column."""
    text = str(value).strip().lower()
    if text in {"genuine", "normal", "정상", "credible"}:
        return "genuine"
    if text in {"washing", "ai_washing", "워싱"}:
        return "washing"
    if text in {"suspicious", "suspected", "의심"}:
        return "suspicious"
    if text in {"", "insufficient", "unknown", "unlabeled", "미확인"}:
        return None
    raise ValueError(f"Unknown ground-truth label: {value!r}")


def channel_feature_row(channel_scores: Mapping, channel_details: Mapping, *,
                        product_type="", sample_id="live", channel_mask=None) -> dict:
    """Build input BEFORE the engine has calculated ACCS/CONF/verdict.

    Scores are accepted for validation and mask compatibility, but the gate's
    continuous input remains evidence quality. ECS and labels are not needed.
    """
    if not all(c in channel_scores and c in channel_details for c in CHANNELS):
        raise ValueError("hes, tes, ces scores and channel_details are required")
    if channel_mask is None:
        channel_mask = {c: float(channel_scores[c]) > 0 for c in CHANNELS}
    if set(channel_mask) != set(CHANNELS) or any(v not in (0, 1, False, True) for v in channel_mask.values()):
        raise ValueError("channel_mask must have exactly hes, tes, ces with 0/1 values")
    row = {"schema_version": SCHEMA_VERSION, "sample_id": sample_id, "product_type": product_type}
    for c in CHANNELS:
        info = channel_details[c]
        row[c] = channel_scores[c]
        row[f"mask_{c}"] = int(channel_mask[c])
        values = (min(float(info.get("evidence_count", 0)) / 4.0, 1.0),
                  min(len(info.get("source_types") or []) / 3.0, 1.0),
                  float(info.get("avg_directness", 0.0)),
                  float(info.get("avg_recency", 0.5)),
                  float(info.get("max_source_share", 0.0)))
        row.update({f"ctx_{c}_{s}": v for s, v in zip(SIGNALS, values)})
    return row


def feature_row(result: Any, *, product_type: str = "", sample_id: str = "") -> dict:
    """Adapt the ACTUAL AnalysisResult contract on EASy main.

    Current main has fallback channel scores > 0 with channel_details.active
    false. Its dynamic_weighting.active_channels is the scored channel set;
    prefer that explicit set to keep the original score path consistent.
    Generic scored CSVs instead require explicit masks: a measured zero may
    be active, and is not automatically interpreted as missing.
    """
    d = asdict(result) if is_dataclass(result) else dict(result)
    details = d.get("details") or {}
    channel_details = details.get("channel_details") or {}
    dynamic = details.get("dynamic_weighting") or {}
    if not all(c in d for c in CHANNELS):
        raise ValueError("AnalysisResult must contain hes, tes, ces; scores cannot be fabricated")
    if not all(c in channel_details for c in CHANNELS):
        raise ValueError("AnalysisResult.details.channel_details is required for context features")
    active = dynamic.get("active_channels")
    if active is None:
        active = [c for c in CHANNELS if channel_details[c].get("active", False)]
    if set(active) - set(CHANNELS):
        raise ValueError(f"Unexpected active channels: {active}")
    row = channel_feature_row(d, channel_details, product_type=product_type, sample_id=sample_id,
                              channel_mask={c: int(c in active) for c in CHANNELS})
    # Audit-only fields, NEVER fed to the weight network or used as labels.
    row.update({
        "engine_version": details.get("engine_version", "unknown"),
        "legacy_accs": details.get("legacy_accs", ""),
        "rule_dynamic_accs": dynamic.get("dynamic_accs", d.get("accs", "")),
        "ecs": d.get("ecs", ""),
        "conf_audit_only": d.get("conf", ""),
        "channel_mask_policy": "engine_active_channels",
    })
    return row


def score_bundle(bundle: Mapping[str, Any], engine: Any) -> Any:
    """Use the existing engine without importing crawlers, keys or the server."""
    from analysis_engine import bundle_to_evidence_records
    from fides_integration import build_claim_inputs

    allowed = inspect.signature(bundle_to_evidence_records).parameters
    records = bundle_to_evidence_records(**{k: v for k, v in bundle.items() if k in allowed})
    ad, ocr, extra = build_claim_inputs(bundle.get("product_json"), bundle.get("norm_info"), bundle.get("ocr_result"))
    product = bundle.get("product_json") or {}
    return engine.analyze(records, ad_text=ad, ocr_text=ocr, extra_texts=extra,
                          product_type=str(product.get("category") or product.get("product_type") or ""))


def validate_features(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    required = ["sample_id", "product_type", *CHANNELS, *MASK_COLUMNS, *CONTEXT_COLUMNS]
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing feature columns: {missing}. Run `python -m fides_ml prepare` first.")
    if frame.empty:
        raise ValueError("Feature table is empty")
    if "schema_version" in frame and not frame.schema_version.eq(SCHEMA_VERSION).all():
        raise ValueError("Feature schema version mismatch")
    if frame.sample_id.astype(str).str.strip().eq("").any() or frame.sample_id.duplicated().any():
        raise ValueError("sample_id must be nonempty and unique")
    mask = frame[list(MASK_COLUMNS)].apply(pd.to_numeric, errors="raise").to_numpy(dtype=np.float32)
    if not np.isin(mask, [0, 1]).all():
        raise ValueError("Channel masks must be exactly 0 or 1")
    raw = frame[list(CHANNELS)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float32)
    invalid = (~np.isfinite(raw) | (raw < 0) | (raw > 100)) & mask.astype(bool)
    if invalid.any():
        raise ValueError("Active HES/TES/CES must be finite numbers in [0, 100]")
    scores = np.where(mask.astype(bool), raw / 100.0, 0.0).astype(np.float32)
    context = frame[list(CONTEXT_COLUMNS)].apply(pd.to_numeric, errors="raise").to_numpy(dtype=np.float32)
    if not np.isfinite(context).all() or (context < 0).any() or (context > 1).any():
        raise ValueError("Context features must be finite numbers in [0, 1]")
    return scores, context, mask


class FeatureEncoder:
    """Training-only vocabulary; unseen categories use a zero vector.

    A never-trained random UNK embedding must not shift category-holdout scores.
    Index zero is reserved and kept zero, so fallback depends on evidence only.
    """

    def __init__(self, categories: list[str] | None = None):
        self.categories = list(categories or [])

    def fit(self, train: pd.DataFrame) -> "FeatureEncoder":
        self.categories = sorted({str(s).strip() for s in train.product_type if str(s).strip()})
        return self

    @property
    def category_dim(self) -> int:
        return len(self.categories) + 1

    def _categories(self, frame):
        lookup = {v: i + 1 for i, v in enumerate(self.categories)}
        indices = [lookup.get(str(v).strip(), 0) for v in frame.product_type]
        category = np.eye(self.category_dim, dtype=np.float32)[indices]
        category[np.asarray(indices) == 0] = 0
        return category

    def transform_weights(self, frame: pd.DataFrame) -> tuple[np.ndarray, ...]:
        """Serving input, deliberately independent of ECS/labels/final results."""
        _, context, mask = validate_features(frame)
        return context, self._categories(frame), mask

    def transform(self, frame: pd.DataFrame) -> tuple[np.ndarray, ...]:
        """Training input including scores for the differentiable objective."""
        scores, context, mask = validate_features(frame)
        category = self._categories(frame)
        if "ecs" not in frame:
            raise ValueError("Missing ecs column (set ecs=0 explicitly when using --ecs-alpha 0)")
        ecs = pd.to_numeric(frame.ecs, errors="raise").to_numpy(dtype=np.float32)
        if not np.isfinite(ecs).all() or (ecs < 0).any() or (ecs > 100).any():
            raise ValueError("ECS must be finite in [0, 100]")
        return scores, context, category, mask, ecs / 100.0

    def to_dict(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, "categories": self.categories,
                "context_columns": list(CONTEXT_COLUMNS), "channels": list(CHANNELS),
                "unknown_category": "zero_vector"}

    @classmethod
    def from_dict(cls, data: dict) -> "FeatureEncoder":
        if data.get("schema_version") != SCHEMA_VERSION or data.get("context_columns") != list(CONTEXT_COLUMNS):
            raise ValueError("Checkpoint feature contract does not match this package")
        if data.get("channels") != list(CHANNELS):
            raise ValueError("Checkpoint channel order mismatch")
        if data.get("unknown_category") != "zero_vector":
            raise ValueError("Checkpoint unknown-category encoding mismatch")
        return cls(data["categories"])


def ontology_digest(directory: str | Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(directory).glob("*.csv")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()
