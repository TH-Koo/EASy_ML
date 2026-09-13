#!/usr/bin/env python3
"""Re-score cached evidence bundles for a fixed list of model codes with the
current (review/score-logic) engine, so the output can be compared row-for-row
against a teammate's CSV that used a different branch's engine.

Usage:
    python scripts/score_by_model_codes.py --codes-file dataset/todo_urls.txt --out dataset/score_mine.csv
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from analysis_engine import OntologyAnalysisEngine, bundle_to_evidence_records
from fides_config import DEFAULT_ENGINE_CONFIG
from fides_integration import build_claim_inputs

DATA_DIR = REPO_ROOT / "dataset"

# The 47-row list the teammate shared (model code -> their reported ACCS),
# kept in original order/duplication for a 1:1 row comparison.
CODES: List[str] = [
    "SQ06FA1WDS", "T875MEE011", "망고슬래브 네모닉 AI", "Q27G4SL", "CU34G4",
    "25B36X", "279QA9200", "V27Q15C", "RK70F58M1ZG", "24E40L", "V27Q65C",
    "G880", "ALPS-CAN AOC27E40L", "27QD200M", "AG326UZD", "245G366",
    "Q27G40ZDF", "AOC27B36X", "G820", "27QD166CM", "AGP327UZD", "Q27G40E",
    "27QD166CM", "27LGQ175CM", "27QNA955", "Q27G4S", "G8800", "VS28D950ACB",
    "WD90H25BHY", "VR90F01AAH", "AR60F07D12WS", "AS356NSMA", "CC80H63E1HS",
    "F21WDSPR", "DW80H73Y1UZ", "QNED65ABA", "뉴스룸", "RS84DB5002CW",
    "VR80F01ADG", "M876GBB232", "RM70F90R2ZD", "WD90H25AHS", "75QNED65ABA",
    "M876GBB131", "QNED65ABA", "FH25WA",
]


def normalize(text: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", str(text or "").lower())


def load_cache_index() -> List[Dict]:
    entries = []
    for path in sorted(glob.glob(str(DATA_DIR / "evidence_cache" / "*.json"))):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue
        bk = data.get("bundle_kwargs") or {}
        pj = bk.get("product_json") or {}
        model_param = str(bk.get("model_param") or "")
        model_name = str(pj.get("model_name") or "")
        product_name = str(pj.get("name") or pj.get("title") or "")
        entries.append({
            "path": path,
            "mtime": Path(path).stat().st_mtime,
            "data": data,
            "model_param": model_param,
            "model_name": model_name,
            "product_name": product_name,
            "norm_keys": {normalize(model_param), normalize(model_name)},
            "identity": normalize(model_param) or normalize(model_name) or normalize(product_name),
        })
    return entries


def find_matches(code: str, entries: List[Dict]) -> List[Dict]:
    """Return every cache entry that could plausibly be this code, ranked by
    match strength. Empty list = no cache. More than one entry = ambiguous
    (must not silently guess)."""
    norm_code = normalize(code)
    if not norm_code:
        return []
    exact = [e for e in entries if norm_code in e["norm_keys"]]
    if exact:
        return exact
    substring = [
        e for e in entries
        if any(k and (norm_code in k or k in norm_code) for k in e["norm_keys"])
    ]
    if substring:
        return substring
    by_name = [e for e in entries if norm_code and norm_code in normalize(e["product_name"])]
    return by_name


def score_entry(engine: OntologyAnalysisEngine, entry: Dict):
    bk = entry["data"]["bundle_kwargs"]
    records = bundle_to_evidence_records(
        product_json=bk.get("product_json") or {},
        norm_info=bk.get("norm_info") or {},
        db_results=bk.get("db_results"),
        jodale_result=bk.get("jodale_result"),
        tipa_result=bk.get("tipa_result"),
        koraia_result=bk.get("koraia_result"),
        kaiac_result=bk.get("kaiac_result"),
        nipa_result=bk.get("nipa_result"),
        ntis_result=bk.get("ntis_result"),
        iitp_result=bk.get("iitp_result"),
        patent_items_df=bk.get("patent_items_df"),
        cert_results=bk.get("cert_results"),
        dart_result=bk.get("dart_result"),
        target_company_name=bk.get("target_company_name", ""),
        model_param=bk.get("model_param", ""),
    )
    ad_text, ocr_text, extra_texts = build_claim_inputs(
        bk.get("product_json") or {}, bk.get("norm_info") or {}, bk.get("ocr_result")
    )
    result = engine.analyze(records, ad_text=ad_text, ocr_text=ocr_text, extra_texts=extra_texts)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DATA_DIR / "score_mine_47.csv"))
    parser.add_argument("--ontology-dir", default=str(REPO_ROOT / "ontology"))
    args = parser.parse_args()

    engine = OntologyAnalysisEngine(args.ontology_dir, engine_config=DEFAULT_ENGINE_CONFIG)
    entries = load_cache_index()
    print(f"캐시 {len(entries)}건 로드. 대조 대상 코드 {len(CODES)}개.")

    rows = []
    misses = []
    ambiguous = []
    for code in CODES:
        matches = find_matches(code, entries)
        if not matches:
            misses.append(code)
            rows.append({"제품명": code, "final_accs": None, "상태": "캐시 없음", "매칭": ""})
            continue
        # Multiple cache files for the *same* product (re-crawled) are not
        # ambiguous -- collapse them and keep the most recent capture. Only
        # flag it when the candidates are genuinely different products.
        distinct_identities = {e["identity"] for e in matches if e["identity"]}
        if len(distinct_identities) > 1:
            candidates = [e["model_param"] or e["model_name"] or e["product_name"] for e in matches]
            ambiguous.append((code, candidates))
            rows.append({
                "제품명": code, "final_accs": None,
                "상태": f"모호함({len(distinct_identities)}개 서로 다른 제품 후보)",
                "매칭": " / ".join(dict.fromkeys(candidates)),
            })
            continue
        entry = max(matches, key=lambda e: e["mtime"])
        try:
            result = score_entry(engine, entry)
            rows.append({
                "제품명": code,
                "final_accs": round(result.accs, 2),
                "상태": "OK",
                "매칭": entry["model_param"] or entry["model_name"] or entry["product_name"],
            })
        except Exception as exc:
            rows.append({"제품명": code, "final_accs": None, "상태": f"채점 실패: {exc}", "매칭": ""})

    import csv
    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["제품명", "final_accs", "상태", "매칭"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n결과 저장: {args.out}")
    print(f"캐시 없음: {len(misses)}건 -> {misses}")
    print(f"모호한 매칭(여러 후보): {len(ambiguous)}건")
    for code, cands in ambiguous:
        print(f"  - {code}: {cands}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
