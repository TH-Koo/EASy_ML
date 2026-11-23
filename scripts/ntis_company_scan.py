"""회사별 NTIS AI 과제를 끝까지 조회해, 예전 방식(상위 50건)과 비교한다.

NTIS 키는 서버 IP 에서만 열리므로 EC2 에서 실행한다.

    python scripts/ntis_company_scan.py                 # 기본 회사 목록
    python scripts/ntis_company_scan.py 삼성전자 코웨이   # 회사 지정
    python scripts/ntis_company_scan.py --api-file /tmp/api_new.py 삼성전자
        # 아직 배포 전인 브랜치의 logic/api.py 로 돌릴 때

캐시를 무시하려면 EASY_NTIS_CACHE_DIR 를 빈 폴더로 지정한다.
"""
import argparse
import importlib.util
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.getcwd())  # /tmp 로 꺼내 돌릴 때는 저장소 폴더에서 실행한다

DEFAULT_COMPANIES = [
    "삼성전자", "엘지전자", "코웨이", "쿠쿠전자", "쿠쿠홈시스", "에스케이매직", "위닉스",
    "청호나이스", "위니아", "신일전자", "한경희생활과학", "바디프랜드", "세라젬",
    "로보락", "에코백스", "드리미", "다이슨코리아", "애플코리아", "샤오미",
]


def load_api(api_file):
    import logic.api as current
    if not api_file:
        return current
    spec = importlib.util.spec_from_file_location("api_under_test", api_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.NTIS_API_KEY = current.NTIS_API_KEY  # 임시 경로에서는 config 를 못 찾는다
    return mod


def old_way_count(api, name):
    """예전 방식: 회사 이름 검색 상위 50건만 본다."""
    hits, _, error = api._ntis_fetch_page(api.NTIS_API_KEY.strip(), name, 1)
    if error:
        return f"오류 {error}"
    return sum(1 for h in hits[:50] if api._ntis_project_from_hit(h, name))


def diagnose(api, name):
    """AI 검색 결과가 있는데 0건일 때, 수행기관·AI 판별 중 어디서 떨어지는지 보여 준다."""
    import collections
    import html
    import re
    hits, _ = api._ntis_fetch_all(api.NTIS_API_KEY.strip(), f"{name} 인공지능")
    agencies = collections.Counter()
    same = ai = 0
    samples = []
    for h in hits:
        raw = "".join(h.find("./ResearchAgency/Name").itertext()) if h.find("./ResearchAgency/Name") is not None else ""
        agency = api.clean_markup(re.sub(r"<[^>]*>", "", html.unescape(raw)))
        agencies[agency] += 1
        title = api.clean_markup("".join(h.find("./ProjectTitle/Korean").itertext())) if h.find("./ProjectTitle/Korean") is not None else ""
        if api.same_organization(agency, name):
            same += 1
            if len(samples) < 5:
                samples.append(title[:60])
        if api._ntis_project_from_hit(h, agency) is not None:
            ai += 1
    print(f"   [진단] '{name} 인공지능' {len(hits)}건: 수행기관 일치 {same}, (기관 무관) AI 과제 {ai}")
    print(f"   [진단] 수행기관 상위: {agencies.most_common(8)}")
    for t in samples:
        print(f"   [진단] 일치 과제 예: {t}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("companies", nargs="*")
    parser.add_argument("--api-file")
    args = parser.parse_args()
    api = load_api(args.api_file)
    key = api.NTIS_API_KEY.strip()
    if not key:
        sys.exit("NTIS_API_KEY 가 없습니다.")

    for name in args.companies or DEFAULT_COMPANIES:
        totals = []
        for query in [name] + [f"{name} {w}" for w in api._NTIS_AI_QUERY_WORDS]:
            _, total, error = api._ntis_fetch_page(key, query, 1)
            totals.append(f"{query.replace(name, '').strip() or '이름'}={error or total}")
        t0 = time.time()
        res = api.verify_ntis_rnd([name])
        took = time.time() - t0
        records = res.get("records") or []
        old = old_way_count(api, name)
        old = f"{old}건" if isinstance(old, int) else old
        print(f"\n## {name}  새 방식 {len(records)}건 ({took:.1f}s)  예전(상위 50건) {old}")
        print(f"   검색 건수: {', '.join(totals)}")
        if res.get("error"):
            print(f"   오류: {res['error']}")
        for r in records[:10]:
            print(f"   - {r['project_name'][:70]}  [{r.get('research_agency')}]")
        if len(records) > 10:
            print(f"   ... 외 {len(records) - 10}건")
        if not records and not res.get("error") and any(not t.endswith("=0") for t in totals[1:]):
            diagnose(api, name)


if __name__ == "__main__":
    main()
