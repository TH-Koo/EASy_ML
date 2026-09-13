#!/usr/bin/env python3
"""ACCS 0.00 으로 떨어진 오분류 제품을 한 건씩 열어 원인을 분류한다.

무엇이 없어서 0점인지 — 주장 자체가 안 잡혔는지, 주장은 잡혔는데 근거가
요건을 못 채웠는지, 애초에 수집이 안 됐는지 — 를 구분한다.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fides_config import DEFAULT_ENGINE_CONFIG  # noqa: E402
from analysis_engine import OntologyAnalysisEngine, bundle_to_evidence_records  # noqa: E402
from fides_integration import build_claim_inputs  # noqa: E402


def main() -> int:
    wrong = pd.read_excel(REPO_ROOT / "dataset" / "score_all.xlsx", sheet_name="오분류")
    targets = {str(r["url"]): str(r["제품명"]) for _, r in wrong.iterrows()}

    engine = OntologyAnalysisEngine(str(REPO_ROOT / "ontology"),
                                    engine_config=DEFAULT_ENGINE_CONFIG)

    for path in sorted(glob.glob(str(REPO_ROOT / "dataset" / "evidence_cache" / "*.json"))):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        url = data["url"]
        if url not in targets:
            continue
        k = data["bundle_kwargs"]
        pj = k.get("product_json") or {}
        ni = k.get("norm_info") or {}

        records = bundle_to_evidence_records(
            product_json=pj, norm_info=ni,
            db_results=k.get("db_results"), jodale_result=k.get("jodale_result"),
            tipa_result=k.get("tipa_result"), koraia_result=k.get("koraia_result"),
            kaiac_result=k.get("kaiac_result"), nipa_result=k.get("nipa_result"),
            patent_items_df=k.get("patent_items_df"), cert_results=k.get("cert_results"),
            dart_result=k.get("dart_result"),
            target_company_name=k.get("target_company_name", ""),
            model_param=k.get("model_param", ""),
        )
        ad, ocr, extra = build_claim_inputs(pj, ni, k.get("ocr_result"))
        result = engine.analyze(records, ad_text=ad, ocr_text=ocr, extra_texts=extra)

        caps = result.capability_scores or []
        claimed = [c for c in caps if c.get("positive_claim")]
        claim_text = str((result.details or {}).get("claim_text") or "")

        print("=" * 78)
        print(f"{targets[url][:60]}   ACCS {result.accs:.2f}  판정 {result.verdict}")
        print(f"  수집 제품명 : {ni.get('product_name')!r}")
        print(f"  회사 / 모델 : {ni.get('company_name')!r} / {ni.get('model_name')!r}")
        print(f"  카테고리    : {pj.get('category')!r}")
        print(f"  근거 {len(records)}건 | 스펙 {len(pj.get('specs') or {})}항목 "
              f"| raw_specs {len(str(pj.get('raw_specs') or ''))}자 "
              f"| OCR {len(str(pj.get('ocr_text') or ''))}자")
        print(f"  판정 근거 텍스트 {len(claim_text)}자")

        # AI 라는 단어가 텍스트에 있는데도 주장이 안 잡혔는지 확인
        low = claim_text.lower()
        has_ai = "ai" in low or "인공지능" in claim_text
        print(f"  텍스트에 AI 언급: {has_ai}  |  식별된 주장 {len(claimed)}건")

        if not claimed:
            # 왜 안 잡혔나 — 점수가 0이 아닌 capability 가 있는지
            near = sorted(caps, key=lambda c: -float(c.get("base_claim_score") or 0))[:3]
            for c in near:
                print(f"     후보 {c['capability_name_ko'][:22]:<24s} "
                      f"claim={float(c.get('base_claim_score') or 0):.2f} "
                      f"strong={c.get('matched_strong_patterns')} "
                      f"weak={c.get('matched_weak_patterns')}")
            print(f"     텍스트 앞 200자: {claim_text[:200]!r}")
        else:
            for c in claimed:
                miss = c.get("missing_required_components") or []
                got = c.get("fulfilled_required_components") or []
                print(f"     주장 {c['capability_name_ko']}  최종 {float(c.get('final_score') or 0):.2f}")
                print(f"        요건 충족 {len(got)} / 미충족 {len(miss)}  -> {miss}")
                print(f"        기여 출처 {c.get('supporting_sources')}")
                print(f"        직접근거 {c.get('direct_evidence_count')} "
                      f"간접 {c.get('indirect_evidence_count')}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
