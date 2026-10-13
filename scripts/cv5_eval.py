"""5-fold stratified GROUP cross-validation for the CEN weight model.

Every row is tested exactly once (out-of-fold), so all Suspicious samples are
evaluated instead of the ~8 in a single 60/20/20 test split. Unmasked and
category-masked variants use identical folds, so they differ only in whether
the model sees product_type.

    python -m scripts.cv5_eval --data artifacts/cv5/features.csv --output artifacts/cv5/run
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold

from fides_ml.data import LABELS, load_training_frame
from fides_ml.evaluate import baseline_scores, metrics, score_labels
from fides_ml.features import FeatureEncoder
from fides_ml.model import ModelConfig
from fides_ml.train import TrainConfig, train_model

MASKED_CATEGORY = "[MASKED_CATEGORY]"


def make_folds(frame, n_splits, seed):
    """Outer test folds, then one inner group fold of the rest as validation (~60/20/20)."""
    y, groups = frame.target.to_numpy(), frame.group_id.to_numpy()
    outer = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    folds = []
    for k, (trainval, test) in enumerate(outer.split(np.zeros(len(y)), y, groups)):
        inner = StratifiedGroupKFold(n_splits=n_splits - 1, shuffle=True, random_state=seed + k + 1)
        train_local, val_local = next(inner.split(np.zeros(len(trainval)), y[trainval], groups[trainval]))
        folds.append({"train": trainval[train_local], "validation": trainval[val_local], "test": test})
    return folds


def label_metrics(y, pred) -> dict:
    labels = list(range(len(LABELS)))
    f1 = f1_score(y, pred, labels=labels, average=None, zero_division=0)
    return {"macro_f1": float(f1.mean()), "accuracy": float((y == pred).mean()),
            "per_class_f1": {LABELS[i]: float(f1[i]) for i in labels},
            "confusion_matrix_order": list(LABELS),
            "confusion_matrix": confusion_matrix(y, pred, labels=labels).tolist()}


def category_majority(frame, train_idx, eval_idx) -> np.ndarray:
    """Predict each row's label from its category's majority label in train only."""
    train = frame.iloc[train_idx]
    majority = train.groupby("product_type").target.agg(lambda s: s.value_counts().idxmax())
    overall = int(train.target.value_counts().idxmax())
    return frame.iloc[eval_idx].product_type.map(majority).fillna(overall).astype(int).to_numpy()


def summarize(per_fold: list[dict]) -> dict:
    keys = ["macro_f1", "accuracy", "balanced_accuracy", "washing_average_precision"]
    out = {}
    for k in keys + [f"f1_{c}" for c in LABELS]:
        values = [f[k] for f in per_fold if k in f]
        if values:
            out[k] = {"mean": float(np.mean(values)), "std": float(np.std(values, ddof=1)), "folds": values}
    return out


def flat(m: dict) -> dict:
    row = {k: m[k] for k in ("macro_f1", "accuracy", "balanced_accuracy", "washing_average_precision") if k in m}
    per_class = m.get("per_class") or {}
    for c in LABELS:
        if c in per_class:
            row[f"f1_{c}"] = per_class[c]["f1"]
        elif "per_class_f1" in m:
            row[f"f1_{c}"] = m["per_class_f1"][c]
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True, help="Feature CSV from `python -m fides_ml prepare`")
    p.add_argument("--output", required=True)
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--epochs", type=int, default=200)
    p.add_argument("--threads", type=int, default=2)
    args = p.parse_args()

    output = Path(args.output)
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"Output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    source = pd.read_csv(args.data)
    masked_path = output / "features_masked.csv"
    source.assign(product_type=MASKED_CATEGORY).to_csv(masked_path, index=False, encoding="utf-8-sig")
    variants = {"unmasked": Path(args.data), "masked": masked_path}

    frame, _ = load_training_frame(args.data)
    folds = make_folds(frame, args.folds, args.seed)
    sample_ids = frame.sample_id.to_numpy()
    fold_ids = [{k: set(sample_ids[v]) for k, v in f.items()} for f in folds]
    split_log = frame[["sample_id", "group_id", "product_type", "label"]].copy()
    for k, f in enumerate(folds):
        split_log.loc[f["test"], "test_fold"] = k
    split_log.to_csv(output / "fold_assignments.csv", index=False, encoding="utf-8-sig")

    cfg = ModelConfig(category_dim=1)
    y = frame.target.to_numpy()
    # Non-learned baselines do not depend on folds or category input.
    arrays = FeatureEncoder().fit(frame).transform(frame)
    rule = baseline_scores(arrays[0], arrays[1], arrays[3], arrays[4], cfg)

    results = {"folds": args.folds, "seed": args.seed, "rows": len(frame),
               "class_counts": frame.label.value_counts().to_dict(), "fold_sizes": [], "variants": {}}
    oof = frame[["sample_id", "product_type", "product_name", "label"]].copy()
    for k, f in enumerate(folds):
        results["fold_sizes"].append({s: frame.iloc[idx].label.value_counts().to_dict() for s, idx in f.items()})

    for name, path in variants.items():
        per_fold, oof_accs = [], np.full(len(frame), np.nan)
        for k in range(args.folds):
            ids = fold_ids[k]

            def split_fn(fr, ids=ids):
                sid = fr.sample_id.to_numpy()
                return {s: np.flatnonzero(np.isin(sid, list(v))) for s, v in ids.items()}

            print(f"== {name} fold {k + 1}/{args.folds}", flush=True)
            report = train_model(path, output / name / f"fold{k}", None,
                                 TrainConfig(epochs=args.epochs, seed=args.seed, threads=args.threads), split_fn)
            per_fold.append({**flat(report["splits"]["test"]["learned"]), "best_epoch": report["best_epoch"]})
            pred = pd.read_csv(output / name / f"fold{k}" / "test_predictions.csv")
            oof_accs[np.isin(sample_ids, pred.sample_id)] = pred.set_index("sample_id").loc[
                sample_ids[np.isin(sample_ids, pred.sample_id)], "accs"].to_numpy()
        oof[f"accs_{name}"] = oof_accs
        oof[f"pred_{name}"] = [LABELS[i] for i in score_labels(oof_accs, cfg)]
        results["variants"][name] = {"per_fold": per_fold, "summary": summarize(per_fold),
                                     "pooled_oof": metrics(y, oof_accs, cfg)}

    # Baselines on the same folds.
    for name, score in rule.items():
        per_fold = [flat(metrics(y[f["test"]], score[f["test"]], cfg)) for f in folds]
        results["variants"][name] = {"per_fold": per_fold, "summary": summarize(per_fold),
                                     "pooled_oof": metrics(y, score, cfg)}
    cat_pred = np.zeros(len(frame), dtype=int)
    per_fold = []
    for f in folds:
        cat_pred[f["test"]] = category_majority(frame, f["train"], f["test"])
        per_fold.append(flat(label_metrics(y[f["test"]], cat_pred[f["test"]])))
    oof["pred_category_majority"] = [LABELS[i] for i in cat_pred]
    results["variants"]["category_majority"] = {"per_fold": per_fold, "summary": summarize(per_fold),
                                                "pooled_oof": label_metrics(y, cat_pred)}

    # Extra views on pooled out-of-fold predictions.
    mixed = frame.groupby("product_type").label.nunique()
    mixed_types = sorted(mixed[mixed > 1].index)
    in_mixed = frame.product_type.isin(mixed_types).to_numpy()
    blackbox = (frame.product_type == "블랙박스").to_numpy()
    views = {}
    for name in ("unmasked", "masked", "fixed_weights_same_accs_formula", "category_majority"):
        pred = (cat_pred if name == "category_majority" else
                score_labels(oof[f"accs_{name}"] if name in variants else rule[name], cfg))
        washing_true, washing_pred = (y == 0), (pred == 0)
        views[name] = {
            "mixed_label_categories": label_metrics(y[in_mixed], pred[in_mixed]),
            "without_blackbox": label_metrics(y[~blackbox], pred[~blackbox]),
            "binary_washing_vs_rest_f1": float(f1_score(washing_true, washing_pred)),
            "suspicious_hits_by_category": frame[(y == 1) & (pred == 1)].product_type.value_counts().to_dict(),
            "suspicious_total_by_category": frame[y == 1].product_type.value_counts().to_dict(),
        }
    results["views"] = views
    results["mixed_label_categories"] = mixed_types

    oof.to_csv(output / "oof_predictions.csv", index=False, encoding="utf-8-sig")
    (output / "cv_summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, v in results["variants"].items():
        s = v["summary"]
        print(f"{name:34s} macroF1 {s['macro_f1']['mean']:.4f}±{s['macro_f1']['std']:.4f}  "
              f"suspF1 {s['f1_suspicious']['mean']:.4f}±{s['f1_suspicious']['std']:.4f}  "
              f"pooled macroF1 {v['pooled_oof']['macro_f1']:.4f}")


if __name__ == "__main__":
    main()
