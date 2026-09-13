#!/usr/bin/env python3
"""가중치 조정분만 되돌려, 그것이 성능의 얼마를 차지하는지 분해한다.

이 프로젝트에서 "가중치·임계값"에 해당하는 변경은 둘뿐이다.

    support_combination_power   1.00 -> 0.25   (근거 결합식의 지수)
    판정 임계값                 80/60/45 -> 70/35/25

나머지는 버그 수정·수집 로직·온톨로지 데이터다. 위 둘만 원래 값으로
되돌려 채점하면, 성능이 튜닝에서 왔는지 그 외에서 왔는지 갈린다.

Usage:
    python scripts/ablation_weights.py
"""
from __future__ import annotations

import glob
import json
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fides_config import DEFAULT_ENGINE_CONFIG, VerdictThresholds  # noqa: E402
from analysis_engine import OntologyAnalysisEngine, bundle_to_evidence_records  # noqa: E402
from fides_integration import build_claim_inputs  # noqa: E402

OLD_THRESHOLDS = VerdictThresholds(credible=80.0, normal=60.0, suspected=45.0)


def normalize_label(value) -> str:
    text = str(value or "").strip().lower()
    if text in {"genuine", "normal", "정상"}:
        return "정상"
    if text in {"washing", "워싱", "ai_washing"}:
        return "워싱"
    return ""


def short_verdict(verdict: str) -> str:
    for key in ("Credible", "Normal", "Suspected", "Washing"):
        if key in str(verdict or ""):
            return key
    return "NotEval"


def load_bundles():
    labels = {}
    for name in ("benchmark_dataset_labeled.csv", "benchmark_holdout_209.csv"):
        path = REPO_ROOT / "dataset" / name
        if not path.exists():
            continue
        frame = pd.read_csv(path, encoding="utf-8-sig")
        for url, label in zip(frame["url"], frame["label"]):
            labels.setdefault(str(url).strip(), label)

    bundles = []
    for path in sorted(glob.glob(str(REPO_ROOT / "dataset" / "evidence_cache" / "*.json"))):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        label = normalize_label(labels.get(data["url"]))
        if not label:
            continue
        bundles.append((label, data["bundle_kwargs"]))
    return bundles


def score(bundles, config):
    engine = OntologyAnalysisEngine(str(REPO_ROOT / "ontology"), engine_config=config)
    rows = []
    for label, k in bundles:
        pj = k.get("product_json") or {}
        ni = k.get("norm_info") or {}
        records = bundle_to_evidence_records(
            product_json=pj, norm_info=ni, db_results=k.get("db_results"),
            jodale_result=k.get("jodale_result"), tipa_result=k.get("tipa_result"),
            koraia_result=k.get("koraia_result"), kaiac_result=k.get("kaiac_result"),
            nipa_result=k.get("nipa_result"), patent_items_df=k.get("patent_items_df"),
            cert_results=k.get("cert_results"), dart_result=k.get("dart_result"),
            target_company_name=k.get("target_company_name", ""),
            model_param=k.get("model_param", ""),
        )
        ad, ocr, extra = build_claim_inputs(pj, ni, k.get("ocr_result"))
        result = engine.analyze(records, ad_text=ad, ocr_text=ocr, extra_texts=extra)
        rows.append((label, short_verdict(result.verdict), result.accs))
    return rows


def metrics(rows):
    tn = sum(1 for l, v, _ in rows if l == "정상" and v in ("Credible", "Normal"))
    fp = sum(1 for l, v, _ in rows if l == "정상" and v not in ("Credible", "Normal"))
    tp = sum(1 for l, v, _ in rows if l == "워싱" and v not in ("Credible", "Normal"))
    fn = sum(1 for l, v, _ in rows if l == "워싱" and v in ("Credible", "Normal"))
    n = tn + fp + tp + fn
    den = ((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)) ** 0.5
    return {
        "정확도": (tp + tn) / n if n else 0.0,
        "정상인식": tn / (tn + fp) if tn + fp else 0.0,
        "워싱탐지": tp / (tp + fn) if tp + fn else 0.0,
        "MCC": (tp * tn - fp * fn) / den if den else 0.0,
        "오분류": f"{fp}+{fn}",
    }


def main() -> int:
    bundles = load_bundles()
    print(f"표본 {len(bundles)}건 "
          f"(정상 {sum(1 for l, _ in bundles if l == '정상')} / "
          f"워싱 {sum(1 for l, _ in bundles if l == '워싱')})\n")

    cases = [
        ("현재 (power 0.25 · 임계 70/35/25)", DEFAULT_ENGINE_CONFIG),
        ("임계값만 원래대로 (80/60/45)",
         replace(DEFAULT_ENGINE_CONFIG, thresholds=OLD_THRESHOLDS)),
        ("power만 원래대로 (1.0)",
         replace(DEFAULT_ENGINE_CONFIG, support_combination_power=1.0)),
        ("둘 다 원래대로 = 튜닝 이전",
         replace(DEFAULT_ENGINE_CONFIG, support_combination_power=1.0,
                 thresholds=OLD_THRESHOLDS)),
    ]

    print(f"{'설정':36s} {'정확도':>7s} {'정상인식':>8s} {'워싱탐지':>8s} {'MCC':>7s}  오분류")
    print("-" * 82)
    for name, config in cases:
        m = metrics(score(bundles, config))
        print(f"{name:36s} {m['정확도']:7.3f} {m['정상인식']:8.3f} "
              f"{m['워싱탐지']:8.3f} {m['MCC']:7.3f}  {m['오분류']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
