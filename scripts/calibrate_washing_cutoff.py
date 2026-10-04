#!/usr/bin/env python3
"""Washing 경계(ACCS)를 train split 만으로 정하고 val 에서 한 번만 확인한다.

입력은 `python -m fides_ml prepare` 결과(features.csv)에 dataset_v2.csv 의
split 컬럼을 url 로 붙인 파일이다. 라벨은 washing 대 나머지(suspicious+genuine)
이진으로 본다 -- dataset_v2 의 suspicious/genuine 은 제품 종류별로 거의
갈려 있어(genuine 만 있는 종류 12, suspicious 만 있는 종류 10, 섞인 종류 5)
룰베이스 ACCS 로 둘 사이 경계를 정하면 제품 종류를 가르는 선이 된다.
그래서 이 스크립트는 washing 경계만 다룬다.

룰베이스 ACCS 는 두 덩어리로 갈린다: AI 주장이 감지되지 않아 Not Evaluated
로 빠지는 바닥(약 5~6점)과, 주장이 감지돼 근거 매칭까지 간 위쪽(약 33점 이상).
MCC 최댓값은 바닥 덩어리 안쪽(노이즈)에서 나올 수 있으므로, 두 덩어리 사이의
빈 구간(gap)을 찾아 그 안의 값이면 모두 같은 결과임을 보이고, 현재 값이
gap 안에 있는지 확인한다. test split 은 읽지 않는다.

Usage:
    python scripts/calibrate_washing_cutoff.py artifacts/rescore_v2_ontology/features.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, matthews_corrcoef, roc_auc_score

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fides_config import DEFAULT_ENGINE_CONFIG  # noqa: E402

FLOOR_MAX = 10.0  # Not Evaluated 바닥 덩어리의 상한(관측값 5~6.4점보다 넉넉히)


def binary_metrics(frame: pd.DataFrame, cutoff: float, score_col: str) -> dict:
    y_true = frame["label"].eq("washing")
    y_pred = frame[score_col] < cutoff
    return {
        "n": len(frame),
        "balanced_accuracy": balanced_accuracy_score(y_true, y_pred),
        "mcc": matthews_corrcoef(y_true, y_pred),
        "washing_recall": float(y_pred[y_true].mean()),
        "non_washing_kept": float((~y_pred[~y_true]).mean()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("features", type=Path)
    parser.add_argument("--score-col", default="rule_dynamic_accs")
    args = parser.parse_args()

    frame = pd.read_csv(args.features, encoding="utf-8-sig")
    if "split" not in frame:
        raise SystemExit("features 에 split 컬럼이 없다 -- dataset_v2.csv 의 split 을 url 로 붙여서 넣을 것")
    train = frame[frame["split"] == "train"]
    val = frame[frame["split"] == "val"]
    score = train[args.score_col]
    current = DEFAULT_ENGINE_CONFIG.thresholds.suspected

    floor_top = score[score < FLOOR_MAX].max()
    upper_bottom = score[score >= FLOOR_MAX].min()
    print(f"train {len(train)}건 | washing 대 나머지 AUC "
          f"{roc_auc_score(train['label'].ne('washing'), score):.3f}")
    print(f"빈 구간(gap): {floor_top:.2f} ~ {upper_bottom:.2f} "
          f"(바닥 덩어리 최댓값 ~ 위쪽 덩어리 최솟값)")

    sweep = pd.DataFrame(
        [{"cutoff": c, **binary_metrics(train, c, args.score_col)}
         for c in np.arange(floor_top + 0.5, upper_bottom, 0.5)]
    )
    spread = sweep["mcc"].max() - sweep["mcc"].min()
    print(f"gap 안 cutoff {len(sweep)}개의 MCC 차이: {spread:.4f} (0 이면 gap 안 어디든 결과 동일)")

    inside = floor_top < current < upper_bottom
    print(f"\n현재 washing 경계 {current} -> gap 안에 {'있음' if inside else '없음'}")
    for name, part in (("train", train), ("val(1회 확인)", val)):
        m = binary_metrics(part, current, args.score_col)
        print(f"  {name}: n={m['n']} 균형정확도 {m['balanced_accuracy']:.3f} MCC {m['mcc']:.3f} "
              f"washing 검출률 {m['washing_recall']:.3f} 비워싱 유지율 {m['non_washing_kept']:.3f}")
    return 0 if inside else 1


if __name__ == "__main__":
    raise SystemExit(main())
