"""
label_by_ontology.py — 온톨로지 패턴 매칭 기반 자동 라벨링

입력: dataset/benchmark_dataset.csv  (specs_text 있음, label 비어있음)
출력: dataset/benchmark_dataset_labeled.csv  (label, certainty, matched_patterns 채워짐)

실행: python label_by_ontology.py
"""
import csv
import re
from pathlib import Path

# =====================================================================
# 경로
# =====================================================================
INPUT_CSV   = "dataset/benchmark_dataset_last.csv"
OUTPUT_CSV  = "dataset/benchmark_dataset_labeled.csv"
ONTOLOGY_DIR = Path("ontology")

# =====================================================================
# product_type → capability 매핑
# =====================================================================
PRODUCT_CAPABILITY_MAP: dict[str, list[str]] = {
    "노트북":    ["CAP_FACE_RECOGNITION", "CAP_ENERGY_OPTIMIZATION", "CAP_SPEECH_RECOGNITION"],
    "게이밍 노트북": ["CAP_FACE_RECOGNITION", "CAP_ENERGY_OPTIMIZATION"],
    "올인원PC":  ["CAP_FACE_RECOGNITION", "CAP_ENERGY_OPTIMIZATION", "CAP_SPEECH_RECOGNITION"],
    "태블릿":    ["CAP_FACE_RECOGNITION", "CAP_SPEECH_RECOGNITION", "CAP_RECOMMENDATION"],
    "스마트폰":  ["CAP_FACE_RECOGNITION", "CAP_SPEECH_RECOGNITION",
                  "CAP_SPEAKER_RECOGNITION", "CAP_RECOMMENDATION"],
    "세탁기":    ["CAP_AI_WASH_COURSE", "CAP_LAUNDRY_DETECTION",
                  "CAP_ENERGY_OPTIMIZATION", "CAP_SMART_HOME_CONTROL"],
    "건조기":    ["CAP_DRY_COURSE", "CAP_ENERGY_OPTIMIZATION", "CAP_SMART_HOME_CONTROL"],
    "냉장고":    ["CAP_SMART_HOME_CONTROL", "CAP_ENERGY_OPTIMIZATION"],
    "에어컨":    ["CAP_SMART_HOME_CONTROL", "CAP_ENERGY_OPTIMIZATION", "CAP_DRY_COURSE"],
    "식기세척기":["CAP_DISHWASH_COURSE", "CAP_ENERGY_OPTIMIZATION"],
    "전자레인지":["CAP_COOKING_MODE"],
    "공기청정기":["CAP_AIR_QUALITY_DETECTION", "CAP_SMART_HOME_CONTROL"],
    "청소기":    ["CAP_DUST_DETECTION", "CAP_PATH_PLANNING_AVOIDANCE"],
    "로봇청소기":["CAP_PATH_PLANNING_AVOIDANCE", "CAP_ANOMALY_DETECTION"],
    "TV":        ["CAP_RECOMMENDATION", "CAP_SMART_HOME_CONTROL", "CAP_SPEECH_RECOGNITION"],
    "모니터":    ["CAP_DISPLAY_OPTIMIZATION", "CAP_PERSON_DETECTION"],
    "웹캠":      ["CAP_OBJECT_DETECTION", "CAP_PERSON_DETECTION", "CAP_FACE_DETECTION", "CAP_FACE_RECOGNITION"],
    "키보드":    ["CAP_AI_TYPING_ASSIST"],
    "프린터":    ["CAP_ENERGY_OPTIMIZATION"],
}

# =====================================================================
# 온톨로지 로딩
# =====================================================================
def load_evidence_patterns() -> dict[str, dict[str, list[str]]]:
    """capability_id → {strong: [...], weak: [...]}"""
    patterns: dict[str, dict[str, list[str]]] = {}
    with open(ONTOLOGY_DIR / "evidence_pattern_master.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row is None or all(v is None or v.strip() == "" for v in row.values()):
                continue
            # BOM 잔여물 방어: 첫 번째 키가 ﻿ 포함될 경우 정규화
            row = {k.lstrip("﻿"): v for k, v in row.items() if k is not None}
            cap = row["capability_id"]
            strength = row["evidence_strength"]
            pattern = row["pattern_text_ko"].strip()
            if len(pattern) < 2:          # 1글자 패턴 오매칭 방지
                continue
            patterns.setdefault(cap, {"strong": [], "weak": []})
            if strength in ("strong", "weak"):
                patterns[cap][strength].append(pattern)
    return patterns


def load_negative_patterns() -> list[dict]:
    """[{pattern, applies_to, penalty, severity}, ...]"""
    negatives = []
    with open(ONTOLOGY_DIR / "negative_pattern_master.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            negatives.append({
                "pattern":    row["pattern_text_ko"].strip(),
                "applies_to": row["applies_to_capability_id"].strip(),
                "penalty":    float(row["penalty_weight"]),
                "severity":   row["severity"],
            })
    return negatives


# =====================================================================
# 매칭 함수
# =====================================================================
def match_patterns(specs: str, caps: list[str],
                   evidence: dict, negatives: list[dict]
                   ) -> tuple[list[str], list[str], float, list[str]]:
    """
    반환: (strong_hits, weak_hits, penalty_total, neg_hits)
    """
    # 줄바꿈 제거 후 공백 정규화
    text = re.sub(r'\s+', ' ', specs).lower().strip()
    # 공백 제거 버전 (AI세탁 ↔ AI 세탁 동시 대응)
    text_nospace = re.sub(r'\s', '', text)
    strong_hits: list[str] = []
    weak_hits:   list[str] = []

    for cap in caps:
        if cap not in evidence:
            continue
        for p in evidence[cap]["strong"]:
            p_ns = re.sub(r'\s', '', p.lower())
            if (p.lower() in text or p_ns in text_nospace) and p not in strong_hits:
                strong_hits.append(p)
        for p in evidence[cap]["weak"]:
            p_ns = re.sub(r'\s', '', p.lower())
            if (p.lower() in text or p_ns in text_nospace) and p not in weak_hits:
                weak_hits.append(p)

    # negative 패턴: ALL 또는 해당 capability에 적용되는 것만
    penalty_total = 0.0
    neg_hits: list[str] = []
    for neg in negatives:
        applies = neg["applies_to"]
        if applies != "ALL" and applies not in caps:
            continue
        neg_ns = re.sub(r'\s', '', neg["pattern"].lower())
        if neg["pattern"].lower() in text or neg_ns in text_nospace:
            penalty_total += neg["penalty"]
            neg_hits.append(f'{neg["pattern"]}(-{neg["penalty"]})')

    return strong_hits, weak_hits, round(penalty_total, 2), neg_hits


# =====================================================================
# 판정 규칙
# =====================================================================
def decide(strong: list[str], weak: list[str],
           penalty: float, specs_empty: bool
           ) -> tuple[str, str]:
    """반환: (label, certainty)"""
    if specs_empty:
        return "washing", "high"

    s = len(strong)
    w = len(weak)

    if s >= 2 and penalty < 0.5:
        return "genuine",    "high"
    if s >= 2 and penalty >= 0.5:
        return "genuine",    "medium"
    if s == 1 and penalty < 0.5:
        return "genuine",    "medium"
    if s == 1 and penalty >= 0.5:
        return "suspicious", "low"
    if s == 0 and w >= 2:
        return "suspicious", "medium"
    if s == 0 and w == 1:
        return "suspicious", "low"
    return "washing", "high"


# =====================================================================
# 메인
# =====================================================================
def main() -> None:
    print("=" * 60)
    print("[*] 온톨로지 패턴 매칭 자동 라벨링")
    print(f"   입력: {INPUT_CSV}")
    print(f"   출력: {OUTPUT_CSV}")
    print("=" * 60)

    evidence  = load_evidence_patterns()
    negatives = load_negative_patterns()
    print(f"  패턴 로드: {sum(len(v['strong'])+len(v['weak']) for v in evidence.values())}개 증거 패턴, "
          f"{len(negatives)}개 부정 패턴")

    # CSV 읽기
    with open(INPUT_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    # fallback: 알 수 없는 분야 → 전체 capability 사용
    all_caps = list(evidence.keys())

    results = []
    label_counts: dict[str, int] = {"genuine": 0, "suspicious": 0, "washing": 0}
    unknown_types: set[str] = set()

    for row in rows:
        ptype  = row.get("product_type", "").strip()
        specs  = row.get("specs_text", "").strip()
        caps   = PRODUCT_CAPABILITY_MAP.get(ptype)

        if caps is None:
            caps = all_caps
            unknown_types.add(ptype)

        specs_empty = len(specs) == 0
        strong, weak, penalty, neg_hits = match_patterns(specs, caps, evidence, negatives)
        label, certainty = decide(strong, weak, penalty, specs_empty)

        matched_str = ""
        if strong:
            matched_str += f"strong: {', '.join(strong)}"
        if weak:
            matched_str += (" | " if matched_str else "") + f"weak: {', '.join(weak)}"
        if neg_hits:
            matched_str += (" | " if matched_str else "") + f"neg: {', '.join(neg_hits)}"
        if not matched_str:
            matched_str = "없음"

        row["label"]            = label
        row["certainty"]        = certainty
        row["matched_patterns"] = matched_str
        results.append(row)
        label_counts[label] += 1

    # 저장
    Path(OUTPUT_CSV).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["domain", "product_type", "product_name",
                  "label", "certainty", "url", "specs_text", "matched_patterns"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    # 결과 요약
    total = len(results)
    print(f"\n[완료] 라벨링 완료: {total}개")
    print(f"   genuine    : {label_counts['genuine']:3d}개 ({label_counts['genuine']/total*100:.1f}%)")
    print(f"   suspicious : {label_counts['suspicious']:3d}개 ({label_counts['suspicious']/total*100:.1f}%)")
    print(f"   washing    : {label_counts['washing']:3d}개 ({label_counts['washing']/total*100:.1f}%)")

    if unknown_types:
        print(f"\n  [!] 매핑 미정의 분야 (전체 capability로 fallback): {', '.join(sorted(unknown_types))}")

    # 샘플 출력 (분야별 1개)
    print("\n[샘플] 분야별 결과 1개씩:")
    seen = set()
    for row in results:
        pt = row["product_type"]
        if pt not in seen:
            seen.add(pt)
            print(f"  [{pt}] {row['product_name'][:30]}")
            print(f"    → {row['label']} / {row['certainty']}")
            print(f"       {row['matched_patterns'][:80]}")

    print(f"\n[저장] {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
