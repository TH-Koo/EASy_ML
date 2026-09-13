#!/usr/bin/env python3
"""실험: 판매 페이지의 기능 서술을 요건 충족으로 얼마나 인정할 것인가.

배경
    인덕션 4건 같은 오분류는 전부 같은 문턱에서 죽는다.

        seller_page/direct_model   capability_relevance=0.92
                                   component_relevance =0.00  -> 탈락

    판매 페이지는 "이 제품이 AI 조리 모드를 표방한다"는 것은 확실히 말하지만
    (capability_relevance 0.92), 요건이 묻는 부품 이름("무게·온도·습도 센서")은
    어떤 마케팅 문구에도 등장하지 않는다(component_relevance 0.00).

실험 내용
    제품 자신의 판매 페이지(direct_model/direct_product)에 한해,
    capability_relevance 에 floor 계수를 곱한 값을 component_relevance 의
    하한으로 준다. floor=0.0 이 현재 동작이고, 1.0 이면 "capability 를
    말했으면 그 부품도 말한 것으로 친다"는 가장 관대한 해석이다.

    소스는 건드리지 않는다. 엔진 인스턴스의 _component_relevance 만 감싸서
    측정하고, 결과는 표로만 낸다.

Usage:
    python scripts/experiment_seller_floor.py
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

FLOORS = (0.0, 0.30, 0.40, 0.50, 0.60, 0.75, 1.00)
DIRECT = {"direct_model", "direct_product"}


def normalize_label(value) -> str:
    text = str(value or "").strip().lower()
    if text in {"genuine", "normal", "정상", "credible"}:
        return "정상"
    if text in {"washing", "워싱", "ai_washing"}:
        return "워싱"
    return ""


def short_verdict(verdict: str) -> str:
    for key in ("Credible", "Normal", "Suspected", "Washing"):
        if key in str(verdict or ""):
            return key
    return "NotEval"


def load_labels() -> dict:
    labels = {}
    for name in ("benchmark_dataset_labeled.csv", "benchmark_holdout_209.csv"):
        path = REPO_ROOT / "dataset" / name
        if not path.exists():
            continue
        frame = pd.read_csv(path, encoding="utf-8-sig")
        if {"url", "label"} - set(frame.columns):
            continue
        for url, label in zip(frame["url"], frame["label"]):
            if url and str(url) != "nan":
                labels.setdefault(str(url).strip(), label)
    return labels


def load_bundles(labels):
    bundles = []
    for path in sorted(glob.glob(str(REPO_ROOT / "dataset" / "evidence_cache" / "*.json"))):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        url = data["url"]
        label = normalize_label(labels.get(url))
        if not label:
            continue
        k = data["bundle_kwargs"]
        pj = k.get("product_json") or {}
        ni = k.get("norm_info") or {}
        # 오수집 페이지는 이제 수집 단계에서 멈추므로 실험 대상에서 제외한다.
        if not (pj.get("specs") or str(pj.get("raw_specs") or "").count(" : ") >= 3):
            continue
        bundles.append((url, label, k, pj, ni))
    return bundles


def install_floor(engine, floor: float):
    """제품 자신의 판매 페이지에 한해 component_relevance 하한을 준다."""
    original = engine._component_relevance

    def patched(*, capability_id, component_name, component_type,
                record, evidence_match_type, capability_relevance):
        value = original(
            capability_id=capability_id, component_name=component_name,
            component_type=component_type, record=record,
            evidence_match_type=evidence_match_type,
            capability_relevance=capability_relevance,
        )
        if floor > 0 and record.source_type == "seller_page" and record.relation_type in DIRECT:
            return max(value, capability_relevance * floor)
        return value

    engine._component_relevance = patched


def score_all(bundles, floor: float):
    engine = OntologyAnalysisEngine(str(REPO_ROOT / "ontology"),
                                    engine_config=DEFAULT_ENGINE_CONFIG)
    install_floor(engine, floor)
    rows = []
    for url, label, k, pj, ni in bundles:
        records = bundle_to_evidence_records(
            product_json=pj, norm_info=ni, db_results=k.get("db_results"),
            jodale_result=k.get("jodale_result"), tipa_result=k.get("tipa_result"),
            koraia_result=k.get("koraia_result"), kaiac_result=k.get("kaiac_result"),
            nipa_result=k.get("nipa_result"), patent_items_df=k.get("patent_items_df"),
            cert_results=k.get("cert_results"), dart_result=k.get("dart_result"),
            target_company_name=k.get("target_company_name", ""),
            model_param=k.get("model_param", ""),
        )
        ad, ocr, extra = build_claim_inputs(pj, ni, k.get("ocr_result"))
        result = engine.analyze(records, ad_text=ad, ocr_text=ocr, extra_texts=extra)
        rows.append({
            "url": url, "라벨": label,
            "판정": short_verdict(result.verdict),
            "ACCS": result.accs,
            "sufficiency": float((result.details or {}).get("evidence_sufficiency") or 0.0),
        })
    return pd.DataFrame(rows)


def metrics(frame: pd.DataFrame) -> dict:
    pred_normal = frame["판정"].isin(["Credible", "Normal"])
    is_normal = frame["라벨"] == "정상"
    tn = int((is_normal & pred_normal).sum())
    fp = int((is_normal & ~pred_normal).sum())
    tp = int((~is_normal & ~pred_normal).sum())
    fn = int((~is_normal & pred_normal).sum())
    n = tn + fp + tp + fn
    denom = ((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)) ** 0.5
    return {
        "n": n,
        "정확도": (tp + tn) / n if n else 0.0,
        "specificity": tn / (tn + fp) if (tn + fp) else 0.0,
        "워싱검출": tp / (tp + fn) if (tp + fn) else 0.0,
        "MCC": (tp * tn - fp * fn) / denom if denom else 0.0,
        "정상→워싱": fp,
        "워싱→정상": fn,
    }


def main() -> int:
    bundles = load_bundles(load_labels())
    n_normal = sum(1 for b in bundles if b[1] == "정상")
    print(f"실험 대상 {len(bundles)}건 (정상 {n_normal} / 워싱 {len(bundles) - n_normal})")
    print("오수집 페이지는 수집 가드가 막으므로 제외했다.\n")

    print(f"{'floor':>6s} {'정상 평균':>9s} {'워싱 평균':>9s} {'정확도':>7s} "
          f"{'specif':>7s} {'워싱검출':>8s} {'MCC':>7s}  {'오분류(정상→/워싱→)':>18s}")
    print("-" * 88)

    baseline = None
    frames = {}
    for floor in FLOORS:
        frame = score_all(bundles, floor)
        frames[floor] = frame
        m = metrics(frame)
        normal_avg = frame.loc[frame["라벨"] == "정상", "ACCS"].mean()
        washing_avg = frame.loc[frame["라벨"] == "워싱", "ACCS"].mean()
        mark = "  <- 현재" if floor == 0.0 else ""
        print(f"{floor:6.2f} {normal_avg:9.2f} {washing_avg:9.2f} {m['정확도']:7.4f} "
              f"{m['specificity']:7.4f} {m['워싱검출']:8.4f} {m['MCC']:7.4f}  "
              f"{m['정상→워싱']:8d} / {m['워싱→정상']:<8d}{mark}")
        if floor == 0.0:
            baseline = frame

    # 워싱 제품이 이 변경에 실제로 영향을 받는지 확인한다.
    print()
    top = frames[max(FLOORS)]
    merged = baseline.merge(top, on="url", suffixes=("_기준", "_최대"))
    washing = merged[merged["라벨_기준"] == "워싱"]
    moved = washing[(washing["ACCS_최대"] - washing["ACCS_기준"]).abs() > 0.005]
    print(f"floor 0.0 -> {max(FLOORS)} 에서 점수가 움직인 워싱 제품: {len(moved)} / {len(washing)}건")
    normal = merged[merged["라벨_기준"] == "정상"]
    moved_n = normal[(normal["ACCS_최대"] - normal["ACCS_기준"]).abs() > 0.005]
    print(f"                              움직인 정상 제품: {len(moved_n)} / {len(normal)}건")

    out = REPO_ROOT / "dataset" / "experiment_seller_floor.csv"
    merged.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n제품별 상세: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
