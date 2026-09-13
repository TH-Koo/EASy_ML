"""Fides rule-based baseline configuration.

The constants in this module are intentionally separated from the analysis
implementation so the same thresholds are used by the engine, API, benchmark,
and UI integration code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class VerdictThresholds:
    """Single source of truth for final classification thresholds.

    Recalibrated on the labeled tuning set (162 products: 130 genuine / 32
    washing, held out from benchmark_holdout_209.csv) with
    scripts/calibrate_thresholds.py, after two engine changes on this branch:
    the RRA model-matching fix and the channel-fallback claim_alignment gate
    (see analysis_engine.py's _calculate_channel_scores). Those two changes
    moved the ACCS distribution enough that the inherited thresholds (80/60/45,
    unchanged since the common ancestor) misclassified 336 of 338 genuine
    products as washing.

    At these values: normal ACCS averages 48.7 (washing 8.5) -- the two
    classes barely overlap, so `normal` sits mid-gap rather than at a round
    number. Every credible value from 55 to 80 ties for the same MCC (0.942)
    because no genuine product in the tuning set reaches the credible band
    from below only by a hair; 67.5 is the tie's median so a slightly
    different sample wouldn't move it far. suff_credible similarly ties
    across its whole sweep range (0.0-0.45) -- genuine products that clear
    `credible` on ACCS also clear every sufficiency floor tried, so this gate
    is not yet doing real work. It stays for the same reason noted in the
    original design: nothing to catch yet is not evidence the metric is
    broken, just that the current benchmark has no example that would test it.

    Re-run scripts/calibrate_thresholds.py against a larger/updated labeled
    set before trusting these across a materially different engine change.
    """

    credible: float = 67.5
    normal: float = 35.0
    suspected: float = 21.8
    minimum_sufficiency_for_normal: float = 0.0
    minimum_sufficiency_for_credible: float = 0.25


@dataclass(frozen=True)
class RelationWeights:
    """Maximum contribution of evidence according to entity relation.

    Company-level evidence is deliberately retained because a company may reuse
    technology developed for another product. It is, however, indirect evidence
    and therefore cannot be treated as equivalent to an exact model match.
    """

    direct_model: float = 1.00
    direct_product: float = 0.90
    product_family: float = 0.75
    company_capability: float = 0.60
    company_general: float = 0.35
    unmatched: float = 0.00


@dataclass(frozen=True)
class DynamicWeightConfig:
    """Rule-based dynamic weighting used before the attention-model stage."""

    base_channel_priors: Dict[str, float] = field(
        default_factory=lambda: {"hes": 0.35, "tes": 0.40, "ces": 0.25}
    )
    directness_signal: float = 0.80
    diversity_signal: float = 0.45
    count_signal: float = 0.25
    recency_signal: float = 0.20
    concentration_penalty: float = 0.30
    evidence_alpha: float = 0.85
    ecs_alpha: float = 0.15


@dataclass(frozen=True)
class EngineConfig:
    thresholds: VerdictThresholds = field(default_factory=VerdictThresholds)
    relation_weights: RelationWeights = field(default_factory=RelationWeights)
    dynamic_weights: DynamicWeightConfig = field(default_factory=DynamicWeightConfig)

    # A single company-level source must not fully prove a required component.
    company_single_source_cap: float = 0.75
    company_multi_source_cap: float = 0.85
    fulfilled_component_threshold: float = 0.45
    strong_component_threshold: float = 0.40
    weak_component_threshold: float = 0.25

    # Seller claims can support a product-level statement, but are not an
    # independent external verification source.
    seller_page_quality_cap: float = 0.55

    # Deduplicated evidence limit used for each channel aggregate.
    max_channel_evidence: int = 6


DEFAULT_ENGINE_CONFIG = EngineConfig()
