#!/usr/bin/env python3
"""판정 임계값(credible/normal/suspected + sufficiency 게이트)을 튜닝셋으로 보정한다.

main(feature/add-evidence) 엔진은 review/score-logic 과 달리 support 결합식에
지수(power) 항이 없다 -- 요건-근거 매칭 자체가 다른 방식(문맥×연관성 곱, 채널
포화 보너스, fallback)이라 sweep 할 power 파라미터가 존재하지 않는다. 그래서
이 스크립트는 예전 버전과 달리 power 는 건드리지 않고, 임계값 5개
(credible, normal, suspected, minimum_sufficiency_for_normal,
minimum_sufficiency_for_credible)만 그리드 서치한다.

ACCS/sufficiency 는 임계값과 무관하게 한 번만 계산하면 되므로(임계값은
_decide_verdict 의 사후 판단에만 쓰인다), 채점은 번들당 1회만 수행하고
임계값 조합은 그 결과 위에서 순수 산술로 저렴하게 스윕한다.

Usage:
    python scripts/calibrate_thresholds.py dataset/benchmark_dataset_labeled.csv \
        --exclude-csv dataset/benchmark_holdout_209.csv
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fides_config import DEFAULT_ENGINE_CONFIG  # noqa: E402
from analysis_engine import OntologyAnalysisEngine, bundle_to_evidence_records  # noqa: E402
from fides_integration import build_claim_inputs  # noqa: E402

CREDIBLE_THRESHOLDS = (55.0, 60.0, 65.0, 70.0, 75.0, 80.0)
NORMAL_THRESHOLDS = (25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0)
SUFFICIENCY_THRESHOLDS = (0.0, 0.10, 0.20, 0.30, 0.40, 0.45)
# suspected 는 Suspected/Washing 두 상태를 가르는 값일 뿐 "정상 판정 여부"
# 이진 지표(MCC 등)에는 영향이 없어 그리드에서 뺐다 -- normal 임계값이
# 정해진 뒤 그 아래 적당한 값으로 별도 안내한다.


def normalize_label(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"genuine", "normal", "정상", "credible"}:
        return "normal"
    if text in {"washing", "워싱", "ai_washing", "suspicious", "의심", "suspected"}:
        return "washing"
    return text


def load_bundles(labels: Dict[str, str]) -> List[Tuple[str, str, dict]]:
    bundles = []
    for path in glob.glob(str(REPO_ROOT / "dataset" / "evidence_cache" / "*.json")):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        label = normalize_label(labels.get(data["url"], ""))
        if label in ("normal", "washing"):
            bundles.append((data["url"], label, data["bundle_kwargs"]))
    return bundles


def score_all(bundles, ontology_dir: str):
    """번들당 1회만 채점해 (label, accs, sufficiency, has_positive_claim) 를 얻는다."""
    engine = OntologyAnalysisEngine(ontology_dir, engine_config=DEFAULT_ENGINE_CONFIG)
    scored = []
    for _url, label, kwargs in bundles:
        product_json = kwargs.get("product_json") or {}
        norm_info = kwargs.get("norm_info") or {}
        records = bundle_to_evidence_records(
            product_json=product_json,
            norm_info=norm_info,
            db_results=kwargs.get("db_results"),
            jodale_result=kwargs.get("jodale_result"),
            nipa_result=kwargs.get("nipa_result"),
            kaiac_result=kwargs.get("kaiac_result"),
            ntis_result=kwargs.get("ntis_result"),
            iitp_result=kwargs.get("iitp_result"),
            patent_items_df=kwargs.get("patent_items_df"),
            cert_results=kwargs.get("cert_results"),
            dart_result=kwargs.get("dart_result"),
            target_company_name=kwargs.get("target_company_name", ""),
            model_param=kwargs.get("model_param", ""),
        )
        ad_text, ocr_text, extra = build_claim_inputs(product_json, norm_info, kwargs.get("ocr_result"))
        result = engine.analyze(records, ad_text=ad_text, ocr_text=ocr_text, extra_texts=extra)
        has_positive = bool(result.details.get("claim_detection", {}).get("detected"))
        scored.append((label, result.accs, float(result.details["evidence_sufficiency"]), has_positive))
    return scored


def decide_predicted_normal(
    accs: float, sufficiency: float, has_positive: bool,
    credible: float, normal: float,
    suff_normal: float, suff_credible: float,
) -> bool:
    """score_all_to_excel.py 의 관례와 동일하게, Credible/Normal 만 '정상 판정'으로 센다.

    positive_caps 가 없으면 엔진은 무조건 'Not Evaluated' 이므로(교란 로직과
    무관하게 항상 정상 판정이 아님), 여기서도 같은 규칙을 앞세운다.
    """
    if not has_positive:
        return False
    if accs >= credible and sufficiency >= suff_credible:
        return True
    if accs >= normal and sufficiency >= suff_normal:
        return True
    return False


def metrics_for(scored, credible, normal, suff_normal, suff_credible):
    tp = tn = fp = fn = 0
    for label, accs, sufficiency, has_positive in scored:
        predicted_normal = decide_predicted_normal(
            accs, sufficiency, has_positive, credible, normal, suff_normal, suff_credible
        )
        if label == "washing" and not predicted_normal:
            tp += 1
        elif label == "normal" and predicted_normal:
            tn += 1
        elif label == "normal" and not predicted_normal:
            fp += 1
        else:
            fn += 1
    total = tp + tn + fp + fn
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    denominator = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return {
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "accuracy": (tp + tn) / total if total else 0.0,
        "balanced_accuracy": (recall + specificity) / 2.0,
        "washing_recall": recall,
        "specificity": specificity,
        "mcc": (tp * tn - fp * fn) / denominator if denominator else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--label-col", default="label")
    parser.add_argument("--exclude-csv", type=Path, action="append", default=[],
                         help="이 CSV 에 있는 url 은 튜닝셋에서 제외한다 (홀드아웃 보호)")
    parser.add_argument("--ontology-dir", default=str(REPO_ROOT / "ontology"))
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    frame = pd.read_csv(args.csv, encoding="utf-8-sig")
    exclude_urls = set()
    for path in args.exclude_csv:
        exclude_urls |= set(pd.read_csv(path, encoding="utf-8-sig")["url"])
    if exclude_urls:
        before = len(frame)
        frame = frame[~frame["url"].isin(exclude_urls)]
        print(f"홀드아웃 {len(exclude_urls)}건 제외: {before} -> {len(frame)}건 튜닝셋")

    labels = frame.set_index("url")[args.label_col].to_dict()
    bundles = load_bundles(labels)
    counts = pd.Series([label for _u, label, _k in bundles]).value_counts().to_dict()
    print(f"캐시된 번들 {len(bundles)}건 {counts}\n")

    scored = score_all(bundles, args.ontology_dir)
    normal_scores = [a for label, a, _s, _p in scored if label == "normal"]
    washing_scores = [a for label, a, _s, _p in scored if label == "washing"]
    print(f"normal ACCS 평균 {sum(normal_scores)/len(normal_scores):.1f} | "
          f"washing ACCS 평균 {sum(washing_scores)/len(washing_scores):.1f}\n")

    results = []
    for credible in CREDIBLE_THRESHOLDS:
        for normal in NORMAL_THRESHOLDS:
            if normal >= credible:
                continue
            for suff_normal in SUFFICIENCY_THRESHOLDS:
                for suff_credible in SUFFICIENCY_THRESHOLDS:
                    if suff_credible < suff_normal:
                        continue
                    row = metrics_for(scored, credible, normal, suff_normal, suff_credible)
                    row.update(
                        credible=credible, normal=normal,
                        suff_normal=suff_normal, suff_credible=suff_credible,
                    )
                    results.append(row)

    table = pd.DataFrame(results).sort_values(
        ["mcc", "balanced_accuracy"], ascending=False
    )
    columns = [
        "credible", "normal", "suff_normal", "suff_credible",
        "mcc", "balanced_accuracy", "specificity", "washing_recall",
        "tp", "tn", "fp", "fn",
    ]
    print(f"=== 상위 {args.top}개 조합 (MCC 기준) ===")
    print(table[columns].head(args.top).to_string(index=False))

    best = table.iloc[0]
    print(
        f"\n최적: credible={best.credible}, normal={best.normal}, "
        f"suff_normal={best.suff_normal}, suff_credible={best.suff_credible}"
        f"  ->  MCC {best.mcc:.3f}, 균형정확도 {best.balanced_accuracy:.3f}, "
        f"specificity {best.specificity:.3f}, washing 검출률 {best.washing_recall:.3f}"
    )

    # MCC 가 동률인 구간(plateau)이 있으면 그 중앙값을 보여줘 한쪽 끝에
    # 걸리지 않게 한다 (예전 power 보정 때와 같은 관례).
    top_mcc = table["mcc"].max()
    plateau = table[table["mcc"] >= top_mcc - 1e-9]
    print(f"\nMCC 동률 {len(plateau)}개 조합의 각 파라미터 중앙값:")
    for col in ["credible", "normal", "suff_normal", "suff_credible"]:
        print(f"  {col}: {plateau[col].median()}")

    # suspected 는 이진 지표에 영향이 없으므로, normal 임계값이 정해진 뒤
    # washing 라벨 평균 ACCS 와 normal 임계값 사이 지점을 안내만 한다.
    chosen_normal = float(plateau["normal"].median())
    washing_mean = sum(washing_scores) / len(washing_scores) if washing_scores else 0.0
    suggested_suspected = round((washing_mean + chosen_normal) / 2, 1)
    print(
        f"\nsuspected 안내값 (참고용, 지표엔 영향 없음): {suggested_suspected} "
        f"(washing 평균 {washing_mean:.1f} 과 normal={chosen_normal} 사이 중간)"
    )

    if args.json_out:
        args.json_out.write_text(
            table[columns].head(50).to_json(orient="records", force_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
