"""Shared ACCS arithmetic for the engine (floats) and training (tensors).

No torch dependency, float conversion, rounding, detach, or verdict logic here.
The engine owns public scores and decisions; training reuses this exact formula.
"""
from __future__ import annotations

from math import isfinite

CHANNELS = ("hes", "tes", "ces")


def blend_coefficients(evidence_alpha=0.85, ecs_alpha=0.15):
    a, b = float(evidence_alpha), float(ecs_alpha)
    if not all(isfinite(x) and x >= 0 for x in (a, b)):
        raise ValueError("ACCS blend coefficients must be finite and nonnegative")
    if a + b == 0:
        return 0.85, 0.15  # Same fallback as the existing engine.
    return a / (a + b), b / (a + b)


def calculate_accs(scores, weights, ecs, *, evidence_alpha=0.85, ecs_alpha=0.15):
    """Inputs scores/ECS are 0..100; inactive channels have weight zero.

    Callers validate/mask inputs before this function. Values may be Python
    numbers, NumPy arrays, or torch tensors; gradients remain connected.
    """
    a, b = blend_coefficients(evidence_alpha, ecs_alpha)
    evidence_score = sum(weights[c] * scores[c] for c in CHANNELS)
    contributions = {c: a * weights[c] * scores[c] for c in CHANNELS}
    contributions["ecs"] = b * ecs
    # Match the engine's original arithmetic/rounding order.
    return {"accs": a * evidence_score + b * ecs,
            "evidence_score": evidence_score, "contributions": contributions,
            "evidence_alpha": a, "ecs_alpha": b}


def validate_weights(weights, channel_mask):
    """Reject malformed model outputs before they affect the authoritative score."""
    if set(weights) != set(CHANNELS) or set(channel_mask) != set(CHANNELS):
        raise ValueError("Weights and mask must contain exactly hes, tes, ces")
    values = {c: float(weights[c]) for c in CHANNELS}
    if any(not isfinite(v) or v < 0 for v in values.values()):
        raise ValueError("Weights must be finite and nonnegative")
    if any(values[c] != 0 for c in CHANNELS if not channel_mask[c]):
        raise ValueError("Missing channels must have exactly zero weight")
    expected = 1.0 if any(channel_mask.values()) else 0.0
    if abs(sum(values.values()) - expected) > 1e-5:
        raise ValueError(f"Weights must sum to {expected} for this mask")
    return values
