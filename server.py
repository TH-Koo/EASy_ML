"""
server.py — Fides 메인 서버 (온톨로지 분석 엔진 연동 완료)

FastAPI 기반 웹 서버. 다나와 URL을 입력받아 AI 워싱 여부를 분석하고 결과를 스트리밍으로 반환합니다.

분석 파이프라인 (run_analysis):
    1. 크롤링      — crawler.py로 다나와 상품 페이지 스크래핑 + 스크린샷
    2. OCR         — ocr_analyzer.py로 상세 이미지에서 텍스트 추출
    3. Gemini 정제 — OCR 텍스트 오타 교정 및 회사명·모델명 추출
    4. 정규화      — normalizer.py로 회사명·모델명 정규화 및 동의어 확장
    5. 병렬 검색   — KC DB, 조달청, TIPA, KORAIA, DART 등 동시 조회
    6. 특허·인증   — 특허(KIPRIS) 수, GS/NEP 인증 조회
    7. 🧠 온톨로지 — analysis_engine.py 호출하여 ACCS 신뢰도 및 판정(verdict) 산출
"""

import os
import sys
import io
import json
import uuid
import asyncio
import contextlib
import concurrent.futures
import re
import urllib.parse
from datetime import datetime
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
import bcrypt as _bcrypt_lib
from pydantic import BaseModel
from sqlalchemy import create_engine, text
import pandas as pd
from google import genai
from google.genai import types as genai_types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logic'))

from crawler import get_product_data
from ocr_analyzer import analyze_ai_washing
from normalizer import normalize_data, expand_company_aliases, is_valid_model_number
from patent_scraper import get_company_patent_data
from llm_resolver import resolve_real_company_name, resolve_model_name
from dart_scraper import check_dart_ai_washing  # 🔥 DART 스크래퍼 추가

"""
설정은 config.py 하나에서만 읽는다 (gitignore 되어 있다).

`_config` 로 붙잡아 두는 이유: 아래에서 DB_URL 등을 `getattr` 로 꺼내야
하는데, import 가 실패한 경우에도 이름이 있어야 한다. 예전에는 import 만
try 로 감싸 두고 DB 접속 문자열은 파일에 직접 박아 놨다.
"""
class _MissingConfig:
    """config.py 가 없을 때 자리를 지킨다. getattr 은 전부 기본값으로 떨어진다."""

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import config as _config
except Exception:
    _config = _MissingConfig()

try:
    DATA_GO_KR_KEY = urllib.parse.unquote(_config.DATA_GO_KR_KEY)
    gemini_client = genai.Client(api_key=_config.GEMINI_API_KEY)
except Exception:
    DATA_GO_KR_KEY = ""
    gemini_client = None


try:
    from fides_integration import (
        infer_product_type,
        load_weight_predictor,
        secure_analyze_bundle,
        weighting_summary,
    )
except ImportError as exc:
    raise RuntimeError("fides_integration.py 또는 analysis_engine.py를 불러오지 못했습니다.") from exc

# CEN 가중치 모델은 서버 시작 시 한 번만 불러와 모든 분석 요청에 재사용한다.
# 체크포인트가 없으면 None 이고, 엔진은 규칙 기반 가중치로 동작한다.
WEIGHT_PREDICTOR = load_weight_predictor()

# DB 접속 문자열은 코드에 두지 않는다.
#
# 여기에 계정과 비밀번호가 그대로 박혀 있었다. server.py 는 깃에 추적되므로
# 운영 RDS 자격증명이 저장소 히스토리에 남았다 — config.py 를 gitignore 해
# 둔 것이 이 한 줄 때문에 무의미했다. 지운다고 히스토리에서 사라지지는
# 않으므로 **비밀번호는 반드시 교체해야 한다.**
#
# 우선순위: 환경변수 → config.py. 둘 다 없으면 켜지지 않고 바로 죽는다.
# 조용히 빈 값으로 뜨면 첫 조회 때 알 수 없는 오류로 실패한다.
DB_URL = os.environ.get("FIDES_DB_URL") or getattr(_config, "DB_URL", None)
if not DB_URL:
    raise RuntimeError(
        "DB 접속 정보가 없습니다. 환경변수 FIDES_DB_URL 을 넣거나 "
        "config.py 에 DB_URL 을 정의하세요."
    )
engine = create_engine(DB_URL, pool_pre_ping=True)

app = FastAPI(title="Fides API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# 진행 상황 + 결과 저장소 (메모리)
_tasks: dict[str, dict] = {}

# ══════════════════════════════════════════
# JWT 인증 설정
# ══════════════════════════════════════════
# 서명 키도 코드에 두지 않는다. 이 값이 새면 아무나 남의 토큰을 만들 수 있다.
# 기본값을 그대로 쓰면 켜질 때 경고를 찍는다 — 조용히 넘어가면 배포본이
# `change-me` 로 서명하게 된다.
JWT_SECRET = os.environ.get("FIDES_JWT_SECRET") or getattr(_config, "JWT_SECRET", "")
if not JWT_SECRET:
    JWT_SECRET = "fides-jwt-secret-2024-change-me"
    print("[WARN] JWT_SECRET 이 설정되지 않아 기본값을 씁니다. 배포 전 교체하세요.")

JWT_ALGORITHM   = "HS256"
JWT_EXPIRE_DAYS = 30


def _create_user_tables():
    """앱 시작 시 users / folders / analysis_history / watchlist 테이블 자동 생성"""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    id            INT AUTO_INCREMENT PRIMARY KEY,
                    email         VARCHAR(255) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    nickname      VARCHAR(100),
                    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            # 기록을 묶어 두는 폴더. analysis_history 가 이 테이블을 참조하므로
            # 먼저 만들어야 한다.
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS folders (
                    id         INT AUTO_INCREMENT PRIMARY KEY,
                    user_id    INT NOT NULL,
                    name       VARCHAR(100) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS analysis_history (
                    id           INT AUTO_INCREMENT PRIMARY KEY,
                    user_id      INT NOT NULL,
                    url          TEXT NOT NULL,
                    product_name VARCHAR(200),
                    company_name VARCHAR(100),
                    verdict      VARCHAR(80),
                    accs_score   FLOAT,
                    risk_level   VARCHAR(30),
                    result_json  LONGTEXT,
                    folder_id    INT NULL,
                    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE SET NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    id           INT AUTO_INCREMENT PRIMARY KEY,
                    user_id      INT NOT NULL,
                    url          TEXT NOT NULL,
                    product_name VARCHAR(200),
                    added_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """))
        print("[DB] users / folders / analysis_history / watchlist tables ready")
    except Exception as e:
        print(f"[DB] table creation skipped: {e}")

    _ensure_folder_id_column()


def _ensure_folder_id_column():
    """
    `CREATE TABLE IF NOT EXISTS` 는 이미 있는 테이블을 건드리지 않는다.
    folders 를 나중에 추가한 배포본에는 analysis_history 가 이미 folder_id
    없이 존재하므로, 컬럼이 없을 때만 직접 ALTER 한다.
    """
    try:
        with engine.begin() as conn:
            exists = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = 'analysis_history'
                  AND column_name = 'folder_id'
            """)).scalar()
            if not exists:
                conn.execute(text(
                    "ALTER TABLE analysis_history ADD COLUMN folder_id INT NULL"
                ))
                conn.execute(text("""
                    ALTER TABLE analysis_history
                    ADD CONSTRAINT fk_analysis_history_folder
                    FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE SET NULL
                """))
                print("[DB] analysis_history.folder_id added")
    except Exception as e:
        print(f"[DB] folder_id migration skipped: {e}")


_create_user_tables()

# ══════════════════════════════════════════
# 요청 모델
# ══════════════════════════════════════════
class AnalyzeRequest(BaseModel):
    url: str

class RegisterRequest(BaseModel):
    email:    str
    password: str
    nickname: str = ""

class LoginRequest(BaseModel):
    email:    str
    password: str

class WatchlistRequest(BaseModel):
    url:          str
    product_name: str = ""

class CompareRequest(BaseModel):
    ids: list[int]

class FolderRequest(BaseModel):
    name: str

class MoveHistoryRequest(BaseModel):
    folder_id: Optional[int] = None

# ══════════════════════════════════════════
# 유틸 함수 (기존 로직 유지)
# ══════════════════════════════════════════
def load_whitelist(filename: str) -> list[str]:
    base = os.path.dirname(os.path.abspath(__file__))
    for path in [os.path.join(base, filename), os.path.join(base, 'logic', filename), filename]:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
    return []

def check_jodale_mall(model_name: str) -> dict:
    import requests as req
    if not DATA_GO_KR_KEY or not model_name:
        return {"status": "스킵", "spec": "", "cert": ""}
    url = "http://apis.data.go.kr/1230000/ShoppingMallPrdInfoService03/getManufacturerItemInfo02"
    params = {'serviceKey': DATA_GO_KR_KEY, 'type': 'json', 'modelNm': model_name, 'numOfRows': '1', 'pageNo': '1'}
    try:
        res = req.get(url, params=params, timeout=5)
        if res.status_code == 200:
            body = res.json().get('response', {}).get('body', {})
            if body.get('items'):
                item = body['items'][0]
                return {"status": "등록됨", "spec": item.get('cntrctSpec', ''), "cert": item.get('certInfo', '')}
        return {"status": "미등록", "spec": "", "cert": ""}
    except Exception as e:
        return {"status": "에러", "spec": "", "cert": str(e)}

def check_tipa_ai(company_name: str) -> dict:
    import requests as req
    if not DATA_GO_KR_KEY or not company_name or company_name == "미확인":
        return {"status": "스킵", "solution_name": ""}
    url = "http://apis.data.go.kr/1352000/TIPA_MnfctAI_Sol_Sply_Entps_Stat/getMnfctAI_Sol_Sply_Entps_Stat"
    params = {'serviceKey': DATA_GO_KR_KEY, 'type': 'json', 'entpsNm': company_name, 'numOfRows': '1', 'pageNo': '1'}
    try:
        res = req.get(url, params=params, timeout=5)
        if res.status_code == 200:
            body = res.json().get('response', {}).get('body', {})
            if body.get('totalCount', 0) > 0 and body.get('items'):
                item = body['items'][0]
                return {"status": "인증기업", "solution_name": item.get('aiSolNm', '')}
        return {"status": "미등록", "solution_name": ""}
    except Exception as e:
        return {"status": "에러", "solution_name": str(e)}

def check_koraia(company_name: str) -> dict:
    whitelist = load_whitelist("koraia_list.txt")
    if not whitelist:
        return {"status": "목록 없음"}
    return {"status": "인증기업"} if any(c in company_name for c in whitelist) else {"status": "미등록"}

def clean_ocr_text_with_gemini(product_data: dict) -> dict | None:
    ocr_str = product_data.get("ocr_extracted_text", "")
    if not ocr_str.strip():
        return None
    product_name = product_data.get("model_name", "알 수 없는 제품")
    specs_str = json.dumps(product_data.get("specs", {}), ensure_ascii=False)
    system_instruction = (
        "너는 이커머스 상세페이지의 데이터 정제 전문가야. "
        "다음 작업을 수행하고 무조건 JSON 형식으로만 답변해:\n"
        "1. company_name: 제조사/브랜드 이름.\n"
        "2. exact_model_name: 전파인증 검색용 모델명.\n"
        "3. cleaned_text: OCR 텍스트 오타 교정 및 정돈.\n"
        "출력 JSON 키는 company_name, exact_model_name, cleaned_text 세 개만."
    )
    user_prompt = f"[제품명]: {product_name}\n[스펙 표]:\n{specs_str}\n[OCR 텍스트]:\n{ocr_str}"
    try:
        if not gemini_client:
            return None
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"[WARN] Gemini OCR failed: {e}")
        return None

def search_kc_db(norm_info: dict, product_json: dict, has_real_company: bool, target_company_name: str, model_param: str) -> pd.DataFrame:
    try:
        if has_real_company:
            real_names = [n.strip() for n in target_company_name.split(',') if n.strip()]
            real_cores = list(set([n.replace('주식회사', '').replace('(주)', '').strip() for n in real_names]))
            comp_cond = " OR ".join([f"company_name LIKE :c{i}" for i, _ in enumerate(real_cores)])
            params = {f"c{i}": f"%{c}%" for i, c in enumerate(real_cores)}
            with engine.connect() as conn:
                result = pd.read_sql(text(f"SELECT * FROM kc_ai_products WHERE ({comp_cond}) LIMIT 50"), conn, params=params)
            if not result.empty: return result

        model_candidates = [m for m in norm_info.get('extracted_tech_models', []) if '-' in m]
        if is_valid_model_number(model_param) and model_param not in model_candidates:
            model_candidates.insert(0, model_param)
        if model_candidates:
            model_cond = " OR ".join([f"model_name LIKE :m{i}" for i, _ in enumerate(model_candidates)])
            params = {f"m{i}": f"%{m}%" for i, m in enumerate(model_candidates)}
            with engine.connect() as conn:
                result = pd.read_sql(text(f"SELECT * FROM kc_ai_products WHERE ({model_cond}) LIMIT 50"), conn, params=params)
            if not result.empty: return result

        if product_json.get('model_name'):
            kw = product_json['model_name'].split()[0]
            with engine.connect() as conn:
                return pd.read_sql(
                    text("SELECT * FROM kc_ai_products WHERE model_name LIKE :kw OR equip_name LIKE :kw LIMIT 50"),
                    conn, params={"kw": f"%{kw}%"}
                )
    except Exception as e:
        print(f"[WARN] KC DB error: {e}")
    return pd.DataFrame()

def search_cert_db(company_aliases: list[str]) -> pd.DataFrame:
    if not company_aliases: return pd.DataFrame()
    try:
        cond = " OR ".join([f"company_name LIKE :a{i}" for i, _ in enumerate(company_aliases)])
        params = {f"a{i}": f"%{a}%" for i, a in enumerate(company_aliases)}
        with engine.connect() as conn:
            return pd.read_sql(
                text(f"SELECT cert_type, cert_no, product_name, company_name, cert_date, expire_date FROM cert_products WHERE ({cond}) LIMIT 30"),
                conn, params=params
            )
    except Exception as e:
        print(f"[WARN] cert DB error: {e}")
        return pd.DataFrame()

def calc_dim_color(v: float) -> str:
    if v >= 60.0: return "#c8ff4a"
    if v >= 35.0: return "#f0c040"
    return "#ff5d4b"

# ══════════════════════════════════════════
# 인증 헬퍼
# ══════════════════════════════════════════
def hash_password(pw: str) -> str:
    return _bcrypt_lib.hashpw(pw.encode('utf-8'), _bcrypt_lib.gensalt()).decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt_lib.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))

def create_jwt(user_id: int, email: str) -> str:
    from datetime import timedelta
    expire  = datetime.utcnow() + timedelta(days=JWT_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "email": email, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_jwt(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None

def user_from_header(authorization: Optional[str]) -> Optional[dict]:
    """Authorization: Bearer <token> 헤더에서 페이로드 추출. 없거나 만료 시 None 반환."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return decode_jwt(authorization[7:])

# ══════════════════════════════════════════
# 분석 파이프라인 (비동기 스레드 실행)
# ══════════════════════════════════════════
def run_analysis(task_id: str, url: str, user_id: Optional[int] = None):
    def push(step: int, message: str):
        _tasks[task_id]["events"].append({"type": "progress", "step": step, "message": message})

    def fail(message: str):
        _tasks[task_id]["events"].append({"type": "error", "message": message})
        _tasks[task_id]["done"] = True

    try:
        # Step 0: 크롤링
        push(0, "URL 크롤링 및 OCR 처리 중")
        product_json = get_product_data(url)
        if not product_json:
            fail("크롤링 실패 — 다나와 제품 URL을 확인하세요.")
            return

        # Step 1: OCR
        push(1, "이미지 OCR 분석 중")
        image_path = product_json.get("screenshot_path")
        if image_path and os.path.exists(image_path):
            ocr_result = analyze_ai_washing(image_path)
            product_json["ocr_extracted_text"] = ocr_result.get("extracted_text", "")

        # Step 2: Gemini 정제
        push(2, "로컬 AI 텍스트 정제 중")
        if product_json.get("ocr_extracted_text", "").strip():
            cleaned = clean_ocr_text_with_gemini(product_json)
            if cleaned and cleaned.get("cleaned_text"):
                product_json["ocr_extracted_text"] = cleaned["cleaned_text"]

        # Step 3: 정규화 + 제조사 추적
        push(3, "데이터 정규화 및 제조사 추적 중")
        norm_info = normalize_data(product_json)
        raw_brand = norm_info.get("norm_company", "")
        target_company_name = resolve_real_company_name(raw_brand, product_json.get('model_name', ''))
        has_real_company = bool(target_company_name and target_company_name != raw_brand)

        for name in target_company_name.split(','):
            name = name.strip()
            for variant in expand_company_aliases(name):
                if variant not in norm_info['company_aliases']:
                    norm_info['company_aliases'].append(variant)

        company_aliases = norm_info.get('company_aliases', [])
        model_param = norm_info.get('final_norm_model', '')
        api_company = target_company_name.split(',')[0].strip() if target_company_name else raw_brand

        # Step 4: 공공 API + DB + DART 병렬 검색
        push(4, "외부 증거(인증/특허/공시) 병렬 수집 중")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            f_db = executor.submit(search_kc_db, norm_info, product_json, has_real_company, target_company_name, model_param)
            f_jodale = executor.submit(check_jodale_mall, model_param)
            f_tipa = executor.submit(check_tipa_ai, api_company)
            f_koraia = executor.submit(check_koraia, api_company)
            f_dart = executor.submit(check_dart_ai_washing, api_company, model_param) # 🔥 DART 추가
            
            db_results_df = f_db.result()
            jodale_result = f_jodale.result()
            tipa_result = f_tipa.result()
            koraia_result = f_koraia.result()
            dart_result = f_dart.result()

        # Step 5: 특허 + GS 인증
        raw_specs_str = product_json.get('raw_specs', '')
        product_category = raw_specs_str.split('/')[0].strip() if raw_specs_str else ""
        patent_count, patent_items_df, patent_search_type = get_company_patent_data(company_aliases, product_category)
        cert_results_df = search_cert_db(company_aliases)


        # 🧠 Step 6: 온톨로지 기반 최종 분석 엔진 호출 🧠
        push(5, "온톨로지 엔진 기반 AI 주장 신뢰도(ACCS) 산출 중")
        
        ontology_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ontology")
        
        # 엔진 입력용 product_json 재구성
        product_for_ontology = {
            "title": product_json.get('product_name') or product_json.get('model_name'),
            "name": product_json.get('product_name') or product_json.get('model_name'),
            "model_name": model_param,
            "description": product_json.get('description', ''),
            "ocr_text": product_json.get('ocr_extracted_text', ''),
            "specs": product_json.get('specs', {}),
            "raw_specs": product_json.get('raw_specs', ''),
            "category": product_json.get('category', ''),
            "url": url,
            "manufacturer": api_company,
        }

        # DataFrame을 dict list로 변환하여 어댑터에 안전하게 전달
        db_records = db_results_df.to_dict(orient="records") if not db_results_df.empty else []
        cert_records = cert_results_df.to_dict(orient="records") if not cert_results_df.empty else []

        analysis_result = secure_analyze_bundle(
            ontology_dir=ontology_dir,
            product_json=product_for_ontology,
            norm_info=norm_info,
            db_results=db_records,
            # 원본 dict를 전달해 상태·레코드 ID·상세 근거를 보존한다.
            jodale_result=jodale_result,
            tipa_result=tipa_result,
            koraia_result=koraia_result,
            patent_items_df=patent_items_df,
            cert_results=cert_records,
            dart_result=dart_result,
            target_company_name=api_company,
            model_param=model_param,
            ocr_result={
                "extracted_text": product_json.get('ocr_extracted_text', ''),
                "analysis": product_json.get('ocr_analysis', {}),
            },
            weight_predictor=WEIGHT_PREDICTOR,
            product_type=infer_product_type(product_for_ontology),
        )
        weighting = weighting_summary(analysis_result)

        # ACCS, 판정, 위험도와 설명은 엔진 결과를 그대로 사용한다.
        print(
            f"[Analysis] ACCS={analysis_result.accs}, HES={analysis_result.hes}, "
            f"TES={analysis_result.tes}, CES={analysis_result.ces}, "
            f"ECS={analysis_result.ecs}, verdict={analysis_result.verdict}, "
            f"weights={weighting['weights']}, model_version={weighting['model_version']}"
        )

        # 📊 Step 7: 프론트엔드용 JSON 결과 조립
        push(6, "분석 완료 및 결과 반환")

        brand = norm_info.get('raw_company', '미확인')
        prod_name = product_json.get('model_name', '')

        _task_start = _tasks[task_id].get("start_time", datetime.now())
        _task_duration = round((datetime.now() - _task_start).total_seconds(), 1)

        result_payload = {
            "product_name": prod_name[:60] + ('...' if len(prod_name) > 60 else ''),
            "company_name": brand,
            "url": url,
            "timestamp": datetime.now().strftime("%Y.%m.%d %H:%M"),
            "analysis_duration_seconds": _task_duration,
            
            # 🔥 온톨로지 결과 매핑 (프론트엔드 스펙에 맞춤)
            "ontology_scores": {
                "accs": analysis_result.accs,
                "raw_accs": analysis_result.raw_accs,
                "hes": analysis_result.hes,
                "tes": analysis_result.tes,
                "ces": analysis_result.ces,
                "ecs": analysis_result.ecs,
                "conf": analysis_result.conf,
            },
            "ontology_verdict": analysis_result.verdict,
            "ontology_risk_level": analysis_result.risk_level,
            "top_capabilities": analysis_result.top_capabilities,
            # 주장별 원자료. 이전에는 top_capabilities(상위 5개)만 남기고
            # 버렸는데, 대조 뷰는 주장 하나하나가 어느 소스에 걸렸는지를
            # 보여줘야 하므로 전체를 싣는다.
            "capability_scores": analysis_result.capability_scores,
            "ontology_reasons": analysis_result.reasons,
            # 채널 가중치·기여도·모델 버전. result_json 으로 DB 에도 함께 저장된다.
            "weighting": weighting,

            # (기존 UI 호환성을 위한 일부 필드 보존)
            "trust_score": analysis_result.accs / 100, # 0~1 스케일 변환 (색상 바닥용)
            "verdict_cls": "genuine" if "신뢰" in analysis_result.verdict else "washing" if "워싱" in analysis_result.verdict else "uncertain",
            "text_color": calc_dim_color(analysis_result.tes),
            "verify_color": calc_dim_color(analysis_result.hes),
            "relation_color": calc_dim_color(analysis_result.ces),
            
            "patent_count": patent_count,
            "gs_count": len(cert_records),
            "specs": [{"key": k, "value": v} for k, v in product_json.get('specs', {}).items()],
            "_jodale_status": jodale_result.get("status", ""),
            "_tipa_status": tipa_result.get("status", ""),
            "_tipa_solution": tipa_result.get("solution_name", ""),
            "_koraia_status": koraia_result.get("status", ""),
            "_kc_rra_count": len(db_records),   # 로컬 KC/RRA DB 조회 결과
            "_dart_status": dart_result.get("status", "스킵") if dart_result else "스킵",
            "_dart_count": len(dart_result.get("evidence", [])) if dart_result else 0,
            "_category": product_category,
        }

        _tasks[task_id]["events"].append({"type": "result", "data": result_payload})

        # 📝 히스토리 저장 (로그인 사용자에 한해서만)
        if user_id:
            try:
                with engine.begin() as conn:
                    conn.execute(text("""
                        INSERT INTO analysis_history
                            (user_id, url, product_name, company_name,
                             verdict, accs_score, risk_level, result_json)
                        VALUES
                            (:uid, :url, :pname, :cname,
                             :verdict, :accs, :risk, :rjson)
                    """), {
                        "uid":     user_id,
                        "url":     url,
                        "pname":   (result_payload.get("product_name") or "")[:200],
                        "cname":   (result_payload.get("company_name") or "")[:100],
                        "verdict": (result_payload.get("ontology_verdict") or "")[:80],
                        "accs":    float(result_payload.get("ontology_scores", {}).get("accs", 0)),
                        "risk":    (result_payload.get("ontology_risk_level") or "")[:30],
                        "rjson":   json.dumps(result_payload, ensure_ascii=False),
                    })
                print(f"[History] saved (user_id={user_id})")
            except Exception as he:
                print(f"[History] save failed: {he}")

        _tasks[task_id]["done"] = True

    except Exception as e:
        import traceback
        traceback.print_exc()
        _tasks[task_id]["events"].append({"type": "error", "message": f"서버 오류 발생: {str(e)}"})
        _tasks[task_id]["done"] = True

# ══════════════════════════════════════════
# 헬퍼: 제품 아이콘 매핑
# ══════════════════════════════════════════
def icon_from_name(name: str, category: str) -> str:
    text = (name + category).lower()
    if any(k in text for k in ["공기청정기", "air"]): return "Wind"
    if any(k in text for k in ["냉장고", "fridge"]): return "Refrigerator"
    if any(k in text for k in ["tv", "모니터", "디스플레이"]): return "Tv"
    if any(k in text for k in ["로봇청소기", "청소기", "vacuum"]): return "Bot"
    if any(k in text for k in ["스마트폰", "phone", "갤럭시", "아이폰"]): return "Smartphone"
    if any(k in text for k in ["세탁기", "건조기"]): return "WashingMachine"
    if any(k in text for k in ["에어컨", "에어프라이어"]): return "Thermometer"
    return "Package"

# ══════════════════════════════════════════
# 헬퍼: 주장(capability) → 대조 뷰 claim
# ══════════════════════════════════════════

# supporting_sources 에 담기는 키를 화면에 쓰는 이름으로 옮긴다.
# 묶음은 analysis_engine 의 채널 정의와 같다:
#   TES  kipris · dart                          기술 근거
#   HES  kc · rra                               공인 인증
#   CES  tipa · koraia · gs · nep · procurement  기관 이력
SOURCE_LABELS = {
    "kipris":      "KIPRIS 특허",
    "dart":        "DART 전자공시",
    "kc":          "KC 인증",
    "rra":         "RRA 전파인증",
    "tipa":        "TIPA 공급기업",
    "koraia":      "KORAIA 협회",
    "gs":          "GS 인증",
    "nep":         "NEP 인증",
    "procurement": "조달청 등록",
}


def build_claims(capability_scores: list) -> list:
    """
    온톨로지가 이미 계산해 둔 주장별 결과를 프론트의 대조 뷰 모양으로 옮긴다.

    지금까지 이 값은 직렬화 단계에서 통째로 버려졌다. 그래서 화면은 주장이
    몇 건인지까지만 알 뿐 "어느 주장에 근거가 없는가"를 말할 수 없었는데,
    그게 이 서비스의 결론이다.

    판정 기준:
        근거 소스가 하나도 없으면            unsupported
        있으나 필수 요건을 다 못 채웠으면      partial
        있고 필수 요건도 채웠으면            verified
    """
    claims = []
    for i, c in enumerate(capability_scores or []):
        if not isinstance(c, dict):
            continue

        sources = [s for s in (c.get("supporting_sources") or []) if s]
        ratio = float(c.get("required_fulfillment_ratio") or 0.0)

        if not sources:
            status = "unsupported"
        elif ratio >= 1.0:
            status = "verified"
        else:
            status = "partial"

        strong = c.get("matched_strong_patterns") or []
        missing = c.get("missing_required_components") or []

        claims.append({
            "id": c.get("capability_id") or f"claim-{i}",
            "text": c.get("capability_name_ko") or "이름 없는 주장",
            # 페이지에서 실제로 걸린 문구. 없으면 인용을 지어내지 않고 비운다.
            "quote": strong[0] if strong else None,
            "status": status,
            "evidence": [
                {
                    "source": s,
                    "label": SOURCE_LABELS.get(s, s.upper()),
                    "record_id": None,
                }
                for s in sources
            ],
            # 왜 못 붙었는지. 빠진 요건이 곧 이유다.
            "note": " · ".join(missing) if missing else None,
        })
    return claims


def claims_rollup(claims: list) -> dict:
    """주장 목록을 판정별 건수로 접는다. 목록·비교 화면이 같이 쓴다."""
    roll = {"total": 0, "verified": 0, "partial": 0, "missing": 0}
    for c in claims or []:
        roll["total"] += 1
        if c["status"] == "verified":
            roll["verified"] += 1
        elif c["status"] == "partial":
            roll["partial"] += 1
        else:
            roll["missing"] += 1
    return roll


def claims_from_result_json(raw: str) -> list:
    """
    저장된 result_json 에서 주장 목록을 복원한다.

    이 분석 이전에 만들어진 기록에는 capability_scores 가 없다. 그때는 빈
    목록을 돌려주고 화면이 알아서 접는다 — 없는 근거를 지어내지 않는다.
    """
    import json as _json
    try:
        return build_claims(_json.loads(raw or "{}").get("capability_scores", []))
    except Exception:
        # 깨진 행 하나가 목록 전체를 죽이지 않게 한다
        return []


# ══════════════════════════════════════════
# 헬퍼: AI-ESA 결과 → AnalysisResult 변환
# ══════════════════════════════════════════
def build_analysis_result(analysis_id: str, payload: dict) -> dict:
    task = _tasks.get(analysis_id, {})
    if "analysis_duration_seconds" in payload:
        duration = float(payload["analysis_duration_seconds"])
    else:
        start_time = task.get("start_time", datetime.now())
        duration = (datetime.now() - start_time).total_seconds()

    ont = payload.get("ontology_scores", {})
    accs = round(float(ont.get("accs", 50)), 2)
    tes  = round(float(ont.get("tes", 50)), 2)
    hes  = round(float(ont.get("hes", 50)), 2)
    ces  = round(float(ont.get("ces", 50)), 2)
    ecs  = round(float(ont.get("ecs", 0)), 2)
    conf = round(float(ont.get("conf", 0)), 2)

    verdict = payload.get("ontology_verdict", "")
    # 화면 분류도 엔진 판정과 동일하게 유지한다.
    if "신뢰" in verdict:
        overall_label = "양호 구간"
    elif "AI 워싱 상품" in verdict:
        overall_label = "위험 구간"
    elif "워싱 의심" in verdict:
        overall_label = "주의 구간"
    else:
        overall_label = "판정 제외"

    # XAI 근거 — top_capabilities(dict 리스트) 우선 사용, fallback: reasons(str 리스트)
    top_caps = payload.get("top_capabilities", [])
    reasons  = payload.get("ontology_reasons", [])
    xai_findings = []

    if top_caps:
        for i, cap in enumerate(top_caps[:5]):
            if not isinstance(cap, dict):
                continue
            score = cap.get("final_score", 50)
            positive = cap.get("positive_claim", True)
            # positive_claim=True → 주장이 뒷받침됨 → 워싱 위험 낮춤 → down
            # positive_claim=False → 주장 미뒷받침 → 워싱 위험 높임 → up
            direction = "down" if positive else "up"
            impact = int((score - 50) * 0.5) if positive else int((50 - score) * 0.5)
            xai_findings.append({
                "rank": i + 1,
                "title": cap.get("capability_name_ko", f"기능 {i+1}"),
                "description": ", ".join(cap.get("matched_strong_patterns", [])[:3]),
                "impact_percent": impact,
                "direction": direction,
                "category": "washing",
            })
    else:
        for i, r in enumerate(reasons[:5]):
            if isinstance(r, str):
                impact = 15 - i * 5
                xai_findings.append({
                    "rank": i + 1, "title": r, "description": "",
                    "impact_percent": impact,
                    "direction": "up" if impact >= 0 else "down",
                    "category": "washing",
                })

    if not xai_findings:
        xai_findings = [{
            "rank": 1, "title": verdict or "분석 완료",
            "description": "", "impact_percent": 10,
            "direction": "up", "category": "washing",
        }]

    # ── 검증 테이블 ──────────────────────────────────────────────────
    #
    # 각 행에 `source` 를 함께 보낸다. 화면은 이 id 로 설명을 찾는다.
    # 이전에는 프론트가 표시 문자열(`key`)로 설명 사전을 뒤졌는데, 양쪽
    # 문구가 따로 바뀌면서 일곱 행이 전부 어긋나 설명이 통째로 사라져
    # 있었다. 문자열은 흔들리고 id 는 안 흔들린다.
    #
    # 이름은 SOURCE_LABELS 를 그대로 쓴다 — 대조 뷰의 근거 라벨과 같은
    # 말이어야 두 화면이 같은 기록을 다르게 부르지 않는다.
    def intent(status: str) -> str:
        if status in ("등록됨", "인증기업", "공시 실적 검증 완료"): return "ok"
        if status in ("미등록", "미취득", "AI 핵심 역량 미흡 (워싱 의심)"): return "warn"
        return "neutral"

    def shown(status: str) -> str:
        """내부 표기를 화면 말로. `스킵`은 우리가 안 봤다는 뜻이다."""
        s = (status or "").strip()
        return "조회 안 함" if s in ("", "스킵") else s

    kc_rra_count = payload.get("_kc_rra_count", 0)
    dart_count   = payload.get("_dart_count", 0)
    dart_status  = payload.get("_dart_status", "")
    patent_count = payload.get("patent_count", 0)
    gs_count     = payload.get("gs_count", 0)

    verification_rows = [
        # ── 로컬 DB ──────────────────────────────────────────────────
        {"source": "rra", "key": SOURCE_LABELS["rra"],
         "value": f"{kc_rra_count}건 확인" if kc_rra_count > 0 else "미확인",
         "intent": "ok" if kc_rra_count > 0 else "neutral"},
        # ── 공공 API ─────────────────────────────────────────────────
        {"source": "procurement", "key": SOURCE_LABELS["procurement"],
         "value": shown(payload.get("_jodale_status")),
         "intent": intent(payload.get("_jodale_status", ""))},
        {"source": "tipa", "key": SOURCE_LABELS["tipa"],
         "value": shown(payload.get("_tipa_status")),
         "intent": intent(payload.get("_tipa_status", ""))},
        {"source": "koraia", "key": SOURCE_LABELS["koraia"],
         "value": shown(payload.get("_koraia_status")),
         "intent": intent(payload.get("_koraia_status", ""))},
        # ── DART 공시 ────────────────────────────────────────────────
        {"source": "dart", "key": SOURCE_LABELS["dart"],
         "value": f"{dart_count}건 ({dart_status})" if dart_count > 0 else shown(dart_status),
         "intent": "ok" if dart_count > 0 else intent(dart_status)},
        # ── 특허 · 인증 ──────────────────────────────────────────────
        {"source": "kipris", "key": SOURCE_LABELS["kipris"],
         "value": f"{patent_count}건",
         "intent": "ok" if patent_count > 0 else "neutral"},
        # GS 와 NEP 는 한 건수로 함께 세므로 한 줄로 둔다
        {"source": "gs", "key": "GS · NEP 인증",
         "value": f"{gs_count}건",
         "intent": "ok" if gs_count > 0 else "neutral"},
    ]

    prod_name = payload.get("product_name", "")
    category  = payload.get("_category", "")

    return {
        "analysis_id": analysis_id,
        "product": {
            "name": prod_name,
            "manufacturer": payload.get("company_name", ""),
            "source": "danawa",
            "category": category,
            "icon": icon_from_name(prod_name, category),
            "tags": [
                t.get("capability_name_ko", "") if isinstance(t, dict) else str(t)
                for t in payload.get("top_capabilities", [])[:5]
            ],
            "ai_claims_count": len(top_caps) or len(reasons),
            "analysis_duration_seconds": round(duration, 1),
            "analysis_date": datetime.now().date().isoformat(),
        },
        "scores": {
            "overall": accs,
            "overall_label": overall_label,
            "text_credibility": tes,
            "verification_credibility": hes,
            "relational_credibility": ces,
            "ecs": ecs,
            "conf": conf,
        },
        "xai_findings": xai_findings,
        "verification": {"rows": verification_rows},
        # 이 분석 이전에 저장된 기록에는 capability_scores 가 없다.
        # 그때는 빈 배열이 나가고 화면은 대조 뷰를 접는다.
        "claims": build_claims(payload.get("capability_scores", [])),
        # 이 기능 이전에 저장된 기록에는 weighting 이 없다.
        "weighting": payload.get("weighting"),
        "meta": {
            "backend": "real",
            "pipeline_version": "real-v1",
            "model_version": (payload.get("weighting") or {}).get("model_version"),
            "notes": None,
        },
        "created_at": datetime.now().isoformat(),
    }

# ══════════════════════════════════════════
# 스테이지 상수
# ══════════════════════════════════════════
_STAGE_NAMES  = ["crawl", "ocr", "llm_refine", "public_verify", "patent_search", "score"]
_STAGE_LABELS = {
    "crawl": "크롤링", "ocr": "OCR", "llm_refine": "로컬 AI 정제 중",
    "public_verify": "공공 API 검증", "patent_search": "특허·인증 검색", "score": "종합 분석",
}

def _make_progress_event(task_id: str, step: int, done: bool = False) -> dict:
    stages = []
    for i, name in enumerate(_STAGE_NAMES):
        if done or i < step:
            state = "done"
        elif i == step:
            state = "running"
        else:
            state = "wait"
        stages.append({"name": name, "label": _STAGE_LABELS[name], "state": state,
                        "started_at": None, "finished_at": None, "error": None})
    pct = 100 if done else min(int((step / len(_STAGE_NAMES)) * 100), 99)
    return {
        "job_id": task_id,
        "overall_percent": pct,
        "current_stage": _STAGE_NAMES[min(step, len(_STAGE_NAMES) - 1)],
        "stages": stages,
    }

# ══════════════════════════════════════════
# SSE 스트리머 (named events)
# ══════════════════════════════════════════
async def event_stream(task_id: str) -> AsyncGenerator[str, None]:
    sent_idx = 0
    while True:
        task = _tasks.get(task_id)
        if not task:
            yield f"event: error\ndata: {{\"message\":\"task not found\"}}\n\n"
            return
        events = task["events"]
        while sent_idx < len(events):
            ev = events[sent_idx]
            if ev["type"] == "progress":
                pe = _make_progress_event(task_id, ev["step"])
                yield f"event: progress\ndata: {json.dumps(pe, ensure_ascii=False)}\n\n"
            elif ev["type"] == "result":
                pe = _make_progress_event(task_id, len(_STAGE_NAMES), done=True)
                yield f"event: complete\ndata: {json.dumps(pe, ensure_ascii=False)}\n\n"
            elif ev["type"] == "error":
                yield f"event: error\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
            sent_idx += 1
        if task.get("done") and sent_idx >= len(events):
            return
        await asyncio.sleep(0.3)

# ══════════════════════════════════════════
# 라우터
# ══════════════════════════════════════════
@app.get("/")
async def index():
    return {"status": "ok", "message": "Fides API server is running. Frontend: http://localhost:3000"}

@app.post("/api/analyze", status_code=202)
async def analyze(req: AnalyzeRequest, authorization: Optional[str] = Header(None)):
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL이 비어 있습니다.")
    if "danawa.com" not in url:
        raise HTTPException(status_code=400, detail="현재 다나와(danawa.com) URL만 지원합니다.")

    # 로그인 사용자 확인 (비로그인도 분석 가능, 단 히스토리는 미저장)
    req_user = user_from_header(authorization)
    req_user_id: Optional[int] = int(req_user["sub"]) if req_user else None

    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"events": [], "done": False, "start_time": datetime.now()}
    loop = asyncio.get_event_loop()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    loop.run_in_executor(executor, run_analysis, task_id, url, req_user_id)
    return {
        "analysis_id": task_id,
        "status": "queued",
        "progress_url": f"/api/analyze/{task_id}/progress",
        "stream_url": f"/api/analyze/{task_id}/stream",
        "result_url": f"/api/analyze/{task_id}/result",
    }

@app.get("/api/analyze/{analysis_id}/stream")
async def stream_new(analysis_id: str):
    if analysis_id not in _tasks:
        raise HTTPException(status_code=404, detail="task not found")
    return StreamingResponse(
        event_stream(analysis_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.get("/api/analyze/{analysis_id}/progress")
async def progress_snapshot(analysis_id: str):
    if analysis_id not in _tasks:
        raise HTTPException(status_code=404, detail="task not found")
    task = _tasks[analysis_id]
    latest_step = 0
    done = task.get("done", False)
    for ev in task["events"]:
        if ev["type"] == "progress":
            latest_step = ev["step"]
    return _make_progress_event(analysis_id, latest_step, done=done)

@app.get("/api/analyze/{analysis_id}/result")
async def get_result(analysis_id: str):
    if analysis_id not in _tasks:
        raise HTTPException(status_code=404, detail="task not found")
    task = _tasks[analysis_id]
    if not task.get("done"):
        raise HTTPException(status_code=409, detail="분석이 아직 완료되지 않았습니다.")
    for ev in task["events"]:
        if ev["type"] == "result":
            return build_analysis_result(analysis_id, ev["data"])
    raise HTTPException(status_code=500, detail="결과 데이터를 찾을 수 없습니다.")

# 하위 호환 (기존 프론트용)
@app.get("/api/stream/{task_id}")
async def stream_legacy(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="task not found")
    return StreamingResponse(
        event_stream(task_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ══════════════════════════════════════════
# 인증 라우터
# ══════════════════════════════════════════

@app.post("/api/auth/register", status_code=201)
async def register(req: RegisterRequest):
    if not req.email or "@" not in req.email:
        raise HTTPException(400, "유효한 이메일을 입력하세요.")
    if len(req.password) < 6:
        raise HTTPException(400, "비밀번호는 6자 이상이어야 합니다.")
    try:
        with engine.begin() as conn:
            dup = conn.execute(
                text("SELECT id FROM users WHERE email = :e"), {"e": req.email}
            ).fetchone()
            if dup:
                raise HTTPException(400, "이미 사용 중인 이메일입니다.")
            hashed   = hash_password(req.password)
            nickname = req.nickname.strip() or req.email.split("@")[0]
            result   = conn.execute(
                text("INSERT INTO users (email, password_hash, nickname) VALUES (:e, :h, :n)"),
                {"e": req.email, "h": hashed, "n": nickname},
            )
            new_id = result.lastrowid
        token = create_jwt(new_id, req.email)
        return {"token": token, "email": req.email, "nickname": nickname}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"회원가입 실패: {e}")


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, email, password_hash, nickname FROM users WHERE email = :e"),
                {"e": req.email},
            ).fetchone()
        if not row or not verify_password(req.password, row[2]):
            raise HTTPException(401, "이메일 또는 비밀번호가 올바르지 않습니다.")
        token = create_jwt(row[0], row[1])
        return {"token": token, "email": row[1], "nickname": row[3] or row[1].split("@")[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"로그인 실패: {e}")


# ══════════════════════════════════════════
# 히스토리 라우터
# ══════════════════════════════════════════

@app.get("/api/history")
async def get_history(authorization: Optional[str] = Header(None)):
    payload = user_from_header(authorization)
    if not payload:
        raise HTTPException(401, "로그인이 필요합니다.")
    user_id = int(payload["sub"])
    try:
        import json as _json
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, url, product_name, company_name,
                           verdict, accs_score, risk_level, created_at, result_json,
                           folder_id
                    FROM analysis_history
                    WHERE user_id = :uid
                    ORDER BY created_at DESC
                    LIMIT 50
                """),
                {"uid": user_id},
            ).fetchall()

        items = []
        for r in rows:
            # category 와 주장 집계는 별도 컬럼이 없어 result_json 에서 뽑는다.
            # 컬럼을 새로 만들면 기존 행은 어차피 비어 있으므로, 이미 저장된
            # 페이로드를 읽는 편이 마이그레이션 없이 과거 기록까지 살린다.
            category = ""
            try:
                category = _json.loads(r[8] or "{}").get("_category") or ""
            except Exception:
                # 깨진 행 하나가 목록 전체를 죽이지 않게 한다
                pass
            rollup = claims_rollup(claims_from_result_json(r[8]))

            items.append({
                "id":           r[0],
                "url":          r[1],
                "product_name": r[2] or "알 수 없음",
                "company_name": r[3] or "",
                "verdict":      r[4] or "",
                "accs_score":   round(r[5] or 0, 1),
                "risk_level":   r[6] or "",
                "created_at":   r[7].strftime("%Y.%m.%d %H:%M") if r[7] else "",
                "category":     category,
                # 이 분석 이전 기록에는 capability_scores 가 없어 전부 0 이다.
                # 화면은 total 이 0 이면 격자를 접는다.
                "claims": rollup,
                "folder_id": r[9],
            })
        return items
    except Exception as e:
        raise HTTPException(500, f"히스토리 조회 실패: {e}")


@app.get("/api/history/{history_id}")
async def get_history_item(history_id: int, authorization: Optional[str] = Header(None)):
    payload = user_from_header(authorization)
    if not payload:
        raise HTTPException(401, "로그인이 필요합니다.")
    user_id = int(payload["sub"])
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT result_json, url FROM analysis_history WHERE id = :id AND user_id = :uid"),
                {"id": history_id, "uid": user_id},
            ).fetchone()
        if not row:
            raise HTTPException(404, "히스토리를 찾을 수 없습니다.")
        return {"result": json.loads(row[0]), "url": row[1]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"히스토리 조회 실패: {e}")


@app.get("/api/history/{history_id}/result")
async def get_history_result(history_id: int, authorization: Optional[str] = Header(None)):
    payload = user_from_header(authorization)
    if not payload:
        raise HTTPException(401, "로그인이 필요합니다.")
    user_id = int(payload["sub"])
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT result_json FROM analysis_history WHERE id = :id AND user_id = :uid"),
                {"id": history_id, "uid": user_id},
            ).fetchone()
        if not row:
            raise HTTPException(404, "히스토리를 찾을 수 없습니다.")
        raw_payload = json.loads(row[0] or "{}")
        return build_analysis_result(f"history-{history_id}", raw_payload)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"히스토리 결과 조회 실패: {e}")


@app.delete("/api/history/{history_id}", status_code=204)
async def delete_history_item(history_id: int, authorization: Optional[str] = Header(None)):
    payload = user_from_header(authorization)
    if not payload:
        raise HTTPException(401, "로그인이 필요합니다.")
    user_id = int(payload["sub"])
    try:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM analysis_history WHERE id = :id AND user_id = :uid"),
                {"id": history_id, "uid": user_id},
            )
    except Exception as e:
        raise HTTPException(500, f"삭제 실패: {e}")


@app.patch("/api/history/{history_id}/folder")
async def move_history_item(history_id: int, body: MoveHistoryRequest, authorization: Optional[str] = Header(None)):
    payload = user_from_header(authorization)
    if not payload:
        raise HTTPException(401, "로그인이 필요합니다.")
    user_id = int(payload["sub"])
    try:
        with engine.begin() as conn:
            if body.folder_id is not None:
                owns = conn.execute(
                    text("SELECT 1 FROM folders WHERE id = :fid AND user_id = :uid"),
                    {"fid": body.folder_id, "uid": user_id},
                ).fetchone()
                if not owns:
                    raise HTTPException(404, "폴더를 찾을 수 없습니다.")
            result = conn.execute(
                text("UPDATE analysis_history SET folder_id = :fid WHERE id = :id AND user_id = :uid"),
                {"fid": body.folder_id, "id": history_id, "uid": user_id},
            )
            if result.rowcount == 0:
                raise HTTPException(404, "기록을 찾을 수 없습니다.")
        return {"id": history_id, "folder_id": body.folder_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"이동 실패: {e}")


# ══════════════════════════════════════════
# 폴더 라우터
# ══════════════════════════════════════════

@app.get("/api/folders")
async def get_folders(authorization: Optional[str] = Header(None)):
    payload = user_from_header(authorization)
    if not payload:
        raise HTTPException(401, "로그인이 필요합니다.")
    user_id = int(payload["sub"])
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT f.id, f.name, f.created_at, COUNT(h.id)
                    FROM folders f
                    LEFT JOIN analysis_history h ON h.folder_id = f.id
                    WHERE f.user_id = :uid
                    GROUP BY f.id, f.name, f.created_at
                    ORDER BY f.created_at ASC
                """),
                {"uid": user_id},
            ).fetchall()
        return [
            {
                "id":         r[0],
                "name":       r[1],
                "created_at": r[2].strftime("%Y.%m.%d") if r[2] else "",
                "count":      r[3],
            }
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(500, f"폴더 조회 실패: {e}")


@app.post("/api/folders", status_code=201)
async def create_folder(body: FolderRequest, authorization: Optional[str] = Header(None)):
    payload = user_from_header(authorization)
    if not payload:
        raise HTTPException(401, "로그인이 필요합니다.")
    user_id = int(payload["sub"])
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "폴더 이름을 입력해주세요.")
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("INSERT INTO folders (user_id, name) VALUES (:uid, :name)"),
                {"uid": user_id, "name": name},
            )
            new_id = result.lastrowid
        return {"id": new_id, "name": name, "created_at": "", "count": 0}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"폴더 생성 실패: {e}")


@app.patch("/api/folders/{folder_id}")
async def rename_folder(folder_id: int, body: FolderRequest, authorization: Optional[str] = Header(None)):
    payload = user_from_header(authorization)
    if not payload:
        raise HTTPException(401, "로그인이 필요합니다.")
    user_id = int(payload["sub"])
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "폴더 이름을 입력해주세요.")
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("UPDATE folders SET name = :name WHERE id = :id AND user_id = :uid"),
                {"name": name, "id": folder_id, "uid": user_id},
            )
            if result.rowcount == 0:
                raise HTTPException(404, "폴더를 찾을 수 없습니다.")
        return {"id": folder_id, "name": name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"이름 변경 실패: {e}")


@app.delete("/api/folders/{folder_id}", status_code=204)
async def delete_folder(folder_id: int, authorization: Optional[str] = Header(None)):
    payload = user_from_header(authorization)
    if not payload:
        raise HTTPException(401, "로그인이 필요합니다.")
    user_id = int(payload["sub"])
    try:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM folders WHERE id = :id AND user_id = :uid"),
                {"id": folder_id, "uid": user_id},
            )
    except Exception as e:
        raise HTTPException(500, f"폴더 삭제 실패: {e}")


@app.get("/api/watchlist")
async def get_watchlist(authorization: Optional[str] = Header(None)):
    payload = user_from_header(authorization)
    if not payload:
        raise HTTPException(401, "로그인이 필요합니다.")
    user_id = int(payload["sub"])
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT id, url, product_name, added_at FROM watchlist WHERE user_id = :uid ORDER BY added_at DESC"),
                {"uid": user_id},
            ).fetchall()
        return [
            {
                "id":           r[0],
                "url":          r[1],
                "product_name": r[2] or "",
                "added_at":     r[3].strftime("%Y.%m.%d") if r[3] else "",
            }
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(500, f"북마크 조회 실패: {e}")


@app.post("/api/watchlist", status_code=201)
async def add_watchlist(body: WatchlistRequest, authorization: Optional[str] = Header(None)):
    payload = user_from_header(authorization)
    if not payload:
        raise HTTPException(401, "로그인이 필요합니다.")
    user_id = int(payload["sub"])
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("INSERT INTO watchlist (user_id, url, product_name) VALUES (:uid, :url, :name)"),
                {"uid": user_id, "url": body.url, "name": body.product_name},
            )
            new_id = result.lastrowid
        return {"id": new_id, "url": body.url, "product_name": body.product_name, "added_at": ""}
    except Exception as e:
        raise HTTPException(500, f"북마크 추가 실패: {e}")


@app.delete("/api/watchlist/{watchlist_id}", status_code=204)
async def delete_watchlist(watchlist_id: int, authorization: Optional[str] = Header(None)):
    payload = user_from_header(authorization)
    if not payload:
        raise HTTPException(401, "로그인이 필요합니다.")
    user_id = int(payload["sub"])
    try:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM watchlist WHERE id = :id AND user_id = :uid"),
                {"id": watchlist_id, "uid": user_id},
            )
    except Exception as e:
        raise HTTPException(500, f"북마크 삭제 실패: {e}")


@app.post("/api/compare")
async def compare_items(body: CompareRequest, authorization: Optional[str] = Header(None)):
    payload = user_from_header(authorization)
    if not payload:
        raise HTTPException(401, "로그인이 필요합니다.")
    user_id = int(payload["sub"])
    if not body.ids or len(body.ids) > 3:
        raise HTTPException(400, "1~3개 항목을 선택해 주세요.")
    try:
        import json as _json
        results = []
        with engine.connect() as conn:
            for item_id in body.ids:
                row = conn.execute(
                    text("""
                        SELECT id, product_name, company_name, accs_score,
                               verdict, risk_level, result_json, created_at
                        FROM analysis_history
                        WHERE id = :id AND user_id = :uid
                    """),
                    {"id": item_id, "uid": user_id},
                ).fetchone()
                if not row:
                    continue
                scores = {}
                category = ""
                try:
                    rj  = _json.loads(row[6] or "{}")
                    # result_json 은 raw payload — ontology_scores 에 실제 값이 있음
                    ont = rj.get("ontology_scores", {})
                    sc  = rj.get("scores", {})  # mock 결과는 여기에도 있을 수 있음
                    category = rj.get("_category") or ""
                    scores = {
                        "text_credibility":         round(float(ont.get("tes") or sc.get("text_credibility") or 0), 1),
                        "verification_credibility": round(float(ont.get("hes") or sc.get("verification_credibility") or 0), 1),
                        "relational_credibility":   round(float(ont.get("ces") or sc.get("relational_credibility") or 0), 1),
                    }
                except Exception:
                    pass

                # 비교 화면의 결론은 점수 차이가 아니라 "어느 주장이 붙었나"다.
                # 항목이 최대 3개라 주장 목록을 통째로 실어도 응답이 크지 않다.
                claims = claims_from_result_json(row[6])

                results.append({
                    "id":           row[0],
                    "product_name": row[1] or "알 수 없음",
                    "company_name": row[2] or "",
                    "accs_score":   round(float(row[3] or 0), 1),
                    "verdict":      row[4] or "",
                    "risk_level":   row[5] or "",
                    "created_at":   row[7].strftime("%Y.%m.%d") if row[7] else "",
                    "category":     category,
                    "claims":       claims,
                    "claims_rollup": claims_rollup(claims),
                    **scores,
                })
        return {"items": results}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"비교 조회 실패: {e}")


@app.get("/api/dashboard")
async def get_dashboard(authorization: Optional[str] = Header(None)):
    payload = user_from_header(authorization)
    if not payload:
        raise HTTPException(401, "로그인이 필요합니다.")
    user_id = int(payload["sub"])
    try:
        with engine.connect() as conn:
            # 요약 통계
            s = conn.execute(
                text("""
                    SELECT
                        COUNT(*)                                                        AS total,
                        AVG(accs_score)                                                 AS avg_score,
                        SUM(CASE WHEN accs_score >= 60 THEN 1 ELSE 0 END)              AS ok_count,
                        SUM(CASE WHEN accs_score >= 35 AND accs_score < 60 THEN 1 ELSE 0 END) AS warn_count,
                        SUM(CASE WHEN accs_score < 35  THEN 1 ELSE 0 END)              AS danger_count
                    FROM analysis_history
                    WHERE user_id = :uid
                """),
                {"uid": user_id},
            ).fetchone()

            # 회사별 집계 (이름 있는 것만, 최대 10개)
            company_rows = conn.execute(
                text("""
                    SELECT
                        company_name,
                        COUNT(*)        AS cnt,
                        AVG(accs_score) AS avg_score,
                        MIN(accs_score) AS min_score,
                        MAX(accs_score) AS max_score
                    FROM analysis_history
                    WHERE user_id = :uid
                      AND company_name IS NOT NULL
                      AND company_name != ''
                    GROUP BY company_name
                    ORDER BY cnt DESC, avg_score DESC
                    LIMIT 10
                """),
                {"uid": user_id},
            ).fetchall()

            # 최근 5개
            recent_rows = conn.execute(
                text("""
                    SELECT id, url, product_name, company_name,
                           verdict, accs_score, risk_level, created_at
                    FROM analysis_history
                    WHERE user_id = :uid
                    ORDER BY created_at DESC
                    LIMIT 5
                """),
                {"uid": user_id},
            ).fetchall()

        total       = int(s[0] or 0)
        avg_score   = round(float(s[1]), 1) if s[1] is not None else None
        ok_count    = int(s[2] or 0)
        warn_count  = int(s[3] or 0)
        danger_count= int(s[4] or 0)

        return {
            "summary": {
                "total":        total,
                "avg_score":    avg_score,
                "ok_count":     ok_count,
                "warn_count":   warn_count,
                "danger_count": danger_count,
            },
            "by_company": [
                {
                    "company_name": r[0],
                    "count":        int(r[1]),
                    "avg_score":    round(float(r[2]), 1) if r[2] is not None else 0,
                    "min_score":    round(float(r[3]), 1) if r[3] is not None else 0,
                    "max_score":    round(float(r[4]), 1) if r[4] is not None else 0,
                }
                for r in company_rows
            ],
            "recent": [
                {
                    "id":           r[0],
                    "url":          r[1],
                    "product_name": r[2] or "알 수 없음",
                    "company_name": r[3] or "",
                    "verdict":      r[4] or "",
                    "accs_score":   round(float(r[5] or 0), 1),
                    "risk_level":   r[6] or "",
                    "created_at":   r[7].strftime("%Y.%m.%d %H:%M") if r[7] else "",
                }
                for r in recent_rows
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"대시보드 조회 실패: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
