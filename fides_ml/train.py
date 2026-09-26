"""Reproducible ordinal ACCS training; validation selection; held-out evaluation."""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys

import numpy as np
import pandas as pd
import torch
from torch.nn import functional as F

from .data import LABELS, group_split, load_training_frame
from .evaluate import baseline_scores, feasibility, metrics
from .features import FeatureEncoder, write_json
from .model import ModelConfig
from .objective import CENSENN, prior_penalty, senn_penalty


@dataclass
class TrainConfig:
    epochs: int = 200
    batch_size: int = 64
    learning_rate: float = 0.001
    weight_decay: float = 0.0001
    patience: int = 30
    lambda_senn: float = 0.1
    lambda_prior: float = 0.005
    lambda_weight_stability: float = 0.01
    noise_std: float = 0.02
    balanced: bool = True
    seed: int = 42
    device: str = "cpu"
    threads: int = 2

    def __post_init__(self):
        if min(self.epochs, self.batch_size, self.patience, self.threads) < 1:
            raise ValueError("Epochs, batch size, patience and threads must be positive")
        if self.learning_rate <= 0 or self.noise_std <= 0:
            raise ValueError("Learning rate and noise std must be positive")
        if min(self.lambda_senn, self.lambda_prior, self.lambda_weight_stability, self.weight_decay) < 0:
            raise ValueError("Regularization coefficients must be nonnegative")


def choose_device(value: str) -> torch.device:
    if value == "auto":
        value = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(value)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA is not available in this PyTorch installation; use --device cpu or install a CUDA build")
    return device


def _tensors(arrays, device):
    return tuple(torch.as_tensor(a, dtype=torch.float32, device=device) for a in arrays)


def predict_arrays(model, arrays, device, batch_size=256) -> dict[str, np.ndarray]:
    values = {k: [] for k in ("accs", "weights", "accs_contributions", "ecs_contribution", "valid")}
    model.eval()
    with torch.no_grad():
        for start in range(0, len(arrays[0]), batch_size):
            batch = _tensors([a[start:start + batch_size] for a in arrays], device)
            out = model(*batch)
            for k in values:
                values[k].append(out[k].cpu().numpy())
    return {k: np.concatenate(v) for k, v in values.items()}


def train_model(data_path, output_dir, model_options=None, train_config=None) -> dict:
    cfg = train_config or TrainConfig()
    random.seed(cfg.seed)
    np.random.seed(cfg.seed)
    torch.manual_seed(cfg.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(cfg.seed)
    torch.set_num_threads(cfg.threads)
    torch.use_deterministic_algorithms(True, warn_only=True)
    device = choose_device(cfg.device)
    frame, audit = load_training_frame(data_path)
    splits = group_split(frame, cfg.seed)
    encoder = FeatureEncoder().fit(frame.iloc[splits["train"]])
    arrays = encoder.transform(frame)
    y = frame.target.to_numpy()
    model_cfg = ModelConfig(category_dim=encoder.category_dim, **(model_options or {}))
    model = CENSENN(model_cfg).to(device)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Output directory is not empty: {output}; use a new run directory")
    output.mkdir(parents=True, exist_ok=True)
    # Check degenerate inputs before spending time on training.
    audit["score_feasibility_by_split"] = {
        name: feasibility(y[idx], arrays[0][idx], arrays[3][idx], arrays[4][idx], model_cfg)
        for name, idx in splits.items()}
    audit["split_counts"] = {name: {"rows": len(idx), "groups": int(frame.iloc[idx].group_id.nunique()),
                                  "labels": frame.iloc[idx].label.value_counts().to_dict()}
                             for name, idx in splits.items()}
    audit["feature_input_sha256"] = hashlib.sha256(Path(data_path).read_bytes()).hexdigest()
    audit["group_overlap_count"] = 0
    audit["score_sources"] = sorted(frame.score_source.unique().tolist()) if "score_source" in frame else []
    train_idx, val_idx = splits["train"], splits["validation"]
    counts = np.bincount(y[train_idx], minlength=3)
    class_weights = torch.tensor(len(train_idx) / (3 * counts) if cfg.balanced else np.ones(3), dtype=torch.float32, device=device)
    parameters = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(parameters, lr=cfg.learning_rate, weight_decay=cfg.weight_decay) if parameters else None
    history, best_state, best_epoch, best_loss, stale = [], copy.deepcopy(model.state_dict()), 0, float("inf"), 0
    rng = np.random.default_rng(cfg.seed)
    max_epochs = cfg.epochs if optimizer is not None else 1
    for epoch in range(1, max_epochs + 1):
        model.train()
        totals = {k: 0.0 for k in ("loss", "ordinal_nll", "senn", "prior", "weight_stability")}
        order = rng.permutation(train_idx)
        for start in range(0, len(order), cfg.batch_size):
            ids = order[start:start + cfg.batch_size]
            h, c, cat, mask, ecs = _tensors([a[ids] for a in arrays], device)
            use_senn = model_cfg.mode == "cen_senn" and cfg.lambda_senn > 0
            if use_senn:
                h.requires_grad_(True)
                c.requires_grad_(True)
            out = model(h, c, cat, mask, ecs)
            target = torch.as_tensor(y[ids], dtype=torch.long, device=device)
            # Sum/count, not PyTorch's varying minibatch sum-of-class-weights
            # denominator; the epoch objective is independent of batching.
            nll = F.nll_loss(out["ordinal_log_probs"], target, reduction="none")
            pred_loss = (nll * class_weights[target]).mean()
            stab = senn_penalty(out, h, c) if use_senn else h.new_zeros(())
            prior = prior_penalty(out["weights"], mask, model.prior)
            weight_stability = h.new_zeros(())
            if model_cfg.mode == "cen_senn" and cfg.lambda_weight_stability > 0:
                perturbed = (c + torch.randn_like(c) * cfg.noise_std).clamp(0, 1)
                changed = model(h, perturbed, cat, mask, ecs)
                weight_stability = (out["weights"] - changed["weights"]).square().sum(-1).mean() / cfg.noise_std ** 2
            loss = pred_loss + cfg.lambda_senn * stab + cfg.lambda_prior * prior + cfg.lambda_weight_stability * weight_stability
            if not torch.isfinite(loss):
                raise RuntimeError("Non-finite loss; inspect input scores and optimization settings")
            if optimizer is not None:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(parameters, 5.0)
                optimizer.step()
            for key, value in zip(totals, (loss, pred_loss, stab, prior, weight_stability)):
                totals[key] += float(value.detach()) * len(ids)
        model.eval()
        with torch.no_grad():
            validation = model(*_tensors([a[val_idx] for a in arrays], device))
            target = torch.as_tensor(y[val_idx], dtype=torch.long, device=device)
            v_loss = float((F.nll_loss(validation["ordinal_log_probs"], target, reduction="none") * class_weights[target]).mean())
        row = {"epoch": epoch, **{k: v / len(train_idx) for k, v in totals.items()}, "validation_ordinal_nll": v_loss}
        history.append(row)
        if v_loss < best_loss - 1e-7:
            best_loss, best_epoch, stale = v_loss, epoch, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            stale += 1
        if epoch == 1 or epoch % 20 == 0:
            print(f"epoch={epoch} train_nll={row['ordinal_nll']:.5f} val_nll={v_loss:.5f} senn={row['senn']:.7f}", flush=True)
        if stale >= cfg.patience:
            break
    model.load_state_dict(best_state)
    torch.save({k: v.detach().cpu() for k, v in model.state_dict().items()}, output / "model.pt")
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent.parent, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    metadata = {"format_version": 2, "serving_contract": "weights_only",
                "model_config": model_cfg.to_dict(), "train_config": asdict(cfg),
                "encoder": encoder.to_dict(), "labels": list(LABELS), "best_epoch": best_epoch,
                "best_validation_ordinal_nll": best_loss, "base_git_commit": commit,
                "python": sys.version.split()[0], "torch": torch.__version__,
                "target": "ACCS 0..100; washing < suspicious < genuine",
                "class_weights": class_weights.cpu().tolist(),
                "score_sources": audit["score_sources"],
                "note": "Ordinal labels constrain intervals; ACCS is not a calibrated truth probability or a supervised exact-score estimate."}
    write_json(output / "metadata.json", metadata)
    report = {"best_epoch": best_epoch, "cutoffs": {"washing": model_cfg.washing_cutoff,
               "genuine": model_cfg.genuine_cutoff, "credible": model_cfg.credible_cutoff}, "splits": {}}
    for name, idx in splits.items():
        subset_arrays = [a[idx] for a in arrays]
        predicted = predict_arrays(model, subset_arrays, device)
        baseline = baseline_scores(arrays[0][idx], arrays[1][idx], arrays[3][idx], arrays[4][idx], model_cfg)
        report["splits"][name] = {"learned": metrics(y[idx], predicted["accs"], model_cfg),
                                  "baselines": {k: metrics(y[idx], score, model_cfg) for k, score in baseline.items()}}
    # Diagnostics on held-out data only; never used to select epochs or cutoffs.
    test_idx = splits["test"]
    test_arrays = [a[test_idx] for a in arrays]
    normal = predict_arrays(model, test_arrays, device)
    perturbed = [a.copy() for a in test_arrays]
    perturb_rng = np.random.default_rng(cfg.seed + 1000)
    perturbed[1] = np.clip(perturbed[1] + perturb_rng.normal(0, cfg.noise_std, perturbed[1].shape), 0, 1).astype(np.float32)
    changed = predict_arrays(model, perturbed, device)
    report["explanation_checks"] = {
        "max_accs_reconstruction_error": float(np.max(np.abs(normal["accs"] - normal["accs_contributions"].sum(-1) - normal["ecs_contribution"]))),
        "max_weight_sum_error": float(np.max(np.abs(normal["weights"].sum(-1) - 1))),
        "max_missing_channel_weight": float(np.max(np.abs(normal["weights"] * (1 - arrays[3][test_idx])))),
        "mean_weight_l1_under_context_noise": float(np.abs(normal["weights"] - changed["weights"]).sum(-1).mean()),
        "mean_accs_change_under_context_noise": float(np.abs(normal["accs"] - changed["accs"]).mean()),
        "noise_std_normalized_context": cfg.noise_std,
        "scope": "Continuous evidence-quality features, fixed product category/masks; not raw text robustness or causal importance.",
    }
    write_json(output / "metrics.json", report)
    write_json(output / "data_audit.json", audit)
    pd.DataFrame(history).to_csv(output / "training_history.csv", index=False)
    assignment = frame[["sample_id", "group_id", "label"]].copy()
    for name, idx in splits.items():
        assignment.loc[idx, "split"] = name
    assignment.to_csv(output / "split_assignments.csv", index=False, encoding="utf-8-sig")
    from .evaluate import predictions_frame
    predictions_frame(frame.iloc[test_idx].reset_index(drop=True), normal, model_cfg).to_csv(
        output / "test_predictions.csv", index=False, encoding="utf-8-sig")
    return report
