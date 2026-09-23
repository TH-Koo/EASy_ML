"""Turn existing crawler caches or explicit seller-only inputs into ML rows."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

import pandas as pd

from .features import feature_row, normalize_label, ontology_digest, read_csv, score_bundle, write_json


def prepare_dataset(labels_path, output_path, *, cache_dir=None, results_path=None,
                    seller_only=False, ontology_dir="ontology", groups_path=None,
                    group_column=None) -> dict:
    from analysis_engine import OntologyAnalysisEngine

    if sum([cache_dir is not None, results_path is not None, bool(seller_only)]) != 1:
        raise ValueError("Choose exactly one of cache_dir, results_path, seller_only")
    labels = read_csv(labels_path)
    if "url" not in labels or "label" not in labels:
        raise ValueError("Label CSV requires url and label columns")
    labels["url"] = labels.url.str.strip()
    if labels.url.eq("").any() or labels.url.duplicated().any():
        raise ValueError("Label CSV URLs must be nonempty and unique")
    if groups_path:
        groups = read_csv(groups_path)
        if "url" not in groups:
            raise ValueError("Group map requires url column")
        group_fields = [c for c in ("base_model_id", "split_group") if c in groups]
        if not group_fields or groups.url.duplicated().any():
            raise ValueError("Group map requires unique URLs and base_model_id or split_group")
        # Explicit group map replaces the corresponding columns, preserving others.
        labels = labels.drop(columns=[c for c in group_fields if c in labels]).merge(
            groups[["url", *group_fields]], on="url", how="left", validate="one_to_one"
        ).fillna("")
    if group_column:
        if group_column not in labels:
            raise ValueError(f"Group column {group_column!r} not found")
        labels["split_group"] = labels[group_column].str.strip()

    sources = {}
    if cache_dir is not None:
        paths = sorted(Path(cache_dir).glob("*.json"))
        if not paths:
            raise ValueError(f"No evidence cache JSON files in {cache_dir}")
        for path in paths:
            item = json.loads(path.read_text(encoding="utf-8-sig"))
            url = str(item.get("url", "")).strip()
            if not url or "bundle_kwargs" not in item:
                raise ValueError(f"Invalid evidence cache contract: {path}")
            if url in sources:
                raise ValueError(f"Multiple caches for URL {url}; choose one snapshot")
            sources[url] = item
    if results_path is not None:
        path = Path(results_path)
        if path.suffix.lower() == ".jsonl":
            items = [json.loads(s) for s in path.read_text(encoding="utf-8-sig").splitlines() if s.strip()]
        else:
            obj = json.loads(path.read_text(encoding="utf-8-sig"))
            items = obj if isinstance(obj, list) else [obj]
        for item in items:
            url = str(item.get("url", "")).strip()
            if not url or url in sources:
                raise ValueError("Analysis result inputs need nonempty unique URL keys")
            sources[url] = item

    engine = OntologyAnalysisEngine(str(ontology_dir)) if results_path is None else None
    rows, excluded = [], []
    for _, source in labels.iterrows():
        url = source.url
        label = normalize_label(source.label)
        if label is None:
            excluded.append({"url": url, "reason": "unlabeled_or_insufficient", "label": source.label})
            continue
        if not seller_only and url not in sources:
            excluded.append({"url": url, "reason": "missing_evidence_cache_or_result", "label": label})
            continue
        if seller_only:
            # Label explanations (matched_patterns) are deliberately NEVER used.
            product = {"product_name": source.get("product_name", ""),
                       "raw_specs": source.get("specs_text", ""),
                       "ocr_text": source.get("OCR_text", source.get("ocr_text", "")), "url": url}
            result = score_bundle({"product_json": product, "norm_info": {}}, engine)
            provenance = "seller_only_no_external_evidence"
        elif cache_dir is not None:
            result = score_bundle(sources[url]["bundle_kwargs"], engine)
            provenance = "rescored_evidence_cache"
        else:
            item = sources[url]
            result = item.get("analysis_result", item)
            provenance = "analysis_result_snapshot"
        row = feature_row(result, product_type=source.get("product_type", ""), sample_id=url)
        row.update({"url": url, "product_name": source.get("product_name", ""), "label": label,
                    "base_model_id": source.get("base_model_id", ""),
                    "split_group": source.get("split_group", ""), "score_source": provenance})
        rows.append(row)
    if not rows:
        raise ValueError("No labeled rows matched evidence. Check URLs and cache path; no features were fabricated.")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(output, index=False, encoding="utf-8-sig")
    pd.DataFrame(excluded, columns=["url", "reason", "label"]).to_csv(
        output.with_suffix(".excluded.csv"), index=False, encoding="utf-8-sig")
    missing_groups = frame.base_model_id.eq("") & frame.split_group.eq("")
    if missing_groups.any():
        frame.loc[missing_groups, ["url", "product_name", "product_type", "base_model_id", "split_group"]].to_csv(
            output.with_suffix(".groups_to_review.csv"), index=False, encoding="utf-8-sig")
    report = {"input_rows": len(labels), "prepared_rows": len(frame),
              "label_counts": dict(Counter(frame.label)), "excluded_rows": len(excluded),
              "excluded_reasons": dict(Counter(x["reason"] for x in excluded)),
              "missing_group_rows": int(missing_groups.sum()),
              "group_column_override": group_column,
              "score_source": sorted(set(frame.score_source)),
              "labels_sha256": hashlib.sha256(Path(labels_path).read_bytes()).hexdigest(),
              "ontology_sha256": ontology_digest(ontology_dir) if engine else None,
              "warnings": (["Seller-only run has no independent external evidence; not a full pipeline evaluation."]
                           if seller_only else []) +
                          (["Grouping by product_type evaluates unseen product categories; not a within-category model-family split."]
                           if group_column == "product_type" else [])}
    write_json(output.with_suffix(".audit.json"), report)
    return report
