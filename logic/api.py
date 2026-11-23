"""
integrated_api.py — 기관 통합 검증 모듈

External API functions return not only a summary/score but, where available,
the underlying records.  The rule engine performs the final relevance and
credibility judgment; collection functions must not discard evidence text.
"""

import os
import re
import html
import sys
import urllib.parse
from datetime import datetime, timedelta

import pandas as pd
import requests
from sqlalchemy import create_engine, text

import xml.etree.ElementTree as ET


current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    import config
    COMMON_DATAGO_KEY = getattr(config, 'DATAGO_API_KEY', '')
    KIPRIS_KEY = getattr(config, 'KIPRIS_KEY', '') 
    NIPA_KEY = getattr(config, 'DATAGO_API_KEY', '') 
    NTIS_API_KEY = getattr(config, 'NTIS_API_KEY', '')
except ImportError:
    print("❌ 에러: config.py 파일을 찾을 수 없습니다.")
    config = None
    COMMON_DATAGO_KEY = KIPRIS_KEY = NIPA_KEY = NTIS_API_KEY = ""

# DB 접속 문자열은 코드에 두지 않는다: 환경변수 FIDES_DB_URL → config.DB_URL.
DB_URL = os.environ.get("FIDES_DB_URL") or getattr(config, "DB_URL", None)
try:
    engine = create_engine(DB_URL) if DB_URL else None
except Exception:
    engine = None


try:
    from logic.patent_scraper import get_company_patent_data
except ImportError:
    get_company_patent_data = None


def clean_name(name):
    """(주), 주식회사, (유) 등을 제거하고 대문자로 통일."""
    if not name:
        return ""
    name = re.sub(r"\(주\)|주식회사|\(유\)|주\s|", "", str(name))
    return name.strip().upper()


def _record_text(row):
    if not isinstance(row, dict):
        return str(row or "")
    return " ".join(str(v) for v in row.values() if v not in (None, ""))


# =====================================================================
# NTIS validation helpers (integrated into this module)
# =====================================================================



def clean_markup(value: object) -> str:
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]*>", " ", value)
    return " ".join(value.split())


def normalize_organization(value: object) -> str:
    value = clean_markup(value).lower()
    value = value.replace("㈜", "").replace("（株）", "")
    value = re.sub(r"\(\s*주\s*\)|\(\s*유\s*\)|주식회사|유한회사|\bco\.?\s*,?\s*ltd\.?\b", "", value)
    return re.sub(r"[^0-9a-z가-힣]", "", value)


def same_organization(actual: object, expected: object) -> bool:
    actual_norm = normalize_organization(actual)
    expected_norm = normalize_organization(expected)
    return bool(actual_norm and expected_norm and actual_norm == expected_norm)


_AI_PHRASES = (
    "인공지능", "딥러닝", "머신러닝", "신경망", "자연어처리", "음성인식",
    "음성 인식", "객체인식", "객체 인식", "이미지인식", "이미지 인식",
    "컴퓨터비전", "컴퓨터 비전", "생성형 ai", "멀티모달 ai", "ai 기반",
    "ai 기술", "ai 모델", "ai 솔루션", "온디바이스 ai",
    "artificial intelligence", "deep learning", "machine learning",
    "neural network", "computer vision", "speech recognition",
    "object detection", "natural language processing", "generative ai",
)


def is_ai_project(text: object) -> bool:
    normalized = clean_markup(text).lower()
    compact = re.sub(r"\s+", "", normalized)
    return any(re.sub(r"\s+", "", phrase) in compact for phrase in _AI_PHRASES)


def _ntis_title_key(title: object) -> str:
    """같은 과제가 연차·세부과제마다 번호만 달리 여러 번 나온다. 제목으로 합친다."""
    return re.sub(r"\W+", "", clean_markup(title).lower())


def project_identity(project_number: object, title: object) -> str:
    number = re.sub(r"\s+", "", str(project_number or ""))
    return number or re.sub(r"\W+", "", clean_markup(title).lower())


# =====================================================================
# Local DB: RRA, TTA
# =====================================================================

def verify_rra(company_aliases: list, model: str) -> dict:
    if not engine:
        return {"score": 0, "error": "DB 연결 실패"}
    search_model = model.split()[0] if model else ""

    for alias in company_aliases:
        name = clean_name(alias)
        try:
            query = text(
                "SELECT cert_no FROM rra "
                "WHERE company_name LIKE :c_name "
                "AND model_name LIKE :m_name LIMIT 1"
            )
            params = {'c_name': f'%{name}%', 'm_name': f'%{search_model}%'}
            df = pd.read_sql(query, engine, params=params)
            if not df.empty:
                record = df.iloc[0].to_dict()
                return {
                    "score": 20,
                    "records": [record],
                    "evidence": f"인증번호: {record.get('cert_no', '')}",
                    "detail": f"RRA 인증 DB에 [{alias}] 명의 실체가 등록되어 있습니다.",
                }
        except Exception:
            continue
    return {"score": 0, "detail": "RRA 전파인증 DB 내역 없음", "evidence": None, "records": []}


def verify_tta(company_aliases: list) -> dict:
    if not engine:
        return {"score": 0, "error": "DB 연결 실패"}
    for alias in company_aliases:
        name = clean_name(alias)
        try:
            query = text("SELECT * FROM tta_cert_list WHERE company_name LIKE :c_name LIMIT 10")
            params = {'c_name': f'%{name}%'}
            df = pd.read_sql(query, engine, params=params)
            if not df.empty:
                return {
                    "score": 20,
                    "records": df.to_dict(orient="records"),
                    "evidence": "TTA GS인증 보유",
                    "detail": f"TTA 소프트웨어 품질 인증 명단({alias}) 확인되었습니다.",
                }
        except Exception:
            continue
    return {"score": 0, "detail": "TTA/GS 인증 내역 없음", "evidence": None, "records": []}


# =====================================================================
# KIPRIS
# =====================================================================

def verify_kipris(company_aliases: list, product_keyword: str = "") -> dict:
    if not KIPRIS_KEY: return {"score": 0, "error": "KIPRIS 키 미설정"}
    if not get_company_patent_data: return {"score": 0, "error": "patent_scraper 모듈 없음"}
    
    company_aliases = list(set([alias.upper() for alias in company_aliases if alias]))
    
    try:
        count, df, search_type = get_company_patent_data(
            company_aliases=company_aliases,
            product_keyword=product_keyword,
            service_key=KIPRIS_KEY,
        )
        records = df.to_dict(orient="records") if isinstance(df, pd.DataFrame) and not df.empty else []

        if count > 0:
            title = df.iloc[0]['발명의명칭(한글)'] if not df.empty else "특허 내역"
            return {"score": 30, "evidence": f"특허 확인: {title} 등 {count}건", "detail": f"KIPRIS 조회 결과, AI 관련 특허 역량이 확인되었습니다.", "records": df.to_dict(orient="records")}
    except Exception as e: 
        print(f"[KIPRIS 에러] {e}")
        return {"score": 0, "error": f"KIPRIS 통신 실패: {e}"}
    
    return {"score": 0, "detail": "AI 특허 내역 없음", "evidence": None}

def verify_koneps(company_aliases: list) -> dict:
    """나라장터 낙찰정보 - 최근 1년을 1개월 단위로 역순 검색."""
    if not COMMON_DATAGO_KEY:
        return {"score": 0, "error": "API 키 미설정"}

    url = "http://apis.data.go.kr/1230000/ScsbidInfoService/getScsbidListSttusServc01"
    today = datetime.today()
    search_names = list(
        set(clean_name(name) for name in company_aliases if len(clean_name(name)) > 1)
    )

    for name in search_names:
        for months in [6, 12]:
            end_dt = today
            start_dt = today - timedelta(days=30 * months)
            try:
                params = {
                    "serviceKey": urllib.parse.unquote(COMMON_DATAGO_KEY),
                    "numOfRows": "50",
                    "inqryBgnDt": start_dt.strftime("%Y%m%d%H%M"),
                    "inqryEndDt": end_dt.strftime("%Y%m%d%H%M"),
                    "type": "json",
                }
                response = requests.get(url, params=params, timeout=3)
                
                if response.status_code != 200:
                    continue

                items = response.json().get('response', {}).get('body', {}).get('items', [])
                for item in items:
                    entrps_nm = item.get('scsbidEntrpsNm', '')
                    if name in entrps_nm:
                        title = item.get('bidNtceNm', '')
                        if any(kw in title.upper() for kw in ['AI', '인공지능', '빅데이터', '소프트웨어', '시스템', '구축', '유지보수', '개발']):
                            return {
                                "score": 15, 
                                "evidence": f"낙찰: {title}", 
                                "detail": f"나라장터 조회 결과, [{name}] 명의의 공공 사업 실적(최근 1년 내)이 확인되었습니다."
                            }
            except Exception as e:
                print(f"[나라장터 에러] {name} 조회 중 예외 발생: {e}")
                continue

    return {"score": 0, "detail": "최근 1년간 나라장터 낙찰 실적 없음", "evidence": None, "records": []}


def verify_pps_mall(company_aliases: list) -> dict:
    if not COMMON_DATAGO_KEY:
        return {"score": 0, "error": "API 키 미설정"}

    url = "http://apis.data.go.kr/1230000/ShoppingMallPrdctInfoService/getShoppingMallPrdctInfoList"
    search_names = []
    for raw_name in company_aliases:
        split_names = raw_name.split(",") if "," in raw_name else [raw_name]
        for s_name in split_names:
            clean = re.sub(r"\(주\)|주식회사|\(유\)|㈜|^주\s*|\s*주$", "", s_name)
            clean = re.sub(r"[^\w\s가-힣0-9a-zA-Z]", "", clean).strip()
            if re.search(r"[가-힣]", clean) and len(clean) > 1:
                search_names.append(clean)
    search_names = list(set(search_names))
    safe_key = urllib.parse.unquote(COMMON_DATAGO_KEY)

    for name in search_names:
        try:
            params = {
                "serviceKey": safe_key,
                "pageNo": "1",
                "numOfRows": "10",
                "type": "json",
                "entrpsNm": name,
            }
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 500:
                print(f"⚠️ [조달몰] '{name}' 검색 불가 (조달청 서버 500 에러)")
                continue
            elif response.status_code == 200:
                print(f"✅ [조달몰] '{name}' 서버 통신 성공 (데이터 분석 중...)")
                res_json = response.json()
                items = res_json.get("response", {}).get("body", {}).get("items", [])
                if isinstance(items, dict):
                    items = items.get("item", [])
                if items:
                    records = items if isinstance(items, list) else [items]
                    target = records[0]
                    return {
                        "score": 5,
                        "records": records[:10],
                        "evidence": f"몰 등록: {name}",
                        "detail": f"조달청 디지털서비스몰 상품({target.get('prdctNm', '등록 상품')} 등) 등록 확인.",
                    }
        except Exception:
            continue

    return {"score": 0, "detail": "조달청 디지털서비스몰 등록 내역 없음", "evidence": None, "records": []}


# =====================================================================
# NIPA / KAIAC
# =====================================================================

def verify_nipa_solution(company_aliases: list) -> dict:
    # Existing project key retained for compatibility. Move secrets to config/env
    # separately; this patch focuses on preserving evidence records.
    key = "QnGWF0isjBPG/EXxLVhwkts/GtuhtD3cAEf3bEzXPvt73kfBsPflla8lVoK8VtBQLaTw1rhvMpiMHjIFoX6Pew=="
    url = "https://api.odcloud.kr/api/15089204/v1/uddi:4d85feed-91b3-4774-bb76-ce7fd277c990"
    headers = {"Authorization": f"Infuser {key}"}

    try:
        params = {"page": 1, "perPage": 2000, "returnType": "JSON"}
        res = requests.get(url, headers=headers, params=params, timeout=15, verify=False)
        if res.status_code == 200:
            items = res.json().get('data', [])            
            for alias in company_aliases:
                clean_target = clean_name(alias).replace(" ", "")
                if not clean_target:
                    continue
                matched_rows = [
                    row
                    for row in items
                    if clean_target in _record_text(row).replace(" ", "").upper()
                ]
                if matched_rows:
                    return {
                        "score": 20,
                        "records": matched_rows[:20],
                        "evidence": f"NIPA 등록 확인: {alias}",
                        "detail": (
                            f"NIPA 제조AI 공급기업 명단에서 [{alias}] 관련 레코드 "
                            f"{len(matched_rows)}건이 확인되었습니다."
                        ),
                    }
        else:
            print(f"[NIPA 에러] 응답코드: {res.status_code}")
    except Exception as exc:
        print(f"[NIPA 예외 발생] {exc}")
        return {"score": 0, "error": f"NIPA 통신 실패: {exc}", "records": []}

    return {"score": 0, "detail": "NIPA 공급기업 명단 내역 없음", "evidence": None, "records": []}


def verify_kaiac(company: str) -> dict:
    return {"score": 0, "detail": "KAIAC 품질 인증 내역 미확인", "evidence": None}


# =====================================================================
# [API 그룹] NTIS 국가 R&D 연구보고서 실적 검증 (NTIS 전용 규격 적용)
# =====================================================================
_NTIS_URL = "https://www.ntis.go.kr/rndopen/openApi/public_project"
_NTIS_PAGE_SIZE = 100
# 회사 이름만으로 찾으면 대기업은 과제가 수천 건이라 상위 일부만 보고 끝났다
# (예전에는 50건). 그 안에 AI 과제가 없으면 실제로 있어도 "없음"이 됐다.
# AI 단어를 붙인 검색을 함께 돌리고, 검색마다 끝 페이지까지 읽는다.
_NTIS_AI_QUERY_WORDS = ("인공지능", "AI", "딥러닝", "머신러닝")
_NTIS_MAX_PER_QUERY = int(os.getenv("EASY_NTIS_MAX_PER_QUERY", "1000"))
_NTIS_CACHE_VERSION = 3


def _ntis_cache_path(name: str) -> str:
    import tempfile
    base = os.environ.get("EASY_NTIS_CACHE_DIR") or os.path.join(tempfile.gettempdir(), "easy_ntis_cache")
    safe = re.sub(r"[^0-9A-Za-z가-힣]", "_", name)
    return os.path.join(base, f"{safe}_{datetime.now():%Y%m%d}_v{_NTIS_CACHE_VERSION}.json")


def _ntis_cache_load(name: str):
    import json
    try:
        with open(_ntis_cache_path(name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _ntis_cache_save(name: str, projects: list) -> None:
    import json
    path = _ntis_cache_path(name)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(projects, f, ensure_ascii=False)
    except OSError as e:
        print(f"[NTIS] 캐시 저장 실패(무시): {e}")


def _ntis_total_hits(root) -> int:
    for elem in root.iter():
        if elem.tag.split("}")[-1].lower() in {"totalhits", "total_hits", "totalcount", "total"}:
            try:
                return int(re.sub(r"\D", "", elem.text or ""))
            except ValueError:
                return 0
    return 0


def _ntis_fetch_page(raw_key: str, query: str, position: int):
    """NTIS 한 페이지. (HIT 요소 목록, 전체 건수, 오류 문자열) 을 돌려준다."""
    params = {
        "apprvKey": raw_key, "collection": "project", "SRWR": query,
        "returnType": "xml", "startPosition": position, "displayCnt": _NTIS_PAGE_SIZE,
    }
    try:
        response = requests.get(_NTIS_URL, params=params, timeout=30)
    except requests.RequestException as e:
        return [], 0, f"{query}: 요청 오류 ({type(e).__name__})"
    if response.status_code != 200:
        return [], 0, f"{query}: HTTP {response.status_code}"
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return [], 0, f"{query}: NTIS 응답 XML 파싱 실패"
    if root.tag.split("}")[-1].lower() in {"error", "exception"}:
        message = " ".join((e.text or "").strip() for e in root.iter() if (e.text or "").strip())
        return [], 0, f"{query}: {message or 'NTIS API 오류 응답'}"
    hits = [item for item in root.iter() if item.tag.split("}")[-1] == "HIT"]
    return hits, _ntis_total_hits(root), ""


def _ntis_fetch_all(raw_key: str, query: str, max_results: int = 0):
    """검색 하나를 끝 페이지까지(최대 max_results, 기본 _NTIS_MAX_PER_QUERY 건) 읽는다."""
    from concurrent.futures import ThreadPoolExecutor

    hits, total, error = _ntis_fetch_page(raw_key, query, 1)
    if error:
        return [], [error]
    errors = []
    cap = max_results or _NTIS_MAX_PER_QUERY
    limit = min(total, cap) if total else cap
    if total and limit > _NTIS_PAGE_SIZE:
        # 전체 건수를 알면 나머지 페이지를 한꺼번에 받는다.
        positions = list(range(1 + _NTIS_PAGE_SIZE, limit + 1, _NTIS_PAGE_SIZE))
        with ThreadPoolExecutor(max_workers=4) as pool:
            for page_hits, _, page_error in pool.map(lambda pos: _ntis_fetch_page(raw_key, query, pos), positions):
                hits.extend(page_hits)
                if page_error:
                    errors.append(page_error)
    elif not total:
        # 전체 건수가 응답에 없으면 빈 페이지가 나올 때까지 차례로 넘긴다.
        position = 1 + _NTIS_PAGE_SIZE
        last = hits
        while last and len(hits) < limit:
            last, _, page_error = _ntis_fetch_page(raw_key, query, position)
            if page_error:
                errors.append(page_error)
                break
            hits.extend(last)
            position += _NTIS_PAGE_SIZE
    return hits, errors


def _ntis_project_from_hit(item, name: str):
    """HIT 하나를 과제 기록으로 바꾼다. 수행기관이 다르거나 AI 과제가 아니면 None."""
    def get_text(path, sep=" "):
        elem = item.find(path)
        if elem is None:
            return ""
        return sep.join(part.strip() for part in elem.itertext() if part and part.strip())

    project_name = get_text("./ProjectTitle/Korean") or get_text("./ProjectTitle")
    if not project_name:
        return None
    searchable_text = " ".join([
        project_name,
        get_text("./Goal/Full"),
        get_text("./Abstract/Full"),
        get_text("./Keyword/Korean"),
        get_text("./Effect/Full"),
    ]).lower()
    if not is_ai_project(searchable_text):
        return None
    # 검색어(name)를 lead_company 에 복사하지 않는다. 실제 수행기관을 읽어
    # 검색한 회사와 정확히 같을 때만 인정한다(엘지디스플레이 ≠ 엘지전자).
    agency_raw = get_text("./ResearchAgency/Name", "") or get_text(".//ResearchAgency/Name", "")
    research_agency = clean_markup(re.sub(r"<[^>]*>", "", html.unescape(agency_raw)))
    if not same_organization(research_agency, name):
        return None
    project_number = get_text("./ProjectNumber")
    project_name = clean_markup(project_name)
    project_id = project_identity(project_number, project_name)
    if not project_id:
        return None
    # 'product_ai'를 카테고리 단어만으로 확정하지 않는다.
    # 실제 AI 기능 일치 판정은 온톨로지 패턴으로 수행한다.
    return {
        "project_name": project_name,
        "project_number": project_number or None,
        "source_record_id": project_number or project_id,
        "research_agency": research_agency,
        "lead_company": research_agency,
        "searched_name": name,
        "company_verified": True,
        "is_ai_project": True,
        "project_summary": clean_markup(searchable_text)[:2000],
        "relevance_type": "general_ai",
        "status": "verified",
    }


def _ntis_projects_for_company(raw_key: str, name: str):
    """회사 하나의 AI 과제 전부. 오류가 없을 때만 하루 동안 캐시한다."""
    cached = _ntis_cache_load(name)
    if cached is not None:
        return cached, []
    projects, errors = {}, []
    # 회사 이름만으로 한 검색은 대기업이면 수천 건이라(삼성전자 7천여 건) 첫
    # 페이지만 본다. AI 과제는 AI 단어를 붙인 검색에서 끝까지 찾는다.
    queries = [(name, _NTIS_PAGE_SIZE)] + [(f"{name} {word}", 0) for word in _NTIS_AI_QUERY_WORDS]
    for query, max_results in queries:
        hits, query_errors = _ntis_fetch_all(raw_key, query, max_results)
        errors.extend(query_errors)
        for item in hits:
            project = _ntis_project_from_hit(item, name)
            if project:
                projects.setdefault(_ntis_title_key(project["project_name"]), project)
    rows = list(projects.values())
    if not errors:
        _ntis_cache_save(name, rows)
    return rows, errors


def verify_ntis_rnd(company_aliases: list, product_keyword: str = "") -> dict:
    if not NTIS_API_KEY:
        return {"score": 0, "error": "NTIS API 키 미설정"}

    search_names = list(dict.fromkeys(
        clean_name(name)
        for name in company_aliases
        if name and len(clean_name(name)) > 1
    ))

    if not search_names:
        return {
            "score": 0,
            "detail": "NTIS 조회 유효 기업명 없음",
            "evidence": None
        }

    raw_key = NTIS_API_KEY.strip()
    valid_projects = {}
    api_errors = []

    for name in search_names:
        try:
            rows, errors = _ntis_projects_for_company(raw_key, name)
        except Exception as e:
            import traceback
            traceback.print_exc()
            rows, errors = [], [f"{name}: 처리 오류 ({type(e).__name__}: {e})"]
        api_errors.extend(errors)
        for project in rows:
            valid_projects.setdefault(_ntis_title_key(project.get("project_name")), project)

    projects = list(valid_projects.values())

    if projects:
        title = projects[0]["project_name"]
        verified_count = sum(bool(row["company_verified"]) for row in projects)

        return {
            "score": 0,  # 점수는 단일 온톨로지 엔진에서만 산출
            "evidence": f"NTIS AI 관련 과제 검색: {title} 등 총 {len(projects)}건",
            "detail": f"NTIS AI 관련 과제 {len(projects)}건 검색, 수행기관 일치 확인 {verified_count}건. 기술 관련성은 별도 검증합니다.",
            "records": projects,
            "status": "verified"
        }

    if api_errors:
        return {
            "score": 0,
            "detail": "NTIS 검색 결과를 정상적으로 확인하지 못했습니다.",
            "error": "; ".join(api_errors[:5]),
            "evidence": None,
            "status": "error"
        }

    return {
        "score": 0,
        "detail": "NTIS 검색 결과에서 AI 관련 과제를 확인하지 못했습니다.",
        "evidence": None,
        "records": [],
        "status": "not_found"
    }



def verify_iitp(company_names, product_keyword=""):
    """
    NTIS 오픈 API를 통해 정보통신기획평가원(IITP) R&D 과제 실적 실시간 조회
    """
    if not NTIS_API_KEY:
        return {"score": 0, "error": "NTIS API 키 미설정"}

    if isinstance(company_names, str):
        company_names = [company_names]

    matched_items = []
    # 기존 NTIS API와 동일한 엔드포인트 사용
    url = "https://www.ntis.go.kr/rndopen/openApi/public_project" 
    search_names = list(set([clean_name(name) for name in company_names if len(clean_name(name)) > 1]))

    for company in search_names:
        params = {
            "apprvKey": NTIS_API_KEY.strip(),
            "collection": "project",
            "SRWR": company,
            "returnType": "json",
            "startPosition": 1,
            "displayCnt": 50
        }

        try:
            # 나라장터처럼 멈추지 않도록 timeout 5초 설정
            response = requests.get(url, params=params, timeout=5)
            
            if response.status_code == 200:
                if response.text.strip().startswith("<?xml") or "<error>" in response.text:
                    continue
                
                res_json = response.json()
                hits = res_json.get('RESULT', {}).get('RESULTSET', {}).get('HIT', [])
                if isinstance(hits, dict):
                    hits = [hits]

                for item in hits:
                    # 소관전문기관 필터링: IITP(정보통신기획평가원) 확인
                    agency = item.get('SpecializedAgency', '')
                    if '정보통신' not in agency and 'IITP' not in agency.upper():
                        continue 

                    project_name = item.get('ProjectTitle', '')
                    if not project_name:
                        title_info = item.get('ResultTitle', {})
                        project_name = title_info.get('Korean', '') if isinstance(title_info, dict) else ''
                    
                    task_no = item.get('ProjectNo', '')
                    is_product_related = any(k in project_name for k in product_keyword.split()) if product_keyword else False
                    
                    matched_items.append({
                        "source_record_id": str(task_no),
                        "과제명": project_name,
                        "주관기관": company,
                        "사업명": agency,
                        "relevance_type": "product_ai" if is_product_related else "general_ai",
                        "status": "verified"
                    })
        except Exception as e:
            print(f"[IITP API 연동 오류 ({company})]: {e}")

    count = len(matched_items)
    has_product_ai = any(item["relevance_type"] == "product_ai" for item in matched_items)
    score = 25 if has_product_ai else (15 if count > 0 else 0)

    return {
        "status": "verified" if count > 0 else "not_found",
        "count": count,
        "items": matched_items[:5],
        "score": score,
        "message": f"IITP 실제 R&D 과제 {count}건 연동 확인" if count > 0 else "IITP 과제 수행 내역 없음"
    }