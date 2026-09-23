"""Serving API: return HES/TES/CES weights only. Engine owns final results."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from fides_scoring import CHANNELS, blend_coefficients, validate_weights
from .features import FeatureEncoder, channel_feature_row, read_csv
from .model import CENWeightModel, ModelConfig


class WeightPredictor:
    """Load once, then inject into OntologyAnalysisEngine/secure_analyze_bundle.

    Version-1 trained checkpoints are compatible: no learned parameter shape or
    state_dict key has changed. Version 2 explicitly records weights_only.
    """

    def __init__(self, checkpoint_dir, device="cpu"):
        path = Path(checkpoint_dir)
        metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
        if metadata.get("format_version") not in (1, 2):
            raise ValueError("Unsupported checkpoint version")
        self.metadata = metadata
        self.encoder = FeatureEncoder.from_dict(metadata["encoder"])
        self.config = ModelConfig(**metadata["model_config"])
        if self.config.category_dim != self.encoder.category_dim:
            raise ValueError("Category vocabulary and model dimensions disagree")
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)
        if self.device.type == "cuda" and not torch.cuda.is_available():
            raise ValueError("CUDA unavailable; use --device cpu")
        self.model = CENWeightModel(self.config).to(self.device)
        state = torch.load(path / "model.pt", map_location=self.device, weights_only=True)
        self.model.load_state_dict(state, strict=True)
        self.model.eval()
        digest = hashlib.sha256((path / "model.pt").read_bytes())
        digest.update(json.dumps({"encoder": metadata["encoder"], "config": metadata["model_config"]}, sort_keys=True).encode())
        self.model_version = "sha256:" + digest.hexdigest()[:16]

    def validate_engine_config(self, engine_config, dynamic_weight_config):
        """Detect training/runtime score-definition drift before accepting traffic."""
        _, ecs_alpha = blend_coefficients(dynamic_weight_config.evidence_alpha, dynamic_weight_config.ecs_alpha)
        thresholds = engine_config.thresholds
        pairs = (("ecs_alpha", self.config.ecs_alpha, ecs_alpha),
                 ("washing_cutoff", self.config.washing_cutoff, thresholds.suspected),
                 ("genuine_cutoff", self.config.genuine_cutoff, thresholds.normal),
                 ("credible_cutoff", self.config.credible_cutoff, thresholds.credible))
        different = [f"{name}: trained={a}, engine={b}" for name, a, b in pairs if abs(a - b) > 1e-8]
        if different:
            raise ValueError("Training/engine scoring settings differ; align configuration or retrain. " + "; ".join(different))

    def predict_frame(self, frame: pd.DataFrame, batch_size=256) -> pd.DataFrame:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        context, category, mask = self.encoder.transform_weights(frame)
        batches = []
        with torch.inference_mode():
            for start in range(0, len(frame), batch_size):
                arrays = [a[start:start + batch_size] for a in (context, category, mask)]
                output = self.model(*(torch.as_tensor(a, dtype=torch.float32, device=self.device) for a in arrays))
                batches.append(output["weights"].cpu().numpy())
        weights = np.concatenate(batches)
        keep = [c for c in ("sample_id", "url", "product_name", "product_type") if c in frame]
        out = frame[keep].reset_index(drop=True).copy()
        for i, c in enumerate(CHANNELS):
            out[f"weight_{c}"] = weights[:, i]
        out["status"] = np.where(mask.sum(-1) > 0, "ok", "no_usable_channels")
        out["method"] = self.config.mode
        out["model_version"] = self.model_version
        return out

    def predict_csv(self, input_path, output_path):
        result = self.predict_frame(read_csv(input_path))
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_path, index=False, encoding="utf-8-sig")
        return result

    def predict_weights(self, *, channel_scores, channel_details, product_type="", channel_mask=None) -> dict:
        row = channel_feature_row(channel_scores, channel_details, product_type=product_type,
                                  channel_mask=channel_mask)
        pred = self.predict_frame(pd.DataFrame([row])).iloc[0]
        weights = validate_weights({c: float(pred[f"weight_{c}"]) for c in CHANNELS},
                                   {c: bool(row[f"mask_{c}"]) for c in CHANNELS})
        return {"weights": weights, "method": self.config.mode,
                "model_version": self.model_version, "status": str(pred.status)}
