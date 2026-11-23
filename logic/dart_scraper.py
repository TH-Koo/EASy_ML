"""
dart_scraper.py — Open DART API 기반 제품 중심 AI 실체 분석기 (캐시 로직 제거본)
"""
try:
    import OpenDartReader
except ImportError:
    from opendartreader import OpenDartReader
import html
import json
import os
import sys
import re
import contextlib
import io
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import config
    DART_KEY = getattr(config, 'DART_API_KEY', getattr(config, 'DART_KEY', ''))
except ImportError:
    DART_KEY = os.environ.get("DART_API_KEY", "")


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

_DART_TEXT_CACHE_DIR = os.path.join("docs_cache", "dart_text")

# OpenDartReader 는 생성될 때마다 docs_cache/ 의 지난 회사코드 파일을 지우고 오늘
# 파일을 새로 쓴다. 서버에서 이 폴더가 다른 계정 소유라 쓰기가 막히면 생성 자체가
# PermissionError 로 실패했고, DART 가 매번 "조회 불가"가 됐다. 쓰기가 막히면
# 회사코드를 직접 받아 쓸 수 있는 임시 폴더에 캐시하고, 그마저 안 되면 읽을 수
# 있는 기존 파일이라도 쓴다.
_DART_READER = None
_DART_READER_DAY = ""


def _dart_fallback_cache_dir() -> str:
    import tempfile
    return os.environ.get("EASY_DART_CACHE_DIR") or os.path.join(tempfile.gettempdir(), "easy_dart_cache")


def _load_corp_codes_without_docs_cache(api_key: str):
    import glob
    import pandas as pd
    from opendartreader import dart_list

    day = time.strftime("%Y%m%d")
    cache_dir = _dart_fallback_cache_dir()
    path = os.path.join(cache_dir, f"opendartreader_corp_codes_{day}.pkl")
    if os.path.exists(path):
        return pd.read_pickle(path)
    try:
        df = dart_list.corp_codes(api_key)
    except Exception as e:
        # 받기도 실패하면 읽을 수 있는 예전 파일 중 가장 최근 것을 쓴다.
        candidates = sorted(
            glob.glob(os.path.join(cache_dir, "opendartreader_corp_codes_*.pkl"))
            + glob.glob(os.path.join("docs_cache", "opendartreader_corp_codes_*.pkl")),
            key=os.path.basename, reverse=True)
        for old in candidates:
            try:
                return pd.read_pickle(old)
            except OSError:
                continue
        raise e
    try:
        os.makedirs(cache_dir, exist_ok=True)
        df.to_pickle(path)
    except OSError as e:
        print(f"[DART] 회사코드 캐시 저장 실패(무시): {e}")
    return df


def _open_dart_reader(api_key: str):
    """하루 한 번만 만들고 재사용한다. 회사코드 파일(8MB)을 요청마다 읽지 않는다."""
    global _DART_READER, _DART_READER_DAY
    day = time.strftime("%Y%m%d")
    if _DART_READER is not None and _DART_READER_DAY == day:
        return _DART_READER
    try:
        reader = OpenDartReader(api_key)
    except OSError as e:
        print(f"[DART] docs_cache 쓰기 불가({e}) → {_dart_fallback_cache_dir()} 사용")
        from opendartreader.dart import OpenDartReader as reader_cls
        reader = reader_cls.__new__(reader_cls)
        reader.api_key = api_key
        reader.corp_codes = _load_corp_codes_without_docs_cache(api_key)
    _DART_READER, _DART_READER_DAY = reader, day
    return reader


def _dart_text_cache_path(corp_code: str) -> str:
    # v2: 사업보고서 '사업의 내용' 문장이 들어간 뒤의 형식. 예전 캐시는 그 부분이
    # 비어 있으므로 버전으로 갈라 다시 받게 한다.
    return os.path.join(_DART_TEXT_CACHE_DIR, f"{corp_code}_v2_{time.strftime('%Y%m%d')}.txt")


# 사업보고서 문장 가운데 AI·스마트 기능을 말하는 문장만 근거 후보로 쓴다.
_BUSINESS_MARKER = "<<사업의 내용>>"
_REPORT_MARKER = "<<보고서>>"
_FEATURE_PATTERN = re.compile(
    r"(?<![A-Za-z])AI(?![A-Za-z])|인공지능|딥러닝|머신러닝|음성\s?인식|SmartThings|스마트싱스"
    r"|ThinQ|씽큐|(?<![A-Za-z])IoT(?![A-Za-z])|사물인터넷|온디바이스|스마트\s?홈",
    re.IGNORECASE,
)
# 제품 분류·이름 → 사업보고서에서 그 제품군을 가리키는 말.
# 회사 전체의 AI 문장(반도체·스마트폰 등)이 세탁기 주장의 근거로 붙지 않게 거른다.
_CATEGORY_STEMS = [
    (("세탁", "건조기", "워시"), ("세탁", "건조기")),
    (("냉장", "김치"), ("냉장", "김치")),
    (("에어컨", "냉난방", "냉방", "공조"), ("에어컨", "냉방", "공조", "HVAC")),
    (("TV", "티비", "텔레비전"), ("TV", "텔레비전")),
    (("로봇청소기", "청소기"), ("청소기", "청소")),
    (("공기청정", "제습", "가습"), ("공기청정", "공기", "제습", "가습")),
    (("식기세척",), ("식기세척",)),
    (("오븐", "레인지", "인덕션", "쿡탑"), ("오븐", "레인지", "조리", "쿠킹", "인덕션")),
    (("스마트폰", "휴대폰", "갤럭시"), ("스마트폰", "모바일", "Galaxy", "갤럭시")),
    (("모니터",), ("모니터",)),
    (("칫솔",), ("칫솔", "구강")),
    (("스피커", "이어폰", "헤드폰", "오디오"), ("오디오", "스피커", "이어폰", "헤드폰")),
]
_MAX_FEATURE_SENTENCES = 8


def _business_section_sentences(raw_xml: str) -> list:
    """사업보고서 원문에서 'II. 사업의 내용' 부분만 잘라 문장 목록으로 돌려준다."""
    if not raw_xml:
        return []
    text = re.sub(r"<[^>]+>", "\n", raw_xml)
    text = html.unescape(text)
    text = re.sub(r"[ \t\xa0　]+", " ", text)
    start = text.find("II. 사업의 내용")
    if start < 0:
        return []
    end = text.find("III. 재무에 관한 사항", start)
    section = text[start:end if end > start else start + 200000]
    sentences, seen = [], set()
    # "있습니다.2011년 …"처럼 마침표 뒤 띄어쓰기가 빠진 곳도 문장을 가른다.
    for part in re.split(r"(?<=다\.)\s*|\n+", section):
        part = re.sub(r"^[\sㆍ·\-•○▶□■◆※]+", "", part).strip()
        if not (15 <= len(part) <= 400) or part in seen:
            continue
        seen.add(part)
        sentences.append(part)
    return sentences


def _category_stems(product_category: str, product_name: str) -> tuple:
    source = f"{product_category or ''} {product_name or ''}".upper()
    stems = []
    for keys, words in _CATEGORY_STEMS:
        if any(k.upper() in source for k in keys):
            stems.extend(words)
    return tuple(stems)


def _extract_feature_sentences(dart_text: str, product_category: str = "", product_name: str = "") -> list:
    """캐시된 DART 글에서 제품군과 AI 기능을 함께 말하는 사업보고서 문장을 고른다.

    제품군을 알 수 있으면 그 제품군을 언급한 문장만 남긴다. 알 수 없으면
    AI 기능 문장 전체에서 고른다.
    """
    if not dart_text or _BUSINESS_MARKER not in dart_text:
        return []
    body = dart_text.split(_BUSINESS_MARKER, 1)[1]
    candidates = [s.strip() for s in body.split("\n") if s.strip() and _FEATURE_PATTERN.search(s)]
    stems = _category_stems(product_category, product_name)
    if stems:
        candidates = [s for s in candidates if any(w.upper() in s.upper() for w in stems)]
    return candidates[:_MAX_FEATURE_SENTENCES]


def _report_meta(dart_text: str) -> tuple:
    match = re.search(re.escape(_REPORT_MARKER) + r"(\d+)\|([^\n]*)", dart_text or "")
    return (match.group(1), match.group(2).strip()) if match else ("", "")


def _load_dart_text_cache(corp_code: str):
    path = _dart_text_cache_path(corp_code)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _save_dart_text_cache(corp_code: str, text: str) -> None:
    try:
        os.makedirs(_DART_TEXT_CACHE_DIR, exist_ok=True)
        with open(_dart_text_cache_path(corp_code), "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        print(f"[DART] 원문 캐시 저장 실패(무시): {e}")


def _fetch_dart_text(dart, found_corp_code: str) -> str:
    """최근 공시 목록·사업보고서 원문·타법인출자 현황을 한 덩어리 글로 모은다."""
    dart_text_data = ""
    business_part = ""  # 문장 추출이 마지막 표시 뒤를 읽으므로 맨 끝에 붙인다.
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            recent = dart.list(found_corp_code, start='2023-01-01')
            if recent is not None and not recent.empty: 
                dart_text_data += "\n".join(recent['report_nm'].tolist()) + "\n"
        except: pass

        # 정기보고서(사업·반기·분기) 가운데 가장 최근 것의 '사업의 내용'.
        # 예전에는 목록의 열 이름을 'rcp_no' 로 읽어(실제는 'rcept_no') 매번
        # KeyError 가 났고, except 에 묻혀 원문이 한 번도 들어오지 않았다.
        try:
            annual = dart.list(found_corp_code, start='2023-01-01', kind='A')
            if annual is not None and not annual.empty:
                first = annual.iloc[0]
                rcept_no = str(first.get('rcept_no') or first.get('rcp_no') or "")
                raw_xml = dart.document(rcept_no) if rcept_no else ""
                sentences = _business_section_sentences(raw_xml)
                if sentences:
                    business_part = (f"{_REPORT_MARKER}{rcept_no}|{first.get('report_nm', '')}\n"
                                     + _BUSINESS_MARKER + "\n" + "\n".join(sentences) + "\n")
        except Exception as e:
            print(f"[DART] 사업보고서 원문 수집 실패(무시): {e}", file=sys.stderr)

        for year in ['2024', '2023']:
            try:
                investments = dart.report(found_corp_code, '타법인출자', year, '11011')
                if investments is not None and not investments.empty: 
                    dart_text_data += investments.to_string() + "\n"
                break
            except: time.sleep(0.5)
    return dart_text_data + business_part


def check_dart_ai_washing(company_aliases: list, product_name: str = "", product_category: str = "") -> dict:
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
        dart = _open_dart_reader(DART_KEY)
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
        # 공시 원문은 하루 동안 바뀌지 않는다. 사업보고서 원문(document)은 회사에
        # 따라 수십 MB 라 분석마다 받으면 DART 한 곳에서만 20초 넘게 걸렸다.
        dart_text_data = _load_dart_text_cache(found_corp_code)
        if dart_text_data is None:
            dart_text_data = _fetch_dart_text(dart, found_corp_code)
            if dart_text_data.strip():
                _save_dart_text_cache(found_corp_code, dart_text_data)

        # 디버깅이 쉽도록 결과에 실제로 매칭된 기업명을 출력합니다.
        if not dart_text_data.strip():
            return {"status": "데이터 없음", "total_score": 0, "detail": f"[{found_corp_name_str}] 명의로 공시된 상세 내역이 없습니다."}

        # 예전 규칙(공시 목록·출자표의 AI 단어)은 그대로 점수만 매긴다.
        legacy_text = dart_text_data.split(_REPORT_MARKER, 1)[0]
        analysis_result = _evaluate_product_focused_rules(product_name or "", legacy_text)
        evidences = analysis_result.get("evidence_log", [])
        total_score = analysis_result.get("total_score", 0)

        # 사업보고서에서 이 제품군의 AI 기능을 말한 문장. 문장 하나가 근거 기록
        # 하나가 되어, 엔진이 주장마다 관련도를 따로 잰다.
        rcept_no, report_name = _report_meta(dart_text_data)
        report_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}" if rcept_no else ""
        records = [
            {
                "title": sentence[:120],
                "text": sentence,
                "section": "II. 사업의 내용",
                "report_name": report_name,
                "corp_name": found_corp_name_str,
                "rcept_no": rcept_no,
                "url": report_url,
            }
            for sentence in _extract_feature_sentences(dart_text_data, product_category, product_name or "")
        ]
        if records:
            total_score = max(total_score, 60)

        status_msg = "공시 실적 검증 완료" if total_score >= 50 else "AI 핵심 역량 미흡 (워싱 의심)"
        if records:
            detail = f"DART [{found_corp_name_str}] {report_name} 사업의 내용에서 제품 관련 AI 기능 문장 {len(records)}건 확인."
        elif evidences:
            detail = f"DART 분석 결과 [{found_corp_name_str}] 실적 총 {len(evidences)}건 확인."
        else:
            detail = f"[{found_corp_name_str}] 명의의 실질적 AI 관련 공시가 없습니다."
        return {"status": status_msg, "total_score": total_score, "evidence": evidences,
                "records": records, "detail": detail}

    except Exception as e:
        return {"status": "조회 불가", "total_score": 0, "detail": f"DART 서버 지연: {str(e)}"}