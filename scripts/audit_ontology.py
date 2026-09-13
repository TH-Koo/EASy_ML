#!/usr/bin/env python3
"""온톨로지 파일 사이의 정합성을 전수 점검한다.

지금까지 확인된 결함은 대부분 "한 파일에는 있는데 다른 파일에는 없다"는
형태였다. 근거맵이 비어 절대 득점할 수 없던 capability, 인증 DB 레코드가
붙는 rra를 인정하지 않던 가전 요건, 한 문구가 무관한 capability에 중복
등록된 패턴 모두 그렇다. 사람이 눈으로 찾을 대상이 아니므로 검사로 남긴다.

Usage:
    python scripts/audit_ontology.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from analysis_engine import compact_text, normalize_source_type  # noqa: E402

ONTOLOGY = REPO_ROOT / "ontology"


def read(name: str) -> pd.DataFrame:
    path = ONTOLOGY / name
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, encoding="utf-8-sig", on_bad_lines="skip", engine="python")
    frame.columns = [str(c).replace("﻿", "").strip() for c in frame.columns]
    return frame.fillna("")


def main() -> int:
    caps = read("ai_capability_master.csv")
    reqs = read("capability_requirement_master.csv")
    maps = read("requirement_evidence_map_master.csv")
    patterns = read("evidence_pattern_master.csv")
    sources = read("source_credibility_master.csv")
    rules = read("capability_scoring_rule_master.csv")
    implications = read("device_component_implication_master.csv")

    cap_ids = set(caps["capability_id"])
    findings: list[tuple[str, str]] = []

    def report(level: str, message: str) -> None:
        findings.append((level, message))

    # 1) capability가 득점 가능한 배선을 갖췄는가
    for cap_id in sorted(cap_ids):
        n_pattern = len(patterns[patterns.capability_id == cap_id])
        n_req = len(reqs[reqs.capability_id == cap_id])
        n_map = len(maps[maps.capability_id == cap_id])
        if n_req and not n_map:
            report("ERROR", f"{cap_id}: 요건 {n_req}개인데 근거맵 0행 -> 절대 득점 불가")
        if not n_pattern:
            report("ERROR", f"{cap_id}: 패턴 0행 -> 발동 불가")

    # 2) 요건맵의 구성요소가 요건 마스터에 실재하는가
    req_key = {(r.capability_id, compact_text(r.component_name_ko)) for r in reqs.itertuples()}
    for row in maps.itertuples():
        key = (row.capability_id, compact_text(row.component_name_ko))
        if row.capability_id in cap_ids and key not in req_key:
            report("ERROR", f"{row.capability_id}: 근거맵의 '{row.component_name_ko}'가 요건 마스터에 없음")

    # 3) 요건에 근거 경로가 하나도 없는 필수 구성요소
    map_key = {(row.capability_id, compact_text(row.component_name_ko)) for row in maps.itertuples()}
    for row in reqs.itertuples():
        level = str(getattr(row, "required_level", ""))
        if level in ("required", "필수") and (row.capability_id, compact_text(row.component_name_ko)) not in map_key:
            report("WARN", f"{row.capability_id}: 필수 구성요소 '{row.component_name_ko}'에 근거 경로 없음")

    # 4) 인증 DB 레코드는 rra로 붙는다. kc만 인정하면 그 DB를 쓸 수 없다.
    by_cap_src = defaultdict(set)
    for row in maps.itertuples():
        by_cap_src[row.capability_id].add(normalize_source_type(row.acceptable_evidence_source))
    for cap_id, srcs in sorted(by_cap_src.items()):
        if "kc" in srcs and "rra" not in srcs:
            report("ERROR", f"{cap_id}: kc만 인정하고 rra 없음 -> 로컬 인증 DB 사용 불가")

    # 5) 근거맵이 참조하는 출처가 신뢰도 마스터에 있는가
    known_sources = {normalize_source_type(s) for s in sources.get("source_type", [])}
    for src in sorted({normalize_source_type(s) for s in maps.get("acceptable_evidence_source", [])}):
        if src and src not in known_sources:
            report("WARN", f"출처 '{src}'가 근거맵에 쓰이지만 source_credibility_master에 없음 -> 기본값 0.5 적용")

    # 6) 한 문구가 서로 다른 capability에 중복 등록됐는가
    by_text = defaultdict(set)
    for row in patterns.itertuples():
        text = compact_text(row.pattern_text_ko)
        if text:
            by_text[text].add(row.capability_id)
    for text, owners in sorted(by_text.items()):
        if len(owners) > 1:
            report("WARN", f"패턴 '{text}'가 {len(owners)}개 capability에 중복: {sorted(owners)}")

    # 7) 기기->부품 추론이 실재하는 구성요소를 가리키는가
    all_components = {compact_text(r.component_name_ko) for r in reqs.itertuples()}
    for row in implications.itertuples():
        if compact_text(row.component_name_ko) not in all_components:
            report("ERROR", f"기기추론의 '{row.component_name_ko}'가 어떤 요건에도 없음")

    # 8) 죽은 설정 확인: 점수 규칙의 가중치 컬럼이 엔진에서 실제로 쓰이는가
    engine_source = (REPO_ROOT / "analysis_engine.py").read_text(encoding="utf-8")
    unused = [
        column
        for column in rules.columns
        if column != "capability_id" and f'"{column}"' not in engine_source
    ]
    if unused:
        report("WARN", f"capability_scoring_rule_master의 미사용 컬럼: {unused}")

    errors = [m for level, m in findings if level == "ERROR"]
    warns = [m for level, m in findings if level == "WARN"]
    print(f"capability {len(cap_ids)}개 · 요건 {len(reqs)}행 · 근거맵 {len(maps)}행 · 패턴 {len(patterns)}행\n")
    if errors:
        print(f"[ERROR] {len(errors)}건")
        for message in errors:
            print(f"  - {message}")
        print()
    if warns:
        print(f"[WARN] {len(warns)}건")
        for message in warns:
            print(f"  - {message}")
        print()
    if not findings:
        print("정합성 문제 없음")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
