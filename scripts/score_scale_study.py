"""ACCS 표시 점수를 0~100 으로 넓히는 변환 후보 비교.

룰베이스 ACCS(rule_dynamic_accs, 1,251건)는 5~63점에 몰려 있다.
여기서는 원점수(판정에 쓰는 값)는 그대로 두고, 화면에 보여 줄 점수만
단조 변환으로 넓히는 방법들을 같은 표본에 적용해 비교한다.

    python scripts/score_scale_study.py [features.csv]
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

CSV = sys.argv[1] if len(sys.argv) > 1 else "artifacts/rescore_v2_ontology/features.csv"
THRESHOLDS = {"suspected": 21.8, "normal": 35.0, "credible": 67.5}


def linear_minmax(x, lo=5.0, hi=63.0):
    return np.clip((x - lo) / (hi - lo) * 100, 0, 100)


def add_20(x):
    return np.clip(x + 20, 0, 100)


def times_15(x):
    return np.clip(x * 1.5, 0, 100)


def piecewise(x):
    """판정 경계에 앵커를 둔 구간 선형. 경계 → 표시 점수: 21.8→30, 35→50, 50→70, 67.5→90."""
    xp = [0.0, 21.8, 35.0, 50.0, 67.5, 100.0]
    fp = [0.0, 30.0, 50.0, 70.0, 90.0, 100.0]
    return np.interp(x, xp, fp)


def piecewise_v2(x):
    """추천안. 경계 21.8→20, 35→40, 67.5→95 에 더해 몰린 45~60 구간을 55~85 로 넓힌다."""
    xp = [0.0, 6.4, 21.8, 35.0, 45.0, 52.0, 60.0, 67.5, 100.0]
    fp = [0.0, 5.0, 20.0, 40.0, 55.0, 70.0, 85.0, 95.0, 100.0]
    return np.interp(x, xp, fp)


def logistic(x, center=47.0, scale=6.0):
    """평가군 중앙(47점)을 기준으로 S 자로 펴고 0/100 에 맞춰 다시 늘린다."""
    f = lambda v: 1 / (1 + np.exp(-(v - center) / scale))
    return (f(x) - f(0.0)) / (f(100.0) - f(0.0)) * 100


def make_equalize(sample):
    """히스토그램 평활화(= 표본 누적분포 CDF 로 백분위 변환)."""
    srt = np.sort(sample)

    def eq(x):
        return np.searchsorted(srt, x, side="right") / len(srt) * 100

    return eq


def summarize(name, f, raw, labels):
    y = f(raw)
    ev = raw > 6.4  # Not-Evaluated 바닥 묶음 제외
    q = np.percentile(y[ev], [10, 25, 50, 75, 90])
    t = dict(zip(THRESHOLDS, f(np.array(list(THRESHOLDS.values())))))
    by_label = {lab: round(float(np.median(y[labels == lab])), 1) for lab in ("genuine", "suspicious", "washing")}
    return {
        "방법": name,
        "최소": round(float(y.min()), 1),
        "최대": round(float(y.max()), 1),
        "평가군 IQR": round(float(q[3] - q[1]), 1),
        "평가군 p10~p90": f"{q[0]:.0f}~{q[4]:.0f}",
        "경계(21.8/35/67.5)→": "/".join(f"{v:.0f}" for v in t.values()),
        "라벨 중앙값 g/s/w": "/".join(str(v) for v in by_label.values()),
    }


def main():
    df = pd.read_csv(CSV, encoding="utf-8-sig")
    raw = df["rule_dynamic_accs"].to_numpy(float)
    labels = df["label"].to_numpy()
    methods = {
        "원점수": lambda x: np.asarray(x, float),
        "+20": add_20,
        "x1.5": times_15,
        "선형 최소-최대(5~63→0~100)": linear_minmax,
        "구간 선형(판정 경계 앵커)": piecewise,
        "구간 선형 v2(추천)": piecewise_v2,
        "로지스틱(S자)": logistic,
        "히스토그램 평활화(백분위)": make_equalize(raw),
    }
    rows = [summarize(n, f, raw, labels) for n, f in methods.items()]
    pd.set_option("display.width", 200)
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
