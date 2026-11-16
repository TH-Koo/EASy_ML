"""
dart_scraper.py — Open DART API 기반 제품 중심 AI 실체 분석기 (캐시 로직 제거본)
"""
try:
    import OpenDartReader
except ImportError:
    from opendartreader import OpenDartReader
import json
import os
import sys
import re
import contextlib
import io
import time
import glob
import threading
import traceback
from datetime import date, datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import config
    DART_KEY = getattr(config, 'DART_API_KEY', getattr(config, 'DART_KEY', ''))
except ImportError:
    DART_KEY = os.environ.get("DART_API_KEY", "")


# ── 기업 고유번호 목록 ─────────────────────────────────────────────────
#
# OpenDartReader 생성자는 '현재 작업 폴더'의 docs_cache 를 쓰고, 날짜가 바뀔
# 때마다 기존 목록 파일을 지운 뒤 DART 에서 통째로 다시 받는다. 배포 서버에서
# 이 다운로드나 파일 쓰기가 실패하면 모든 분석이 'DART 조회 불가'가 된다.
# 그래서 생성자를 건너뛰고 목록을 직접 읽는다.
#   1) 프로젝트 docs_cache 에 최근(_CORP_MAX_AGE_DAYS 이내) 목록이 있으면 그것을 쓴다.
#   2) 없거나 오래됐으면 새로 받아 저장한다(저장 실패는 무시).
#   3) 받기도 실패하면 오래된 목록이라도 쓴다. 기업 목록은 천천히 바뀐다.
# 읽은 목록은 프로세스 안에서 재사용한다.
_CORP_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs_cache")
_CORP_PREFIX = "opendartreader_corp_codes_"
_CORP_MAX_AGE_DAYS = 30
_corp_lock = threading.Lock()
_corp_state = {"df": None, "day": None}


def _corp_files() -> list:
    """docs_cache 의 목록 파일을 (날짜, 경로) 로, 최신순으로."""
    out = []
    for path in glob.glob(os.path.join(_CORP_CACHE_DIR, _CORP_PREFIX + "*.pkl")):
        stamp = os.path.basename(path)[len(_CORP_PREFIX):-4]
        try:
            out.append((datetime.strptime(stamp, "%Y%m%d").date(), path))
        except ValueError:
            continue
    return sorted(out, reverse=True)


def _read_corp_file(path: str):
    """목록 파일을 읽는다. 다른 pandas 버전으로 저장돼 못 읽으면 None."""
    try:
        return pd.read_pickle(path)
    except Exception as e:
        print(f"[DART] 기업 목록 파일을 읽지 못함({os.path.basename(path)}): {type(e).__name__}")
        return None


def _download_corp_codes(today):
    try:
        from opendartreader import dart_list
    except ImportError:
        from OpenDartReader import dart_list
    df = dart_list.corp_codes(DART_KEY)
    try:
        os.makedirs(_CORP_CACHE_DIR, exist_ok=True)
        df.to_pickle(os.path.join(_CORP_CACHE_DIR, f"{_CORP_PREFIX}{today:%Y%m%d}.pkl"))
    except OSError as e:
        print(f"[DART] 기업 목록 저장 실패(계속 진행): {e}")
    return df


def _load_corp_codes():
    today = date.today()
    with _corp_lock:
        if _corp_state["df"] is not None and _corp_state["day"] == today:
            return _corp_state["df"]
        files = _corp_files()
        df = None
        # 1) 최근 목록
        for stamp, path in files:
            if (today - stamp).days > _CORP_MAX_AGE_DAYS:
                break
            df = _read_corp_file(path)
            if df is not None:
                break
        # 2) 새로 받기
        if df is None:
            try:
                df = _download_corp_codes(today)
            except Exception as e:
                print(f"[DART] 기업 목록 받기 실패: {type(e).__name__}: {e}")
        # 3) 오래된 목록이라도
        if df is None:
            for stamp, path in files:
                df = _read_corp_file(path)
                if df is not None:
                    print(f"[DART] {stamp} 기업 목록으로 계속 진행")
                    break
        if df is None:
            raise RuntimeError("DART 기업 목록을 읽지도 받지도 못함")
        _corp_state.update(df=df, day=today)
        return df


def _make_reader():
    """생성자 없이 리더를 만든다. 리더 메서드는 api_key 와 corp_codes 만 쓴다."""
    reader = OpenDartReader.__new__(OpenDartReader)
    reader.api_key = DART_KEY
    reader.corp_codes = _load_corp_codes()
    return reader


def _clean_dart_text(text: str) -> str:
    if not text: return ""
    text = text[:200000] # 정규식 과부하 방지를 위해 최대 20만 자로 제한
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\b\d{14}\b|\b\d{8}\b|\b\d{4}[-.]\d{2}[-.]\d{2}\b', '', text) 
    text = re.sub(r'\b\d{1,3}(,\d{3})+\b|\b\d{4,}\b|\b\d+\.\d+\b|\b\d{1,2}\b', '', text)          
    return re.sub(r'\s+', ' ', text).strip()

def _evaluate_product_focused_rules(product_name: str, dart_text_data: str) -> dict:
    ai_keywords = ['인공지능', '딥러닝', '머신러닝', '생성형', 'llm', '자연어', '신경망', 'ai', '스마트', '빅데이터']
    rnd_keywords = ['연구', '개발', '센터', '랩', 'lab', '투자', '출자', '인수', '사업', '수주', '공급', '솔루션']
    ip_keywords = ['특허', '지식재산', '지적재산', '출원', '등록', 'ip']
    
    prod_tokens = [token for token in product_name.split() if len(token) > 1]
    
    rnd_score, ip_score, product_score = 0, 0, 0
    evidence_log = []

    for line in dart_text_data.split('\n'):
        line_lower = line.lower()
        if not line_lower.strip(): continue
        
        # 🎯 AI 관련 키워드가 문장에 없으면 무조건 버림
        if not any(k in line_lower for k in ai_keywords):
            continue
        
        clean_context = _clean_dart_text(line)[:150]
        
        if prod_tokens and any(pt.lower() in line_lower for pt in prod_tokens):
            if product_score == 0: product_score = 20
            evidence_log.append(f"📦 [AI 제품적용] {clean_context}")
        elif any(k in line_lower for k in rnd_keywords):
            if rnd_score == 0: rnd_score = 60
            evidence_log.append(f"💰 [AI 사업/연구] {clean_context}")
        elif any(k in line_lower for k in ip_keywords):
            if ip_score == 0: ip_score = 20
            evidence_log.append(f"📜 [AI 특허/IP] {clean_context}")
        else:
            if rnd_score == 0: rnd_score = 60
            evidence_log.append(f"🔍 [AI 기술언급] {clean_context}")

    unique_evidences = list(set(evidence_log))
    return {"total_score": min(rnd_score + ip_score + product_score, 100), "evidence_log": unique_evidences[:5]}

def check_dart_ai_washing(company_aliases: list, product_name: str = "") -> dict:
    if not DART_KEY or not company_aliases: return {"status": "스킵", "total_score": 0, "detail": "기업명 미확인."}

    search_list = []
    if isinstance(company_aliases, str):
        search_list = [n.strip() for n in company_aliases.split(',')]
    elif isinstance(company_aliases, list):
        for name in company_aliases:
            if isinstance(name, str) and ',' in name:
                search_list.extend([n.strip() for n in name.split(',')])
            else:
                search_list.append(name)
    
    # 중복 제거
    clean_list = list(set([n for n in search_list if n]))

    try:
        dart = _make_reader()
        corp_list = dart.corp_codes
        
        found_corp_code = None
        found_corp_name_str = None
        
        # 🚀 [핵심 패치 1] 무조건 '정확히 일치(Exact Match)' 하는 상장사를 최우선으로 찾습니다.
        for name in clean_list:
            clean = re.sub(r'\(주\)|주식회사|\(유\)|㈜', '', name).strip()
            if not clean: continue
            
            # 대소문자 무시하고 정확히 일치하는지 확인
            corp_info = corp_list[corp_list['corp_name'].str.upper() == clean.upper()]
            if not corp_info.empty:
                # 상장사(stock_code 존재)를 우선 선택
                listed = corp_info[corp_info['stock_code'].notna() & (corp_info['stock_code'].str.strip() != '')]
                if not listed.empty:
                    found_corp_code = listed.iloc[0]['corp_code']
                    found_corp_name_str = listed.iloc[0]['corp_name']
                else:
                    found_corp_code = corp_info.iloc[0]['corp_code']
                    found_corp_name_str = corp_info.iloc[0]['corp_name']
                break
                
        # 🚀 [핵심 패치 2] 정확히 일치하는게 없다면, '포함(Contains)'하는 상장사를 찾습니다.
        if not found_corp_code:
            for name in clean_list:
                clean = re.sub(r'\(주\)|주식회사|\(유\)|㈜', '', name).strip()
                if not clean: continue
                
                matches = corp_list[corp_list['corp_name'].str.upper().str.contains(clean.upper(), na=False, regex=False)]
                if not matches.empty:
                    listed = matches[matches['stock_code'].notna() & (matches['stock_code'].str.strip() != '')]
                    if not listed.empty:
                        found_corp_code = listed.iloc[0]['corp_code']
                        found_corp_name_str = listed.iloc[0]['corp_name']
                        break
                    
        # 🚀 [핵심 패치 3] 상장사도 없으면, 포함하는 기업 중 아무거나 첫번째
        if not found_corp_code:
            for name in clean_list:
                clean = re.sub(r'\(주\)|주식회사|\(유\)|㈜', '', name).strip()
                if not clean: continue
                
                matches = corp_list[corp_list['corp_name'].str.upper().str.contains(clean.upper(), na=False, regex=False)]
                if not matches.empty:
                    found_corp_code = matches.iloc[0]['corp_code']
                    found_corp_name_str = matches.iloc[0]['corp_name']
                    break

        if not found_corp_code: 
            return {"status": "비상장사", "total_score": 0, "detail": "DART 미등록 법인."}

        # 🚀 [핵심 패치 4] 애매한 이름 대신 고유 8자리 코드(corp_code)로 정확하게 통신 시도
        dart_text_data = ""
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                recent = dart.list(found_corp_code, start='2023-01-01')
                if recent is not None and not recent.empty: 
                    dart_text_data += "\n".join(recent['report_nm'].tolist()) + "\n"
            except: pass

            try:
                annual = dart.list(found_corp_code, start='2023-01-01', kind='A')
                if annual is not None and not annual.empty:
                    raw_xml = dart.document(annual.iloc[0]['rcp_no'])
                    if raw_xml: dart_text_data += raw_xml[:150000] + "\n" 
            except: pass

            for year in ['2024', '2023']:
                try:
                    investments = dart.report(found_corp_code, '타법인출자', year, '11011')
                    if investments is not None and not investments.empty: 
                        dart_text_data += investments.to_string() + "\n"
                    break
                except: time.sleep(0.5)

        # 디버깅이 쉽도록 결과에 실제로 매칭된 기업명을 출력합니다.
        if not dart_text_data.strip():
            return {"status": "데이터 없음", "total_score": 0, "detail": f"[{found_corp_name_str}] 명의로 공시된 상세 내역이 없습니다."}

        analysis_result = _evaluate_product_focused_rules(product_name, dart_text_data)
        evidences = analysis_result.get("evidence_log", [])
        status_msg = "공시 실적 검증 완료" if analysis_result.get("total_score", 0) >= 50 else "AI 핵심 역량 미흡 (워싱 의심)"
        
        return {"status": status_msg, "total_score": analysis_result.get("total_score", 0), "evidence": evidences, "detail": f"DART 분석 결과 [{found_corp_name_str}] 실적 총 {len(evidences)}건 확인." if evidences else f"[{found_corp_name_str}] 명의의 실질적 AI 관련 공시가 없습니다."}

    except Exception as e:
        # 원인이 서버 로그에 남아야 배포 환경 문제를 찾을 수 있다
        print(f"[DART] 조회 실패: {type(e).__name__}: {e}")
        traceback.print_exc()
        return {"status": "조회 불가", "total_score": 0, "detail": f"DART 서버 지연: {str(e)}"}