"""Training-only score supervision and SENN loss; not a serving predictor."""
from __future__ import annotations

import torch
from torch.nn import functional as F

from fides_scoring import CHANNELS, calculate_accs
from .model import CENWeightModel, ModelConfig, masked_normalize


class CENSENN(CENWeightModel):
    """Differentiable training wrapper with the same state_dict as the gate.

    The score exists here to judge and improve the weights. At runtime only
    CENWeightModel is loaded; AnalysisEngine computes the final ACCS/verdict.
    """

    def forward(self, concepts, context, category, mask, ecs=None):
        output = super().forward(context, category, mask)
        weights = output["weights"]
        h = torch.where(mask.bool(), concepts, torch.zeros_like(concepts))
        if ecs is None:
            if self.config.ecs_alpha:
                raise ValueError("ECS is required when ecs_alpha > 0")
            ecs = torch.zeros_like(h[:, 0])
        scored = calculate_accs(
            {c: h[:, i] * 100 for i, c in enumerate(CHANNELS)},
            {c: weights[:, i] for i, c in enumerate(CHANNELS)}, ecs * 100,
            evidence_alpha=1 - self.config.ecs_alpha, ecs_alpha=self.config.ecs_alpha,
        )
        return {**output, "score": scored["evidence_score"] / 100,
                "contributions": weights * h,
                "accs": scored["accs"],
                "accs_contributions": torch.stack([scored["contributions"][c] for c in CHANNELS], dim=-1),
                "ecs_contribution": scored["contributions"]["ecs"],
                "ordinal_log_probs": ordinal_log_probs(scored["accs"], self.config)}


def ordinal_log_probs(accs: torch.Tensor, config: ModelConfig) -> torch.Tensor:
    """Stable interval likelihood; not the engine's full production verdict."""
    a = (config.washing_cutoff - accs) / config.temperature
    b = (config.genuine_cutoff - accs) / config.temperature
    gap = accs.new_tensor((config.washing_cutoff - config.genuine_cutoff) / config.temperature)
    middle = F.logsigmoid(b) + F.logsigmoid(-a) + torch.log(-torch.expm1(gap))
    return torch.stack((F.logsigmoid(a), middle, F.logsigmoid(-b)), dim=-1)


def senn_penalty(output: dict, concepts: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
    """Squared SENN Eq.(3) for u=[h,c]: ||grad(f)-[w,0]||².

    Include context derivatives: grad_h(f)-w alone would be identically zero.
    create_graph=True retains the second derivatives needed for optimization.
    """
    grad_h, grad_c = torch.autograd.grad(
        output["score"].sum(), (concepts, context),
        create_graph=True, retain_graph=True, allow_unused=True,
    )
    if grad_c is None:
        grad_c = torch.zeros_like(context)
    return ((grad_h - output["weights"]).square().sum(-1) + grad_c.square().sum(-1)).mean()


def prior_penalty(weights, mask, prior):
    reference = masked_normalize(prior.expand_as(weights), mask)
    return (weights * (weights.clamp_min(1e-8).log() - reference.clamp_min(1e-8).log())).sum(-1).mean()
