"""Refit and export the adopted Suspicious-only auxiliary forest.

Example from the repository root::

    python scripts/train_s_only.py --fit-all \
        --features artifacts/run_01/features.csv \
        --categories dataset/dataset_v2.csv --output artifacts/s_only

The explicit full-data refit produces a serving artifact. Historical cross-
validation results describe the previous development experiment, and this
command does not estimate accuracy on new products.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier

from fides_ml.features import CONTEXT_COLUMNS, SCHEMA_VERSION, normalize_label, ontology_digest


LABELS = ["washing", "suspicious", "genuine"]
FEATURE_COLUMNS = [
    "hes", "tes", "ces", "ecs", "mask_hes", "mask_tes", "mask_ces",
    *CONTEXT_COLUMNS,
]


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def load_training_data(features_path, categories_path):
    frame = pd.read_csv(features_path, dtype=str, encoding="utf-8-sig").fillna("")
    required = {"sample_id", "label", *FEATURE_COLUMNS}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Feature CSV is missing required columns: {sorted(missing)}")
    frame["sample_id"] = frame.sample_id.str.strip()
    if frame.empty or frame.sample_id.eq("").any() or frame.sample_id.duplicated().any():
        raise ValueError("Training sample IDs must be nonempty and unique")
    if "schema_version" in frame and not frame.schema_version.eq(SCHEMA_VERSION).all():
        raise ValueError("Training feature schema differs from the serving feature contract")
    normalized_labels = frame.label.map(normalize_label)
    if normalized_labels.isna().any():
        raise ValueError("Every training row needs a washing, suspicious, or genuine reference label")
    frame["label"] = normalized_labels
    if set(frame.label) != set(LABELS):
        raise ValueError("All three reference classes are required for this auxiliary forest")

    raw_values = []
    for column in FEATURE_COLUMNS:
        original = frame[column].str.strip()
        values = pd.to_numeric(original.replace("", np.nan), errors="coerce")
        invalid = original.ne("") & values.isna()
        if invalid.any() or np.isinf(values.to_numpy(float)).any():
            raise ValueError(f"Invalid numeric training value in {column}")
        raw_values.append(values.to_numpy(float))
    raw = np.column_stack(raw_values)
    for name in ("mask_hes", "mask_tes", "mask_ces"):
        values = raw[:, FEATURE_COLUMNS.index(name)]
        if not np.isin(values[np.isfinite(values)], (0, 1)).all():
            raise ValueError(f"{name} must contain 0, 1, or a missing value")

    urls = frame["url"].str.strip() if "url" in frame else frame.sample_id
    if urls.eq("").any() or urls.duplicated().any():
        raise ValueError("Training URLs must be nonempty and unique for the category join")
    # The only category-source columns read are the lookup key and product type.
    category_source = pd.read_csv(
        categories_path, usecols=["url", "product_type"], dtype=str, encoding="utf-8-sig",
    ).fillna("")
    category_source["url"] = category_source.url.str.strip()
    category_source = category_source.loc[category_source.url.isin(urls)].set_index("url")
    if not category_source.index.is_unique or set(category_source.index) != set(urls):
        raise ValueError("Category source must contain exactly one match for each training URL")
    categories = category_source.loc[urls, "product_type"].str.strip().to_numpy()
    invalid_categories = [str(value).lower() in {"", "masked", "[masked_category]"} for value in categories]
    if any(invalid_categories):
        raise ValueError("Use original nonmasked product types for every training product")
    return frame, raw, categories


def design_matrix(raw, categories, medians, vocabulary):
    values = np.where(np.isnan(raw), np.asarray(medians)[None, :], raw)
    category_features = np.zeros((len(categories), len(vocabulary)), dtype=float)
    positions = {name: index for index, name in enumerate(vocabulary)}
    for row, category in enumerate(categories):
        if category in positions:
            category_features[row, positions[category]] = 1.0
    return np.column_stack([values, category_features])


def export_trees(forest):
    trees = []
    for estimator in forest.estimators_:
        tree = estimator.tree_
        values = tree.value[:, 0, :].astype(float)
        totals = values.sum(axis=1, keepdims=True)
        if not np.isfinite(values).all() or (totals <= 0).any():
            raise ValueError("Forest contains an invalid node probability distribution")
        values = values / totals
        trees.append({
            "children_left": tree.children_left.tolist(),
            "children_right": tree.children_right.tolist(),
            "feature": tree.feature.tolist(),
            "threshold": tree.threshold.tolist(),
            "value": values.tolist(),
        })
    return trees


def reference_json_probabilities(artifact, rows, categories):
    """Independently check exported trees using sklearn's float32 input routing."""
    raw = np.asarray([[row[name] if row[name] is not None else np.nan
                       for name in artifact["feature_columns"]] for row in rows], dtype=float)
    inputs = design_matrix(raw, categories, artifact["feature_medians"], artifact["category_vocabulary"])
    inputs = inputs.astype(np.float32)
    result = np.zeros((len(inputs), 3), dtype=float)
    for tree in artifact["trees"]:
        left = np.asarray(tree["children_left"], dtype=int)
        right = np.asarray(tree["children_right"], dtype=int)
        feature = np.asarray(tree["feature"], dtype=int)
        threshold = np.asarray(tree["threshold"], dtype=float)
        nodes = np.zeros(len(inputs), dtype=int)
        active = left[nodes] >= 0
        while active.any():
            indices = np.flatnonzero(active)
            current = nodes[indices]
            go_left = inputs[indices, feature[current]] <= threshold[current]
            nodes[indices] = np.where(go_left, left[current], right[current])
            active = left[nodes] >= 0
        result += np.asarray(tree["value"], dtype=float)[nodes]
    return result / len(artifact["trees"])


def make_fixture(frame, raw, categories, forest, medians, vocabulary, threshold):
    full_inputs = design_matrix(raw, categories, medians, vocabulary)
    probabilities = forest.predict_proba(full_inputs)
    examples = set(range(min(8, len(frame))))
    examples.update(np.argsort(probabilities[:, 1])[-8:].tolist())
    for label in LABELS:
        examples.update(np.flatnonzero(frame.label.eq(label).to_numpy())[:3].tolist())
    examples = sorted(examples)
    rows = [{name: float(raw[index, j]) if np.isfinite(raw[index, j]) else None
             for j, name in enumerate(FEATURE_COLUMNS)} for index in examples]
    fixture_categories = [str(categories[index]) for index in examples]
    fixture_ids = frame.iloc[examples].sample_id.tolist()
    # Verify unseen-category and missing-value preprocessing, as well as real rows.
    rows.append(dict(rows[0]))
    fixture_categories.append("__UNSEEN_S_ONLY_EXPORT_PARITY_CATEGORY__")
    fixture_ids.append("fixture_unknown_category")
    rows.append(dict.fromkeys(FEATURE_COLUMNS, None))
    fixture_categories.append(str(categories[examples[0]]))
    fixture_ids.append("fixture_all_numeric_missing")
    fixture_raw = np.asarray([[row[name] if row[name] is not None else np.nan
                               for name in FEATURE_COLUMNS] for row in rows], dtype=float)
    expected = forest.predict_proba(design_matrix(fixture_raw, fixture_categories, medians, vocabulary))
    return {
        "sample_ids": fixture_ids,
        "rows": rows,
        "categories": fixture_categories,
        "probabilities": expected.tolist(),
        "suspicious_threshold_reached": (expected[:, 1] >= threshold).tolist(),
    }, probabilities


def train_and_export(features_path, categories_path, output, threshold, ontology_dir):
    features_path, categories_path = Path(features_path), Path(categories_path)
    output, ontology_dir = Path(output), Path(ontology_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose a new or empty output directory to keep model versions separate")
    if not (0.5 < threshold <= 1.0):
        raise ValueError("The adopted Suspicious-only policy requires a probability threshold above 0.5 and at most 1")
    if not ontology_dir.is_dir() or not any(ontology_dir.glob("*.csv")):
        raise ValueError("Ontology directory must contain the scoring CSV files")
    frame, raw, categories = load_training_data(features_path, categories_path)
    medians = []
    empty_columns = []
    for index, name in enumerate(FEATURE_COLUMNS):
        observed = raw[:, index][np.isfinite(raw[:, index])]
        if len(observed):
            medians.append(float(np.median(observed)))
        else:
            medians.append(0.0)
            empty_columns.append(name)
    vocabulary = sorted(set(categories))
    target = frame.label.map(dict(zip(LABELS, range(3)))).to_numpy(int)
    counts = np.bincount(target, minlength=3)
    weights = {label: float(np.sqrt(len(target) / (3 * count))) for label, count in enumerate(counts)}
    forest = RandomForestClassifier(
        n_estimators=200, max_depth=6, min_samples_leaf=5,
        class_weight=weights, n_jobs=2, random_state=42,
    )
    forest.fit(design_matrix(raw, categories, medians, vocabulary), target)
    if not np.array_equal(forest.classes_, np.arange(3)):
        raise ValueError("Unexpected probability class order")
    metadata = {
        "training_rows": len(frame),
        "labels": {name: int(counts[index]) for index, name in enumerate(LABELS)},
        "class_weights": {name: weights[index] for index, name in enumerate(LABELS)},
        "versions": {"sklearn": sklearn.__version__, "numpy": np.__version__, "python": platform.python_version()},
        "source_features_sha256": file_digest(features_path),
        "source_categories_sha256": file_digest(categories_path),
        "ontology_sha256": ontology_digest(ontology_dir),
        "feature_schema_version": SCHEMA_VERSION,
        "estimator_params": forest.get_params(),
        "trained_on": "full_data_refit",
        "historical_metrics_development_only": True,
        "historical_reference": {
            "protocol": "1152 products, original 5 model-family group folds, category supplied, S-only correction",
            "accuracy": 0.8550347222222222,
            "suspicious_correct": 10,
            "suspicious_total": 37,
            "scope": "Previous development cross-validation, before this full-data serving refit. New-product performance needs a separate evaluation.",
        },
        "numeric_empty_columns_imputed_with_zero": empty_columns,
        "category_input": "Original product_type via exact URL join, sorted vocabulary fit on refit training rows, unknown category all zero",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    artifact = {
        "format_version": 1,
        "policy": "suspicious_only",
        "labels": LABELS,
        "threshold": float(threshold),
        "feature_columns": FEATURE_COLUMNS,
        "category_vocabulary": vocabulary,
        "feature_medians": medians,
        "trees": export_trees(forest),
        "metadata": metadata,
    }
    fixture, probabilities = make_fixture(frame, raw, categories, forest, medians, vocabulary, threshold)
    fixture_observed = reference_json_probabilities(artifact, fixture["rows"], fixture["categories"])
    fixture_expected = np.asarray(fixture["probabilities"])
    fixture_difference = float(np.abs(fixture_expected - fixture_observed).max())
    rows = [{name: float(raw[index, j]) if np.isfinite(raw[index, j]) else None
             for j, name in enumerate(FEATURE_COLUMNS)} for index in range(len(frame))]
    observed = reference_json_probabilities(artifact, rows, categories)
    difference = float(np.abs(probabilities - observed).max())
    if not np.allclose(observed, probabilities, rtol=0, atol=2e-12) or fixture_difference > 2e-12:
        raise AssertionError(f"Exported tree prediction differs from sklearn: {difference}, fixture {fixture_difference}")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "model.json", artifact)
    write_json(output / "parity_fixture.json", fixture)
    reference = frame[["sample_id", "label"]].copy()
    reference["category"] = categories
    for index, label in enumerate(LABELS):
        reference[f"probability_{label}"] = probabilities[:, index]
    reference["suspicious_threshold_reached"] = probabilities[:, 1] >= threshold
    reference.to_csv(output / "sklearn_reference_predictions.csv", index=False, encoding="utf-8-sig")
    parity = {
        "training_rows_checked": len(frame),
        "fixture_rows_checked": len(fixture["rows"]),
        "export_vs_sklearn_max_absolute_error": difference,
        "fixture_max_absolute_error": fixture_difference,
        "threshold_decisions_identical": bool(np.array_equal(probabilities[:, 1] >= threshold, observed[:, 1] >= threshold)),
        "model_sha256": file_digest(output / "model.json"),
        "portable_runtime_checked": False,
        "scope": "Export numerical equivalence using refit training inputs. This report does not estimate prediction accuracy on new products.",
    }
    # Verify the separately maintained serving implementation when available.
    try:
        from fides_ml.s_only import PortableSOnlyModel
    except ImportError:
        PortableSOnlyModel = None
    if PortableSOnlyModel is not None:
        serving_model = PortableSOnlyModel(output / "model.json")
        runtime = np.asarray(serving_model.predict_rows(rows, list(categories)), dtype=float)
        runtime_fixture = np.asarray(serving_model.predict_rows(fixture["rows"], fixture["categories"]), dtype=float)
        if (runtime.shape != probabilities.shape or runtime_fixture.shape != fixture_expected.shape
                or not np.allclose(runtime, probabilities, rtol=0, atol=2e-12)
                or not np.allclose(runtime_fixture, fixture_expected, rtol=0, atol=2e-12)):
            raise AssertionError("Portable serving runtime differs from the sklearn reference")
        parity["portable_runtime_checked"] = True
        parity["runtime_max_absolute_error"] = float(np.abs(runtime - probabilities).max())
    write_json(output / "exporter_parity.json", parity)
    print(f"Refit serving forest on {len(frame)} labeled products and {len(vocabulary)} training product types.", flush=True)
    print(f"Saved {output / 'model.json'}; exported probabilities match sklearn within {difference:.3g}.", flush=True)
    print("Historical 85.50% describes the previous development CV. This full-data refit has no new-product accuracy estimate.", flush=True)
    return artifact, parity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--categories", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fit-all", action="store_true", help="Explicitly refit the serving model on all supplied labeled rows")
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--ontology-dir", type=Path, default=ROOT / "ontology")
    args = parser.parse_args()
    if not args.fit_all:
        parser.error("Pass --fit-all explicitly to create a serving refit. Evaluate development changes with the frozen grouped comparison first.")
    train_and_export(args.features, args.categories, args.output, args.threshold, args.ontology_dir)


if __name__ == "__main__":
    main()
