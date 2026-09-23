"""CEN weight generator. Serving returns weights, never ACCS or a verdict."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import torch
from torch import nn

from .features import CONTEXT_COLUMNS, PRIORS


@dataclass
class ModelConfig:
    category_dim: int
    context_dim: int = len(CONTEXT_COLUMNS)
    hidden_dim: int = 32
    prototypes: int = 4
    mode: str = "cen_senn"  # fixed | global | cen | cen_senn
    ecs_alpha: float = 0.15  # Existing main: 0.85 * evidence_score + 0.15 * ECS.
    washing_cutoff: float = 21.8
    genuine_cutoff: float = 35.0
    credible_cutoff: float = 67.5
    temperature: float = 5.0  # ACCS points; fixed softness of ordinal training loss.

    def __post_init__(self):
        if self.mode not in {"fixed", "global", "cen", "cen_senn"}:
            raise ValueError(f"Unknown model mode: {self.mode}")
        if min(self.category_dim, self.context_dim, self.hidden_dim, self.prototypes) < 1:
            raise ValueError("Model dimensions must be positive")
        if not 0 <= self.ecs_alpha < 1:
            raise ValueError("ecs_alpha must be in [0, 1)")
        if not 0 < self.washing_cutoff < self.genuine_cutoff <= self.credible_cutoff <= 100:
            raise ValueError("Require 0 < washing_cutoff < genuine_cutoff <= credible_cutoff <= 100")
        if self.temperature <= 0:
            raise ValueError("temperature must be positive")

    def to_dict(self) -> dict:
        return asdict(self)


def masked_normalize(values: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    weighted = values * mask
    return weighted / weighted.sum(-1, keepdim=True).clamp_min(1e-12)


class CENWeightModel(nn.Module):
    """The only learned serving module: context -> HES/TES/CES weights.

    D[k] = softmax(prototype_logits[k])
    alpha(c) = softmax(MLP(c))
    w(c,m) = normalize(mask * (alpha(c) @ D))
    SENN and ordinal score supervision live in objective.py, used only during
    training/evaluation. The gate does not read concept scores, ECS, CONF,
    labels, labeling reasons, product IDs or rule verdicts. Parameter names
    remain compatible with the original CENSENN checkpoints.
    """

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        self.register_buffer("prior", torch.tensor(PRIORS, dtype=torch.float32))
        self.gate = nn.Sequential(
            nn.Linear(config.context_dim + config.category_dim + 3, config.hidden_dim),
            nn.Tanh(), nn.Linear(config.hidden_dim, config.prototypes),
        )
        # Break prototype symmetry so gate and dictionary can both learn.
        logits = self.prior.log().repeat(config.prototypes, 1)
        logits = logits + torch.randn_like(logits) * 0.15
        self.prototype_logits = nn.Parameter(logits)
        self.global_logits = nn.Parameter(self.prior.log().clone())
        for p in self.gate.parameters():
            p.requires_grad_(config.mode in {"cen", "cen_senn"})
        self.prototype_logits.requires_grad_(config.mode in {"cen", "cen_senn"})
        self.global_logits.requires_grad_(config.mode == "global")

    def forward(self, context, category, mask) -> dict[str, torch.Tensor]:
        mode = self.config.mode
        if mode == "fixed":
            raw_weights = self.prior.expand_as(mask)
        elif mode == "global":
            raw_weights = self.global_logits.softmax(-1).expand_as(mask)
        else:
            alpha = self.gate(torch.cat((context, category, mask), dim=-1)).softmax(-1)
            raw_weights = alpha @ self.prototype_logits.softmax(-1)
        weights = masked_normalize(raw_weights, mask)
        return {"weights": weights, "valid": mask.sum(-1) > 0}
