"""Synthetic plumbing check; these are NOT real product scores or labels."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .features import CHANNELS, CONTEXT_COLUMNS, SCHEMA_VERSION


def make_demo(path, n_groups=180, seed=7) -> dict:
    rng = np.random.default_rng(seed)
    rows = []
    # Two highly different channels; correct importance depends on continuous
    # evidence context. Multiple variants share a group to exercise leakage guards.
    for group in range(n_groups):
        label = ("washing", "suspicious", "genuine")[group % 3]
        preferred = int(rng.integers(0, 3))
        for variant in range(2):
            values = rng.uniform(5, 95, size=3)
            values[preferred] = {"washing": 7, "suspicious": 31, "genuine": 82}[label] + rng.normal(0, 1)
            row = {"schema_version": SCHEMA_VERSION, "sample_id": f"synthetic-{group}-{variant}",
                   "url": f"https://example.invalid/{group}/{variant}", "product_name": f"Demo {group} variant {variant}",
                   "product_type": f"synthetic_type_{group % 5}", "split_group": f"family-{group}",
                   "base_model_id": f"family-{group}", "label": label, "ecs": 0,
                   "score_source": "SYNTHETIC_NOT_FOR_PRODUCT_EVALUATION"}
            for col in CONTEXT_COLUMNS:
                row[col] = float(rng.uniform(.1, .3))
            for i, channel in enumerate(CHANNELS):
                row[channel] = float(values[i])
                row[f"mask_{channel}"] = 1
                row[f"ctx_{channel}_directness"] = float(.95 if i == preferred else .05)
            rows.append(row)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")
    return {"rows": len(rows), "groups": n_groups, "warning": "Synthetic execution check only"}
