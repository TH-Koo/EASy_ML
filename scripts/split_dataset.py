#!/usr/bin/env python3
"""dataset_v2.csv 에 train/val/test 분할(split 컬럼)을 고정해 기록한다.

같은 group_id(같은 모델의 변형 상품 등)는 한 split 에만 들어가도록 그룹 단위로
나누고, 세 라벨(washing/suspicious/genuine) 비율이 split 마다 비슷하도록
StratifiedGroupKFold(5-fold)를 쓴다: fold 0 = test, fold 1 = val, 나머지 = train
(약 60/20/20). 채점 결과와 무관하게 라벨/그룹만 보고 나누므로, 채점 로직이
바뀌어도 분할은 그대로 유지된다.

Usage:
    python scripts/split_dataset.py dataset/dataset_v2.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

FOLD_TO_SPLIT = {0: "test", 1: "val"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--group-col", default="group_id")
    args = parser.parse_args()

    frame = pd.read_csv(args.csv, encoding="utf-8-sig")
    if "split" in frame:
        raise SystemExit("이미 split 컬럼이 있다 -- 분할을 바꾸려면 컬럼을 지우고 다시 실행")

    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=args.seed)
    frame["split"] = "train"
    for fold, (_train_idx, held_idx) in enumerate(
        splitter.split(frame, frame["label"], frame[args.group_col])
    ):
        if fold in FOLD_TO_SPLIT:
            frame.loc[frame.index[held_idx], "split"] = FOLD_TO_SPLIT[fold]

    leaked = frame.groupby(args.group_col)["split"].nunique().gt(1).sum()
    if leaked:
        raise AssertionError(f"{leaked}개 그룹이 여러 split 에 걸쳐 있다")

    frame.to_csv(args.csv, index=False, encoding="utf-8-sig")
    table = pd.crosstab(frame["split"], frame["label"], margins=True)
    ratio = pd.crosstab(frame["split"], frame["label"], normalize="index").round(3)
    print(table.to_string(), "\n")
    print(ratio.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
