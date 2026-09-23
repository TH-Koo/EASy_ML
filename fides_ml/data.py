"""Validated ordinal labels and leakage-aware group partitions."""
from __future__ import annotations

import hashlib
from collections import Counter

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

from .features import MASK_COLUMNS, normalize_label, read_csv, validate_features

LABELS = ("washing", "suspicious", "genuine")


def connected_groups(frame: pd.DataFrame) -> np.ndarray:
    """Union linked split_group, base_model_id, URL and exact product identities.

    Using one column in preference to another can split a base model whose
    seller variants received inconsistent split_group IDs. Connected components
    close that loophole. Product-name matching is only an extra safeguard, not a
    substitute for explicit reviewed family IDs.
    """
    parent = list(range(len(frame)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen = {}
    for i, (_, row) in enumerate(frame.iterrows()):
        if not any(str(row.get(c, "")).strip() for c in ("split_group", "base_model_id")):
            raise ValueError("Every training row needs split_group or base_model_id. Supply --groups, or explicitly use --group-column product_type for a category holdout.")
        for col in ("split_group", "base_model_id", "url", "product_name"):
            value = str(row.get(col, "")).strip().casefold()
            if not value:
                continue
            key = (col, " ".join(value.split()))
            if key in seen:
                parent[find(i)] = find(seen[key])
            else:
                seen[key] = i
    members = {}
    for i in range(len(frame)):
        members.setdefault(find(i), []).append(str(frame.iloc[i].sample_id))
    ids = {k: "group_" + hashlib.sha256("\n".join(sorted(v)).encode()).hexdigest()[:16]
           for k, v in members.items()}
    return np.array([ids[find(i)] for i in range(len(frame))])


def load_training_frame(path) -> tuple[pd.DataFrame, dict]:
    frame = read_csv(path)
    if "label" not in frame:
        raise ValueError("Training requires the reference label column")
    input_count = len(frame)
    normalized = frame.label.map(normalize_label)
    dropped_label = int(normalized.isna().sum())
    frame = frame.loc[normalized.notna()].copy()
    frame["label"] = normalized[normalized.notna()]
    validate_features(frame)
    no_evidence = frame[list(MASK_COLUMNS)].astype(float).sum(axis=1).eq(0)
    dropped_ids = frame.loc[no_evidence, "sample_id"].tolist()
    frame = frame.loc[~no_evidence].reset_index(drop=True)
    if frame.empty:
        raise ValueError("No rows have usable HES/TES/CES; learning weights is impossible")
    frame["group_id"] = connected_groups(frame)
    frame["target"] = frame.label.map({v: i for i, v in enumerate(LABELS)}).astype(int)
    if set(frame.label) != set(LABELS):
        raise ValueError(f"Ordinal training requires all three labels {LABELS}; found {sorted(set(frame.label))}")
    # Repeated independent copies of exactly the same item must not have conflicting labels.
    for col in ("url", "product_name"):
        if col in frame:
            nonempty = frame[frame[col].astype(str).str.strip().ne("")]
            if (nonempty.groupby(col).label.nunique() > 1).any():
                raise ValueError(f"Conflicting labels for the same {col}; review labels before training")
    return frame, {"input_rows": input_count, "training_eligible_rows": len(frame),
                   "unlabeled_excluded": dropped_label, "no_channel_excluded": len(dropped_ids),
                   "no_channel_sample_ids": dropped_ids, "class_counts": dict(Counter(frame.label)),
                   "groups": int(frame.group_id.nunique())}


def group_split(frame: pd.DataFrame, seed=42) -> dict[str, np.ndarray]:
    """Approximately 60/20/20 with disjoint groups and all classes per split.

    Select among deterministic candidate GROUP splits by size and label balance
    only. No model, features, validation loss or test performance is consulted.
    """
    y, groups = frame.target.to_numpy(), frame.group_id.to_numpy()
    for cls in range(len(LABELS)):
        if len(set(groups[y == cls])) < 3:
            raise ValueError(f"{LABELS[cls]} needs at least 3 distinct groups for train/validation/test")

    def holdout(indices, fraction, random_state):
        local_y, local_g = y[indices], groups[indices]
        base = np.bincount(local_y, minlength=3) / len(local_y)
        best = None
        splitter = GroupShuffleSplit(n_splits=256, test_size=fraction, random_state=random_state)
        for train_local, held_local in splitter.split(indices, local_y, local_g):
            if len(set(local_y[train_local])) != 3 or len(set(local_y[held_local])) != 3:
                continue
            # Retain two groups per class when another split is still needed.
            if fraction == 0.2 and any(len(set(local_g[train_local][local_y[train_local] == c])) < 2 for c in range(3)):
                continue
            proportion = np.bincount(local_y[held_local], minlength=3) / len(held_local)
            objective = abs(len(held_local) / len(indices) - fraction) + np.abs(proportion - base).sum()
            if best is None or objective < best[0]:
                best = (objective, indices[train_local], indices[held_local])
        if best is None:
            raise ValueError("Cannot form class-complete disjoint group splits; add/review groups, not random row splits")
        return best[1], best[2]

    trainval, test = holdout(np.arange(len(frame)), 0.2, seed)
    train, validation = holdout(trainval, 0.25, seed + 1)
    result = {"train": train, "validation": validation, "test": test}
    group_sets = [set(groups[idx]) for idx in result.values()]
    if any(group_sets[i] & group_sets[j] for i in range(3) for j in range(i)):
        raise AssertionError("Internal error: group leakage")
    return result
