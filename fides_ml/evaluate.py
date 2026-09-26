"""ACCS-first evaluation, ordinal metrics, baselines and score feasibility."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, average_precision_score, balanced_accuracy_score,
                             confusion_matrix, f1_score, precision_score, recall_score)

from .data import LABELS
from .features import CHANNELS, PRIORS


def predictions_frame(frame, values, config):
    """Offline score-band diagnostics ONLY; never the engine's final verdict."""
    keep = [c for c in ("sample_id", "url", "product_name", "product_type", "label") if c in frame]
    out = frame[keep].reset_index(drop=True).copy()
    valid, accs = values["valid"], values["accs"]
    out["accs"] = np.where(valid, accs, np.nan)
    classes = score_labels(accs, config)
    out["score_band_label"] = [LABELS[i] if ok else "" for i, ok in zip(classes, valid)]
    out["status"] = np.where(valid, "ok", "no_usable_channels")
    for j, c in enumerate(CHANNELS):
        out[f"weight_{c}"] = values["weights"][:, j]
        out[f"contribution_{c}"] = values["accs_contributions"][:, j]
    out["contribution_ecs"] = values["ecs_contribution"]
    return out


def score_labels(accs, config) -> np.ndarray:
    return np.where(np.asarray(accs) < config.washing_cutoff, 0,
                    np.where(np.asarray(accs) < config.genuine_cutoff, 1, 2))


def metrics(y, accs, config) -> dict:
    y = np.asarray(y)
    accs = np.asarray(accs)
    pred = score_labels(accs, config)
    per_class = {}
    for i, label in enumerate(LABELS):
        per_class[label] = {
            "support": int((y == i).sum()),
            "precision": float(precision_score(y == i, pred == i, zero_division=0)),
            "recall": float(recall_score(y == i, pred == i, zero_division=0)),
            "f1": float(f1_score(y == i, pred == i, zero_division=0)),
            "mean_accs": float(accs[y == i].mean()) if (y == i).any() else None,
        }
    return {"n": len(y), "macro_f1": float(f1_score(y, pred, labels=[0, 1, 2], average="macro", zero_division=0)),
            "accuracy": float(accuracy_score(y, pred)), "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
            "ordinal_label_mae": float(np.abs(y - pred).mean()),
            "washing_average_precision": float(average_precision_score(y == 0, -accs)) if (y == 0).any() else None,
            "confusion_matrix_order": list(LABELS), "confusion_matrix": confusion_matrix(y, pred, labels=[0, 1, 2]).tolist(),
            "per_class": per_class, "accs_range": [float(accs.min()), float(accs.max())]}


def baseline_scores(concepts, context, mask, ecs, config) -> dict[str, np.ndarray]:
    def normalize(weights):
        a = weights * mask
        return a / np.maximum(a.sum(-1, keepdims=True), 1e-12)

    fixed = normalize(np.broadcast_to(PRIORS, mask.shape))
    # Same quality-context formula as main fides_config.py (on normalized signals).
    features = context.reshape(-1, 3, 5)
    count, diversity, directness, recency, concentration = [features[:, :, i] for i in range(5)]
    logits = np.log(PRIORS) + .80 * directness + .45 * diversity + .25 * count + .20 * recency - .30 * concentration
    dynamic = normalize(np.exp(logits - logits.max(axis=1, keepdims=True)))
    def score(w):
        return 100 * ((1 - config.ecs_alpha) * (w * concepts).sum(-1) + config.ecs_alpha * ecs)
    return {"fixed_weights_same_accs_formula": score(fixed), "rule_dynamic_same_accs_formula": score(dynamic)}


def attainable_intervals(concepts, mask, ecs, config):
    low = np.where(mask > 0, concepts, np.inf).min(-1)
    high = np.where(mask > 0, concepts, -np.inf).max(-1)
    low = 100 * ((1 - config.ecs_alpha) * low + config.ecs_alpha * ecs)
    high = 100 * ((1 - config.ecs_alpha) * high + config.ecs_alpha * ecs)
    return low, high


def feasibility(y, concepts, mask, ecs, config) -> dict:
    """A convex weighted score cannot escape its input-score range."""
    low, high = attainable_intervals(concepts, mask, ecs, config)
    possible = np.where(y == 0, low < config.washing_cutoff,
                        np.where(y == 1, (high >= config.washing_cutoff) & (low < config.genuine_cutoff),
                                 high >= config.genuine_cutoff))
    return {"unreachable_label_rows": int((~possible).sum()), "total_rows": len(y),
            "by_label": {label: int(((y == i) & ~possible).sum()) for i, label in enumerate(LABELS)},
            "note": "Necessary score-range check, not a performance bound. Dictionary constraints can further reduce attainability. Weights alone cannot fix mislabeled or inadequate concept scores."}
