#!/usr/bin/env python3
"""캐시된 근거 번들 전체를 현재 엔진으로 재채점하고 결과를 엑셀로 낸다.

pipeline_main.run_full_pipeline() 이 저장한 dataset/evidence_cache/*.json 을
읽으므로 재크롤링도, 공공 API 호출도 하지 않는다. 채점 로직만 바꿔가며
같은 근거로 몇 번이든 다시 잴 수 있다는 뜻이고, KIPRIS 일일 한도에도
영향받지 않는다.

시트 구성
    제품별      제품 1건 = 1행. 점수·판정·채널·근거 구성까지 전부
    지표요약    라벨이 있는 제품에 대한 accuracy/specificity/MCC 등
    오분류      라벨과 판정이 어긋난 건만 추려 원인 추적용 열을 붙임
    출처별기여  어떤 출처가 실제로 점수에 기여했는지 집계
    채널분포    ACCS 구간별 분포 (정상/워싱)

Usage:
    python scripts/score_all_to_excel.py
    python scripts/score_all_to_excel.py --out dataset/score_all.xlsx
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# --data-dir 로 덮어쓴다. 다른 브랜치 워크트리에서 돌릴 때 필요하다.
DATA_DIR = REPO_ROOT / "dataset"

from fides_config import DEFAULT_ENGINE_CONFIG  # noqa: E402
from analysis_engine import OntologyAnalysisEngine, bundle_to_evidence_records  # noqa: E402
from fides_integration import build_claim_inputs  # noqa: E402

# 판정 문자열은 "신뢰 상품 / Normal" 처럼 한글·영문이 붙어 있다. 영문만 쓴다.
VERDICT_ORDER = ["Credible", "Normal", "Suspected", "Washing", "NotEval"]


def short_verdict(verdict: str) -> str:
    text = str(verdict or "")
    for key in ("Credible", "Normal", "Suspected", "Washing"):
        if key in text:
            return key
    return "NotEval"


def normalize_label(value) -> str:
    text = str(value or "").strip().lower()
    if text in {"genuine", "normal", "정상", "credible"}:
        return "정상"
    if text in {"washing", "워싱", "ai_washing"}:
        return "워싱"
    if text in {"suspicious", "의심", "suspected"}:
        return "의심"
    return ""


def load_labels() -> dict:
    """벤치마크 CSV들에서 url -> label 을 모은다. 여러 파일에 흩어져 있다."""
    labels = {}
    for name in ("benchmark_dataset_labeled.csv", "benchmark_holdout_209.csv"):
        path = DATA_DIR / name
        if not path.exists():
            continue
        frame = pd.read_csv(path, encoding="utf-8-sig")
        if "url" not in frame.columns or "label" not in frame.columns:
            continue
        for url, label in zip(frame["url"], frame["label"]):
            if url and str(url) != "nan":
                labels.setdefault(str(url).strip(), label)
    return labels


def load_names() -> dict:
    """라벨 CSV의 제품명. 캐시에 제품명이 비어 있는 경우를 메운다."""
    names = {}
    for name in ("benchmark_dataset_labeled.csv", "benchmark_holdout_209.csv"):
        path = DATA_DIR / name
        if not path.exists():
            continue
        frame = pd.read_csv(path, encoding="utf-8-sig")
        if "url" not in frame.columns or "product_name" not in frame.columns:
            continue
        for url, product in zip(frame["url"], frame["product_name"]):
            if url and str(url) != "nan":
                names.setdefault(str(url).strip(), str(product))
    return names


def score_one(engine, kwargs):
    product_json = kwargs.get("product_json") or {}
    norm_info = kwargs.get("norm_info") or {}
    records = bundle_to_evidence_records(
        product_json=product_json,
        norm_info=norm_info,
        db_results=kwargs.get("db_results"),
        jodale_result=kwargs.get("jodale_result"),
        tipa_result=kwargs.get("tipa_result"),
        koraia_result=kwargs.get("koraia_result"),
        kaiac_result=kwargs.get("kaiac_result"),
        nipa_result=kwargs.get("nipa_result"),
        patent_items_df=kwargs.get("patent_items_df"),
        cert_results=kwargs.get("cert_results"),
        dart_result=kwargs.get("dart_result"),
        target_company_name=kwargs.get("target_company_name", ""),
        model_param=kwargs.get("model_param", ""),
    )
    ad_text, ocr_text, extra_texts = build_claim_inputs(
        product_json, norm_info, kwargs.get("ocr_result")
    )
    result = engine.analyze(records, ad_text=ad_text, ocr_text=ocr_text, extra_texts=extra_texts)
    return result, records, product_json, norm_info


def build_row(url, label, name, result, records, product_json, norm_info):
    details = result.details or {}
    caps = result.capability_scores or []
    claimed = [c for c in caps if c.get("positive_claim")]

    by_source = details.get("evidence_by_source") or {}
    by_relation = details.get("evidence_by_relation") or {}

    # 실제로 점수에 기여한 출처 (요건 기여가 하나라도 있는 것)
    contributing = Counter()
    for cap in claimed:
        for src in cap.get("supporting_sources") or []:
            contributing[str(src)] += 1

    top = claimed[0] if claimed else {}

    return {
        "제품명": name or norm_info.get("product_name") or product_json.get("name") or "",
        "수집된 제품명": norm_info.get("product_name") or "",
        "회사": norm_info.get("company_name") or "",
        "모델": norm_info.get("model_name") or "",
        "카테고리": product_json.get("category") or "",
        "라벨": label or "미라벨",
        "판정": short_verdict(result.verdict),
        "ACCS": round(result.accs, 2),
        "HES": round(result.hes, 2),
        "TES": round(result.tes, 2),
        "CES": round(result.ces, 2),
        "ECS": round(result.ecs, 2),
        "확신도": round(result.conf, 2),
        "sufficiency": round(float(details.get("evidence_sufficiency") or 0.0), 3),
        "주장수": len(claimed),
        "근거수": int(details.get("evidence_count") or len(records)),
        "직접근거": sum(int(c.get("direct_evidence_count") or 0) for c in claimed),
        "최상위주장": top.get("capability_name_ko", ""),
        "최상위점수": round(float(top.get("final_score") or 0.0), 2),
        "필수요건충족률": round(float(top.get("required_fulfillment_ratio") or 0.0), 3),
        "기여출처": " · ".join(f"{k}({v})" for k, v in contributing.most_common()),
        "근거_판매페이지": int(by_source.get("seller_page", 0)),
        "근거_특허": int(by_source.get("kipris", 0)),
        "근거_인증RRA": int(by_source.get("rra", 0)),
        "근거_인증KC": int(by_source.get("kc", 0)),
        "근거_공시DART": int(by_source.get("dart", 0)),
        "관계_직접모델": int(by_relation.get("direct_model", 0)),
        "관계_제품군": int(by_relation.get("product_family", 0)),
        "관계_회사역량": int(by_relation.get("company_capability", 0)),
        "관계_회사일반": int(by_relation.get("company_general", 0)),
        "url": url,
    }


def metrics(frame: pd.DataFrame) -> dict:
    """판정 경로 그대로 평가한다. Normal 이상 = 정상 예측."""
    sub = frame[frame["라벨"].isin(["정상", "워싱"])]
    if sub.empty:
        return {}
    pred_normal = sub["판정"].isin(["Credible", "Normal"])
    is_normal = sub["라벨"] == "정상"
    tn = int((is_normal & pred_normal).sum())        # 정상을 정상으로
    fp = int((is_normal & ~pred_normal).sum())       # 정상을 워싱으로
    tp = int((~is_normal & ~pred_normal).sum())      # 워싱을 워싱으로
    fn = int((~is_normal & pred_normal).sum())       # 워싱을 정상으로
    n = tn + fp + tp + fn
    denom = ((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)) ** 0.5
    spec = tn / (tn + fp) if (tn + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "표본수": n,
        "정상 라벨": tn + fp,
        "워싱 라벨": tp + fn,
        "정확도": round((tp + tn) / n, 4) if n else 0.0,
        "specificity (정상을 정상으로)": round(spec, 4),
        "워싱 검출률": round(rec, 4),
        "균형정확도": round((spec + rec) / 2, 4),
        "MCC": round((tp * tn - fp * fn) / denom, 4) if denom else 0.0,
        "정상→워싱 오분류": fp,
        "워싱→정상 오분류": fn,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(REPO_ROOT / "dataset" / "score_all.xlsx"))
    parser.add_argument("--ontology-dir", default=str(REPO_ROOT / "ontology"))
    # 다른 브랜치의 엔진으로 같은 근거를 채점해 비교할 때 쓴다. 근거 캐시와
    # 라벨 CSV 는 git 이 추적하지 않으므로 워크트리에는 없다.
    parser.add_argument("--data-dir", default=str(REPO_ROOT / "dataset"),
                        help="근거 캐시와 라벨 CSV 가 있는 dataset 디렉터리")
    args = parser.parse_args()

    global DATA_DIR
    DATA_DIR = Path(args.data_dir)

    labels, names = load_labels(), load_names()
    engine = OntologyAnalysisEngine(args.ontology_dir, engine_config=DEFAULT_ENGINE_CONFIG)

    paths = sorted(glob.glob(str(DATA_DIR / "evidence_cache" / "*.json")))
    print(f"캐시된 번들 {len(paths)}건을 현재 엔진으로 재채점합니다.")
    # 다른 브랜치에는 없는 설정이 있을 수 있으므로 방어적으로 읽는다.
    print(f"  power={getattr(DEFAULT_ENGINE_CONFIG, 'support_combination_power', 'n/a')} "
          f"credible={DEFAULT_ENGINE_CONFIG.thresholds.credible} "
          f"normal={DEFAULT_ENGINE_CONFIG.thresholds.normal} "
          f"suspected={DEFAULT_ENGINE_CONFIG.thresholds.suspected}\n")

    rows, failures = [], []
    for i, path in enumerate(paths, 1):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            url = data["url"]
            result, records, product_json, norm_info = score_one(engine, data["bundle_kwargs"])
            rows.append(build_row(url, normalize_label(labels.get(url)),
                                  names.get(url, ""), result, records, product_json, norm_info))
        except Exception as exc:
            failures.append({"파일": Path(path).name, "오류": str(exc)})
        if i % 50 == 0:
            print(f"  {i}/{len(paths)} 완료")

    frame = pd.DataFrame(rows).sort_values(["라벨", "ACCS"], ascending=[True, False])
    print(f"\n채점 완료: {len(frame)}건 (실패 {len(failures)}건)\n")

    summary = metrics(frame)
    for key, value in summary.items():
        print(f"  {key:28s} {value}")

    # 오분류 — 라벨과 판정이 어긋난 것
    labeled = frame[frame["라벨"].isin(["정상", "워싱"])]
    pred_normal = labeled["판정"].isin(["Credible", "Normal"])
    wrong = labeled[((labeled["라벨"] == "정상") & ~pred_normal)
                    | ((labeled["라벨"] == "워싱") & pred_normal)]

    # 출처별 기여 집계
    source_cols = [c for c in frame.columns if c.startswith("근거_")]
    src = pd.DataFrame({
        "출처": [c.replace("근거_", "") for c in source_cols],
        "총 근거 수": [int(frame[c].sum()) for c in source_cols],
        "근거를 가진 제품 수": [int((frame[c] > 0).sum()) for c in source_cols],
    }).sort_values("총 근거 수", ascending=False)

    # ACCS 구간 분포
    bins = [-0.01, 0.01, 10, 20, 25, 35, 50, 70, 100]
    tags = ["0 (채점 안 됨)", "0~10", "10~20", "20~25", "25~35 (의심)",
            "35~50 (신뢰)", "50~70 (신뢰)", "70~100 (높은 신뢰)"]
    labeled_bins = labeled.assign(구간=pd.cut(labeled["ACCS"], bins=bins, labels=tags))
    dist = (labeled_bins.pivot_table(index="구간", columns="라벨", values="ACCS",
                                     aggfunc="count", observed=False)
            .fillna(0).astype(int).reset_index())

    verdict_tab = (labeled.pivot_table(index="라벨", columns="판정", values="ACCS",
                                       aggfunc="count", observed=False)
                   .fillna(0).astype(int).reset_index())

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="제품별", index=False)
        pd.DataFrame([{"항목": k, "값": v} for k, v in summary.items()]).to_excel(
            writer, sheet_name="지표요약", index=False)
        verdict_tab.to_excel(writer, sheet_name="지표요약", index=False, startrow=len(summary) + 3)
        wrong.to_excel(writer, sheet_name="오분류", index=False)
        src.to_excel(writer, sheet_name="출처별기여", index=False)
        dist.to_excel(writer, sheet_name="ACCS분포", index=False)
        if failures:
            pd.DataFrame(failures).to_excel(writer, sheet_name="채점실패", index=False)

        # 열 너비를 내용에 맞춘다. 기본값이면 제품명이 전부 잘려 읽을 수 없다.
        for sheet_name in writer.sheets:
            sheet = writer.sheets[sheet_name]
            for column in sheet.columns:
                letter = column[0].column_letter
                width = max((len(str(cell.value)) for cell in column if cell.value), default=8)
                sheet.column_dimensions[letter].width = min(max(width + 2, 9), 46)
            sheet.freeze_panes = "A2"

    print(f"\n엑셀 저장: {out}")
    print(f"  시트: 제품별({len(frame)}) · 지표요약 · 오분류({len(wrong)}) · "
          f"출처별기여 · ACCS분포" + (f" · 채점실패({len(failures)})" if failures else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
