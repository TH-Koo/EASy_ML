#!/usr/bin/env python3
"""Sweep EngineConfig.support_combination_power against cached evidence bundles
and report accuracy/specificity/MCC at each value, using real product labels.

Evidence bundles are cached automatically by pipeline_main.run_full_pipeline()
(see _save_evidence_bundle_cache) under dataset/evidence_cache/*.json, so this
script re-scores real, already-collected evidence without re-crawling or
re-calling any paid API.

Usage:
    python scripts/sweep_support_power.py dataset/benchmark_sample_27.csv \
        --label-col label --threshold 60

The CSV only needs `url` and a label column; only rows whose URL has a cached
evidence bundle are used.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fides_config import DEFAULT_ENGINE_CONFIG  # noqa: E402
from analysis_engine import OntologyAnalysisEngine, bundle_to_evidence_records  # noqa: E402
from fides_integration import build_claim_inputs  # noqa: E402

DEFAULT_POWERS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.33, 0.25, 0.167)


def normalize_label(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"genuine", "normal", "정상", "credible"}:
        return "normal"
    if text in {"washing", "워싱", "ai_washing", "suspicious", "의심", "suspected"}:
        return "washing"
    return text


def load_cached_bundles(labels: dict[str, str]) -> list[tuple[str, str, dict]]:
    bundles = []
    for path in glob.glob(str(REPO_ROOT / "dataset" / "evidence_cache" / "*.json")):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        url = data["url"]
        label = normalize_label(labels.get(url, ""))
        if label not in ("normal", "washing"):
            continue
        bundles.append((url, label, data["bundle_kwargs"]))
    return bundles


def score_with_power(bundles: list[tuple[str, str, dict]], power: float, ontology_dir: str):
    cfg = replace(DEFAULT_ENGINE_CONFIG, support_combination_power=power)
    engine = OntologyAnalysisEngine(ontology_dir, engine_config=cfg)
    results = []
    for url, label, kwargs in bundles:
        product_json = kwargs.get("product_json") or {}
        norm_info = kwargs.get("norm_info") or {}
        evidence_records = bundle_to_evidence_records(
            product_json=product_json,
            norm_info=norm_info,
            db_results=kwargs.get("db_results"),
            jodale_result=kwargs.get("jodale_result"),
            tipa_result=kwargs.get("tipa_result"),
            koraia_result=kwargs.get("koraia_result"),
            kaiac_result=kwargs.get("kaiac_result"),
            nipa_result=kwargs.get("nipa_result"),
            patent_items_df=kwargs.get("patent_items_df"),
            cert_results=kwargs.get("cert_results"),
            dart_result=kwargs.get("dart_result"),
            target_company_name=kwargs.get("target_company_name", ""),
            model_param=kwargs.get("model_param", ""),
        )
        ad_text, ocr_text, extra_texts = build_claim_inputs(product_json, norm_info, kwargs.get("ocr_result"))
        result = engine.analyze(evidence_records, ad_text=ad_text, ocr_text=ocr_text, extra_texts=extra_texts)
        results.append((url, label, result.accs))
    return results


def metrics_at_threshold(results, threshold: float):
    tp = tn = fp = fn = 0
    for _url, label, accs in results:
        pred = "normal" if accs >= threshold else "washing"
        if label == "washing" and pred == "washing":
            tp += 1
        elif label == "normal" and pred == "normal":
            tn += 1
        elif label == "normal" and pred == "washing":
            fp += 1
        elif label == "washing" and pred == "normal":
            fn += 1
    n = tp + tn + fp + fn
    accuracy = (tp + tn) / n if n else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    washing_recall = tp / (tp + fn) if (tp + fn) else 0.0
    denom = ((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)) ** 0.5
    mcc = (tp * tn - fp * fn) / denom if denom else 0.0
    return dict(n=n, tp=tp, tn=tn, fp=fp, fn=fn, accuracy=accuracy,
                specificity=specificity, washing_recall=washing_recall, mcc=mcc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--label-col", default="label")
    parser.add_argument("--threshold", type=float, default=60.0)
    parser.add_argument("--ontology-dir", default=str(REPO_ROOT / "ontology"))
    parser.add_argument("--powers", type=float, nargs="+", default=list(DEFAULT_POWERS))
    args = parser.parse_args()

    frame = pd.read_csv(args.csv, encoding="utf-8-sig")
    labels = frame.set_index("url")[args.label_col].to_dict()
    bundles = load_cached_bundles(labels)
    print(f"캐시된 번들 {len(bundles)}건 (normal/washing만)\n")

    print(f"{'power':>8s} {'normal avg':>11s} {'washing avg':>12s} {'acc':>6s} {'specif':>7s} {'wash_recall':>11s} {'MCC':>6s}")
    for power in args.powers:
        results = score_with_power(bundles, power, args.ontology_dir)
        normal_scores = [a for _, l, a in results if l == "normal"]
        washing_scores = [a for _, l, a in results if l == "washing"]
        m = metrics_at_threshold(results, args.threshold)
        n_avg = sum(normal_scores) / len(normal_scores) if normal_scores else float("nan")
        w_avg = sum(washing_scores) / len(washing_scores) if washing_scores else float("nan")
        print(f"{power:8.3f} {n_avg:11.1f} {w_avg:12.1f} {m['accuracy']:6.2f} {m['specificity']:7.2f} "
              f"{m['washing_recall']:11.2f} {m['mcc']:6.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
