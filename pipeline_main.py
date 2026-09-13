"""
pipeline_main.py — EASy 전체 통합 파이프라인
(판정 텍스트 꼬임 해결, ECS 기준 강화, 조기 종료 및 데이터셋 누적 저장 적용)
"""

import os
import sys
import shutil
import concurrent.futures
import re
import copy
import json
import hashlib
import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from logic.crawler import get_product_data
from logic.ocr_analyzer import analyze_ai_washing
from logic.normalizer import normalize_data
from logic.llm_resolver import resolve_real_company_name, resolve_model_name
from logic.dart_scraper import check_dart_ai_washing
from logic.api import (
    verify_kipris,
    verify_koneps,
    verify_pps_mall,
    verify_nipa_solution,
    verify_kaiac,
    verify_ntis_rnd,
    verify_iitp,
)

from fides_integration import secure_analyze_bundle


# =====================================================================
# DB 연결 및 로컬 검색 엔진
# =====================================================================
_MODEL_FIELD_PATTERN = re.compile(r"(?:단품|본체|세트)?모델명\s*:\s*([A-Za-z0-9][A-Za-z0-9\-]{3,})")

DB_URL = 'mysql+pymysql://admin:fidescapstone@fides-db.cdgw08ugc1uu.ap-northeast-2.rds.amazonaws.com:3306/CapstonDesign'
engine = create_engine(DB_URL, pool_pre_ping=True)


def _spec_table_model(scraped_item: dict) -> str:
    """스펙표에 적힌 규제기관용 모델번호를 꺼낸다 (있으면 LLM 추측보다 우선한다).

    다나와 스펙표는 "갤럭시S26 울트라" 같은 마케팅명과 별개로 "모델명: SM-S948"
    처럼 RRA/KC 인증 DB가 실제로 쓰는 모델번호를 이미 갖고 있는 경우가 많다.
    LLM(resolve_model_name)은 마케팅 제목만 보고 "S26"처럼 짧고 인증 DB에
    존재하지 않는 이름을 지어내는데, 그 값은 4자 미만이라 _model_match 에서
    아예 매칭을 시도하지도 못하고 버려진다. 스펙표에 이미 있는 값을 두고
    지어낼 이유가 없다.
    """
    specs = scraped_item.get("specs") or {}
    if isinstance(specs, dict):
        # "모델명"이 정확히 일치하는 키를 우선하고, 세트/본체/단품 변형은 그 다음.
        priority_keys = [k for k in specs if k == "모델명"]
        other_keys = [k for k in specs if k != "모델명" and "모델명" in k]
        for key in priority_keys + other_keys:
            value = str(specs.get(key, "")).strip()
            if len(value) >= 4:
                return value

    # specs 딕셔너리 파싱 과정에서 이 한 줄만 누락되는 경우가 있었다 (갤럭시
    # Z 폴드7 등): raw_specs 원문에는 "모델명 : SM-F966B"가 그대로 있는데
    # 구조화된 specs 딕셔너리엔 해당 키가 빠져 있었다. 원문에서 직접 찾는다.
    raw_specs = str(scraped_item.get("raw_specs") or "")
    match = _MODEL_FIELD_PATTERN.search(raw_specs)
    if match:
        return match.group(1)
    return ""


def search_kc_db_local(company_aliases, model_name):
    base_model = model_name[:5] if len(model_name) >= 5 else model_name
    clean_aliases = list(set([re.sub(r'\(주\)|주식회사|\s', '', a) for a in company_aliases if a]))

    if not clean_aliases:
        return {'detail': '검색어 없음', 'records': []}

    comp_cond = " OR ".join([
        f"REPLACE(REPLACE(company_name, '(주)', ''), ' ', '') LIKE :c{i}"
        for i in range(len(clean_aliases))
    ])
    params = {f"c{i}": f"%{c}%" for i, c in enumerate(clean_aliases)}

    try:
        with engine.connect() as conn:
            # 회사명만 맞으면 50건 상한 안에서 무작위 순서로 잘렸다. 삼성처럼
            # 인증 건수가 많은 회사는 정작 이 제품의 모델과 일치하는 행이
            # LIMIT 밖으로 밀려나, 무관한 다른 제품 인증만 company_general
            # 근거로 남고 필수 요건(무선 모듈 등)은 영원히 충족되지 못했다.
            # (캐시 388건 중 350건이 이 LIMIT 에 정확히 걸려 있었다.)
            # 모델이 일치하는 행을 항상 먼저 오게 정렬해, 있는데도 잘려
            # 나가는 일을 막는다.
            query = f"""
                SELECT * FROM kc_ai_products
                WHERE ({comp_cond})
                  AND (
                    equip_name REGEXP '무선|통신|센서|비전|스마트|IoT|블루투스|Wi-Fi|제어|AI|인공지능'
                    OR model_name LIKE :model
                  )
                ORDER BY (model_name LIKE :model) DESC
                LIMIT 50
            """
            params['model'] = f"%{base_model}%"
            df = pd.read_sql(text(query), conn, params=params)
            records = df.to_dict(orient="records") if not df.empty else []

            if records:
                return {'detail': f"✅ 로컬 DB에서 RRA 인증 {len(records)}건 확인", 'records': records}
            return {'detail': "❌ DB 매칭 없음 (AI/통신 하드웨어 내역 없음)", 'records': []}

    except Exception as e:
        return {'error': f"DB 오류: {str(e)}", 'records': []}

def search_cert_db_local(company_aliases):
    clean_aliases = list(set([re.sub(r'\(주\)|주식회사|\s', '', a) for a in company_aliases if a]))

    if not clean_aliases:
        return {'detail': '검색어 없음', 'records': []}

    comp_cond = " OR ".join([
        f"REPLACE(REPLACE(company_name, '(주)', ''), ' ', '') LIKE :c{i}"
        for i in range(len(clean_aliases))
    ])
    params = {f"c{i}": f"%{c}%" for i, c in enumerate(clean_aliases)}

    try:
        with engine.connect() as conn:
            query = f"""
                SELECT * FROM cert_products
                WHERE ({comp_cond})
                  AND product_name REGEXP 'AI|인공지능|딥러닝|머신러닝|소프트웨어|플랫폼|알고리즘|제어|스마트홈|인식|비전|음성'
                LIMIT 50
            """
            df = pd.read_sql(text(query), conn, params=params)
            records = df.to_dict(orient="records") if not df.empty else []

            if records:
                return {'detail': f"✅ 로컬 DB에서 인증 {len(records)}건 확인", 'records': records}
            return {'detail': "❌ DB 매칭 없음", 'records': []}

    except Exception as e:
        return {'error': f"DB 오류: {str(e)}", 'records': []}


# =====================================================================
# 데이터셋 자동 누적 저장 로직 (Dataset Accumulator)
# =====================================================================
def save_to_dataset(product_info, scores, final_score, is_ai_product, verdict, risk_level):
    dataset_dir = "dataset"
    os.makedirs(dataset_dir, exist_ok=True)
    csv_filename = os.path.join(dataset_dir, "ai_washing_dataset.csv")
    
    model_name = product_info.get("model", "미확인")
    file_exists = os.path.isfile(csv_filename)

    if file_exists:
        try:
            existing_df = pd.read_csv(csv_filename, encoding='utf-8-sig')
            if model_name in existing_df['모델명'].values:
                print(f"\n⚠️ [DataSave] '{model_name}' 모델은 이미 dataset에 존재하여 누적 저장을 스킵합니다.")
                return
        except Exception as e:
            print(f"CSV 중복 검사 오류 (무시하고 진행): {e}")

    # 점수 임계값을 다시 적용하지 않고 엔진의 최종 판정을 그대로 사용한다.
    if not is_ai_product or "판정 제외" in verdict or "미확인" in verdict:
        label = "일반 상품 (Non-AI)"
    elif "높은 신뢰" in verdict:
        label = "매우 신뢰 (Normal)"
    elif "신뢰 상품" in verdict:
        label = "신뢰 (Normal)"
    elif "워싱 의심" in verdict:
        label = "워싱 의심 (Suspected)"
    else:
        label = "AI 워싱 상품 (Washing)"

    data = {
        "상품카테고리": product_info.get("category", "기타"),
        "법인명(브랜드)": product_info.get("company", "미확인"),
        "모델명": model_name,
        "광고내_AI키워드": "O" if is_ai_product else "X",
        "HW실체성(HES)": scores.get("hes", 0),
        "기술근거성(TES)": scores.get("tes", 0),
        "인증신뢰성(CES)": scores.get("ces", 0),
        "다양성(ECS)": scores.get("ecs", 0),
        "DART_상태": "O" if scores.get("has_dart") else "X",
        "총_신뢰도점수": final_score,
        "최종판정_라벨": label,
        "상세판정": verdict,
        "위험도": risk_level,
        "검증일시": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    df = pd.DataFrame([data])
    df.to_csv(csv_filename, mode='a', index=False, header=not file_exists, encoding='utf-8-sig')
    print(f"\n✅ [DataSave] 분석 결과가 '{csv_filename}'에 누적 저장되었습니다!")

def save_dynamic_weight_log(product_info, analysis_result, url=""):
    """
    analysis_engine.py에서 생성한 동적 가중치 로그를 JSONL로 누적 저장한다.
    """
    dataset_dir = "dataset"
    os.makedirs(dataset_dir, exist_ok=True)
    log_filename = os.path.join(dataset_dir, "analysis_logs.jsonl")

    details = getattr(analysis_result, "details", {}) or {}
    dynamic_weight_log = details.get("dynamic_weight_log")

    if not dynamic_weight_log:
        print("\n [DynamicWeightLog] 저장할 동적 가중치 로그가 없습니다.")
        return

    log_data = {
        "url": url,
        "category": product_info.get("category", "기타"),
        "company": product_info.get("company", "미확인"),
        "model": product_info.get("model", "미확인"),
        "hes": getattr(analysis_result, "hes", 0),
        "tes": getattr(analysis_result, "tes", 0),
        "ces": getattr(analysis_result, "ces", 0),
        "ecs": getattr(analysis_result, "ecs", 0),
        "conf": getattr(analysis_result, "conf", 0),
        "final_accs": getattr(analysis_result, "accs", 0),
        "verdict": getattr(analysis_result, "verdict", ""),
        "risk_level": getattr(analysis_result, "risk_level", ""),
        "dynamic_weight_log": dynamic_weight_log,
        "created_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        with open(log_filename, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_data, ensure_ascii=False) + "\n")
        print(f"\n✅ [DynamicWeightLog] 동적 가중치 로그가 '{log_filename}'에 저장되었습니다!")
    except Exception as e:
        print(f"\n❌ [DynamicWeightLog] 로그 저장 중 오류 발생: {e}")


# =====================================================================
# OCR 결과 캐시 로직
# =====================================================================
def _calculate_file_sha256(file_path, chunk_size=1024 * 1024):
    """
    OCR 대상 이미지의 해시를 계산한다.

    - 같은 이미지이면 OCR 결과를 재사용하기 위한 용도
    - 전체 파일을 읽지만 OCR 연산보다 훨씬 가볍다.
    - 파일이 없거나 읽기 실패하면 빈 문자열을 반환한다.
    """
    if not file_path or not os.path.exists(file_path):
        return ""

    try:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception:
        return ""


def _build_ocr_cache_meta(image_path):
    """
    OCR 캐시 검증용 메타데이터 생성.
    이미지 내용 해시와 파일 크기를 함께 저장하여,
    같은 경로라도 이미지가 바뀌면 캐시를 사용하지 않도록 한다.
    """
    if not image_path or not os.path.exists(image_path):
        return {
            "image_path": image_path or "",
            "image_size": 0,
            "image_sha256": "",
        }

    try:
        return {
            "image_path": os.path.abspath(image_path),
            "image_size": os.path.getsize(image_path),
            "image_sha256": _calculate_file_sha256(image_path),
        }
    except Exception:
        return {
            "image_path": image_path or "",
            "image_size": 0,
            "image_sha256": "",
        }


def _load_ocr_result_cache(image_path, cache_path):
    """
    기존 OCR 결과 JSON을 읽어 재사용 가능한지 확인한다.

    재사용 조건:
    - ocr_result.json 파일 존재
    - extracted_text 필드 존재
    - 저장 당시 이미지 해시와 현재 이미지 해시가 동일

    조건이 맞지 않으면 None을 반환하여 OCR을 새로 수행한다.
    """
    if not cache_path or not os.path.exists(cache_path):
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)

        if not isinstance(cached, dict):
            return None

        if "extracted_text" not in cached:
            return None

        cached_meta = cached.get("_cache_meta", {})
        current_meta = _build_ocr_cache_meta(image_path)

        if not cached_meta:
            return None

        if not current_meta.get("image_sha256"):
            return None

        if cached_meta.get("image_sha256") != current_meta.get("image_sha256"):
            return None

        if cached_meta.get("image_size") != current_meta.get("image_size"):
            return None

        print(f"✅ [OCR Cache] 기존 OCR 결과 재사용: {cache_path}")
        return cached

    except Exception as e:
        print(f"⚠️ [OCR Cache] 캐시 읽기 실패, OCR을 새로 수행합니다: {e}")
        return None


def _save_ocr_result_cache(image_path, cache_path, ocr_result):
    """
    OCR 결과를 JSON으로 저장한다.
    이후 같은 이미지가 들어오면 OCR을 다시 수행하지 않고 캐시를 재사용한다.
    """
    if not cache_path or not isinstance(ocr_result, dict):
        return

    try:
        cached_result = copy.deepcopy(ocr_result)
        cached_result["_cache_meta"] = _build_ocr_cache_meta(image_path)

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cached_result, f, ensure_ascii=False, indent=4)

        print(f"✅ [OCR Cache] OCR 결과 저장 완료: {cache_path}")

    except Exception as e:
        print(f"⚠️ [OCR Cache] OCR 결과 저장 실패: {e}")


# =====================================================================
# 파이프라인 코어 로직
# =====================================================================
def generate_tailored_search_payload(raw_llm_name, scraping_aliases=None):
    base_list = [n.strip() for n in raw_llm_name.split(',')] if ',' in raw_llm_name else [raw_llm_name]

    if scraping_aliases:
        base_list.extend(scraping_aliases)

    base_list = list(set([n for n in base_list if n]))
    payload = {
        "pps_mall": [],
        "local_db": [],
        "kipris": [],
        "dart": [],
        "nipa": [],
        "koneps": [],
    }
    expanded_names = []

    for name in base_list:
        clean_name = re.sub(r'\(주\)|주식회사|\(유\)|㈜', '', name).strip()
        if not clean_name:
            continue

        expanded_names.append(clean_name)
        expanded_names.append(clean_name.upper())
        expanded_names.append(clean_name.lower())

    expanded_names = list(set(expanded_names))

    for clean_name in expanded_names:
        payload["kipris"].append(clean_name)
        payload["local_db"].append(clean_name)
        payload["nipa"].append(clean_name)
        # 나라장터(KONEPS)는 조달몰 검색어와 분리한다.
        # pps_mall은 영문/특수문자 후보를 제외하지만,
        # KONEPS는 회사명 후보를 더 넓게 사용해야 검색 누락이 줄어든다.
        payload["koneps"].append(clean_name)

        if re.search(r'[가-힣]', clean_name):
            payload["dart"].append(clean_name)

        pps_clean = re.sub(r'^주\s*|\s*주$', '', clean_name)
        pps_clean = re.sub(r'[^\w\s가-힣0-9a-zA-Z]', '', pps_clean).strip()

        if re.search(r'[a-zA-Z]', pps_clean):
            continue
        if re.search(r'[가-힣]', pps_clean) and len(pps_clean) > 1:
            payload["pps_mall"].append(pps_clean)

    for key in payload:
        payload[key] = list(set(payload[key]))

    return payload


def _get_valid_api_result(res_dict):
    """Return a usable external-evidence result without dropping real records.

    Some providers return records/evidence with no numeric score.  The old
    implementation discarded those dictionaries because both score fields
    defaulted to 0, which could silently disconnect a working API from ACCS.
    """
    if not res_dict:
        return None

    if not isinstance(res_dict, dict):
        return res_dict

    if res_dict.get("error"):
        return None

    records = res_dict.get("records")
    if isinstance(records, list) and any(isinstance(row, dict) and row for row in records):
        return copy.deepcopy(res_dict)

    evidence = res_dict.get("evidence")
    has_evidence = bool(evidence) if not isinstance(evidence, list) else any(bool(x) for x in evidence)
    if has_evidence:
        return copy.deepcopy(res_dict)

    try:
        score = float(res_dict.get("score", 0) or 0)
        total_score = float(res_dict.get("total_score", 0) or 0)
    except (TypeError, ValueError):
        score = total_score = 0.0

    if score > 0 or total_score > 0:
        return copy.deepcopy(res_dict)

    return None


def _build_patent_items_df(kipris_res):
    """Convert KIPRIS API output to real patent rows for the rule engine."""
    if not isinstance(kipris_res, dict):
        return None

    patent_records = kipris_res.get("records", [])
    if isinstance(patent_records, list):
        clean_records = [row for row in patent_records if isinstance(row, dict) and row]
        if clean_records:
            return pd.DataFrame(clean_records)

    if kipris_res.get("score", 0) > 0 and (kipris_res.get("detail") or kipris_res.get("evidence")):
        kip_text = f"{kipris_res.get('detail', '')} {kipris_res.get('evidence', '')}"
        return pd.DataFrame([{
            "title": "KIPRIS 검색 요약",
            "detail": kip_text,
            "status": "verified",
            "search_type": kipris_res.get("search_type", "legacy_summary"),
        }])

    return None



# 스펙표가 없을 때 raw_specs 가 스펙표 형태인지 판단하는 최소 "key : value" 쌍 수.
# 크롤러는 raw_specs 를 "항목 : 값 / 항목 : 값" 으로 만든다. 상품 페이지가
# 아닌 페이지의 본문에는 이 구조가 나타나지 않는다.
_MIN_SPEC_PAIRS = 3


def _looks_like_product_page(scraped_item: dict) -> bool:
    """수집 결과가 실제 상품 페이지인지 판단한다.

    이전 판정은 "스펙 항목 또는 본문 텍스트가 있으면 통과"였는데, 이것으로는
    거르지 못했다. 다나와 뉴스 페이지는 스펙표가 없는 대신 본문이 3,000자라
    그대로 통과했고, 제품명 "뉴스룸"으로 분석까지 진행돼 ACCS 0 으로 기록됐다.

    캐시 330건을 재보니 실제 상품은 전부 스펙 16항목 이상을 갖고, 스펙이 0인
    것은 그 뉴스 페이지 3건뿐이었다. 그래서 스펙표를 1차 기준으로 쓰되,
    스펙표가 없는 상품 유형을 놓치지 않도록 raw_specs 가 스펙표 형태
    ("항목 : 값")일 때도 통과시킨다. 뉴스 페이지 본문에는 이 쌍이 0개다.
    """
    specs = scraped_item.get("specs") or {}
    if specs:
        return True
    raw_specs = str(scraped_item.get("raw_specs") or "")
    return raw_specs.count(" : ") >= _MIN_SPEC_PAIRS


def _save_evidence_bundle_cache(url: str, bundle_kwargs: dict) -> None:
    """Cache the exact keyword arguments passed to secure_analyze_bundle().

    This lets scoring-logic experiments (e.g. sweeping
    fides_config.EngineConfig.support_combination_power against the labeled
    benchmark) re-run OntologyAnalysisEngine.analyze() against real,
    already-collected evidence without re-crawling or re-calling paid APIs.
    """
    cache_dir = os.path.join("dataset", "evidence_cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, hashlib.sha256(url.encode("utf-8")).hexdigest()[:24] + ".json")

    serializable = dict(bundle_kwargs)
    serializable["ontology_dir"] = str(serializable.get("ontology_dir", ""))
    patent_items_df = serializable.get("patent_items_df")
    if isinstance(patent_items_df, pd.DataFrame):
        serializable["patent_items_df"] = patent_items_df.to_dict(orient="records")

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"url": url, "bundle_kwargs": serializable}, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        print(f"⚠️ [EvidenceCache] 캐시 저장 실패 (무시하고 진행): {e}")


def run_full_pipeline(url: str):
    if not url:
        print("❌ 실행할 URL이 없습니다.")
        return

    print("\n" + "=" * 85)
    print(" [EASy] 실시간 AI 워싱 검증 파이프라인 가동")
    print("=" * 85)

    scraped_item = get_product_data(url)
    if not scraped_item:
        return

    # 상품 페이지가 아닌 것을 받아오는 경우가 있다. 벤치마크에는 제품명이
    # "뉴스룸"이고 스펙도 본문도 비어 있는 수집 결과가 섞여 있었다. 이런
    # 입력은 판정할 대상이 없으므로 무거운 공공데이터 통신을 하기 전에
    # 멈춘다. 스펙과 본문이 모두 비었을 때만 걸러 정상 상품을 놓치지 않는다.
    if not _looks_like_product_page(scraped_item):
        print("\n [중단] 상품 페이지로 보이지 않습니다(스펙·본문 없음). 분석을 건너뜁니다.")
        print(f" 수집된 제목: {scraped_item.get('model_name', '')!r}")
        return

    img_path = scraped_item.get("screenshot_path", "")
    ocr_result = {}
    ocr_text = ""
    is_ai_product = True

    if img_path:
        save_dir = os.path.dirname(img_path) if os.path.dirname(img_path) else "product_images"
        os.makedirs(save_dir, exist_ok=True)
        json_path = os.path.join(save_dir, "ocr_result.json")

        cached_ocr_result = _load_ocr_result_cache(img_path, json_path)

        if cached_ocr_result is not None:
            ocr_result = cached_ocr_result
        else:
            print("⏳ [OCR] 캐시가 없거나 이미지가 변경되어 OCR을 새로 수행합니다.")
            ocr_result = analyze_ai_washing(img_path)
            _save_ocr_result_cache(img_path, json_path, ocr_result)

        ocr_text = ocr_result.get("extracted_text", "")
        is_ai_product = ocr_result.get("is_ai_product", True)

    if not is_ai_product:
        print("\n [조기 종료] 광고 이미지 내 AI/인공지능 키워드가 발견되지 않았습니다.")
        print(" AI 홍보를 하지 않는 일반 상품으로 분류하여 무거운 공공데이터 통신을 스킵합니다.")

        norm_result = normalize_data(scraped_item)
        fast_company = norm_result.get("norm_company", "미확인")
        fast_model = norm_result.get("final_norm_model", "미확인")

        save_to_dataset(
            product_info={
                "category": scraped_item.get("category", ""),
                "company": fast_company,
                "model": fast_model,
            },
            scores={"hes": 0, "tes": 0, "ces": 0, "ecs": 0, "has_dart": False},
            final_score=0,
            is_ai_product=False,
            verdict="분석 스킵 (비 AI 상품)",
            risk_level="없음(일반상품)",
        )
        return

    norm_result = normalize_data(scraped_item)
    official_company = resolve_real_company_name(norm_result.get("raw_company", ""), scraped_item.get("model_name", ""))
    official_model = (
        _spec_table_model(scraped_item)
        or resolve_model_name(scraped_item.get("model_name", ""), ocr_text)
        or norm_result.get("final_norm_model", "미확인")
    )
    product_category = scraped_item.get("category", "") if isinstance(scraped_item.get("category"), str) else ""
    llm_aliases = scraped_item.get("aliases", [])
    search_payload = generate_tailored_search_payload(official_company, llm_aliases)

    print(f"\n 분석 대상: {official_company} / {official_model}")
    print("⏳ 로컬 DB 및 다중 API 통신을 병렬로 진행합니다...\n")

    final_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        dart_target_list = search_payload["dart"] if search_payload["dart"] else [official_company]
        futures = {
            executor.submit(check_dart_ai_washing, dart_target_list, scraped_item.get("model_name")): 'DART',
            executor.submit(verify_kipris, search_payload["kipris"], product_category): 'KIPRIS',   
            executor.submit(search_kc_db_local, search_payload["local_db"], official_model): 'RRA',
            executor.submit(search_cert_db_local, search_payload["local_db"]): 'TTA',
            executor.submit(verify_nipa_solution, search_payload["nipa"]): 'AI공급',
            executor.submit(verify_pps_mall, search_payload["pps_mall"]): '조달몰',
            executor.submit(verify_koneps, search_payload["koneps"]): '나라장터',
            executor.submit(verify_kaiac, search_payload["local_db"]): 'KAIAC',
            executor.submit(verify_ntis_rnd, search_payload["koneps"]): 'NTIS',
            executor.submit(verify_iitp, search_payload["koneps"], product_category): 'IITP',
        }

        for future in concurrent.futures.as_completed(futures):
            final_results[futures[future]] = future.result()

    print("\n 온톨로지 기반 AI Claim Credibility Score(ACCS) 산출 중...")

    ontology_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ontology")
    rra_records = copy.deepcopy(
        final_results.get('RRA', {}).get('records', []) if isinstance(final_results.get('RRA'), dict) else []
    )
    tta_records = copy.deepcopy(
        final_results.get('TTA', {}).get('records', []) if isinstance(final_results.get('TTA'), dict) else []
    )
    kipris_res = final_results.get('KIPRIS', {})

    if isinstance(kipris_res, dict) and kipris_res.get('records'):
        patent_items_df = pd.DataFrame(kipris_res['records'])
    elif isinstance(kipris_res, dict) and (kipris_res.get('detail') or kipris_res.get('evidence')):
        kip_text = f"{kipris_res.get('detail', '')} {kipris_res.get('evidence', '')}"
        patent_items_df = pd.DataFrame([{"title": kip_text}])
    else:
        patent_items_df = None

    analyze_bundle_kwargs = dict(
        ontology_dir=ontology_path,
        product_json={
            # Keep the original Danawa title as claim text; official_model is only
            # the normalized identifier used for matching external evidence.
            "title": scraped_item.get("model_name", ""),
            "name": scraped_item.get("model_name", "") or official_model,
            "description": str(scraped_item.get("description", "")),
            "ocr_text": ocr_text,
            "specs": scraped_item.get("specs", {}),
            "raw_specs": scraped_item.get("raw_specs", ""),
            "category": product_category,
            "url": url,
            "manufacturer": official_company,
            "model_name": official_model,
        },
        norm_info={
            "company_name": official_company,
            "model_name": official_model,
            "product_name": scraped_item.get("model_name", "") or official_model,
        },
        db_results=rra_records,
        jodale_result=(
            _get_valid_api_result(final_results.get('조달몰'))
            or _get_valid_api_result(final_results.get('나라장터'))
        ),
        nipa_result=_get_valid_api_result(final_results.get('AI공급')),
        kaiac_result=_get_valid_api_result(final_results.get('KAIAC')),
        ntis_result=_get_valid_api_result(final_results.get('NTIS')),
        iitp_result=_get_valid_api_result(final_results.get('IITP')),
        patent_items_df=patent_items_df,
        cert_results=tta_records,
        dart_result=_get_valid_api_result(final_results.get('DART')),
        target_company_name=official_company,
        model_param=official_model,
        ocr_result=ocr_result,
    )

    # 재크롤링·재호출 없이 채점 로직만 다시 시험할 수 있도록, 실제로 엔진에
    # 넘긴 근거를 그대로 캐시한다 (scripts/calibrate_thresholds.py 등이 사용).
    _save_evidence_bundle_cache(url, analyze_bundle_kwargs)
    analysis_result = secure_analyze_bundle(**analyze_bundle_kwargs)

    has_dart = bool(_get_valid_api_result(final_results.get('DART')))

    print("\n" + "=" * 85)
    print(" [1] AI 워싱 검증 상세 근거 (Evidence Detail)")
    print("=" * 85)

    print(f"\n [제품 상세페이지 OCR 분석]")
    if ocr_text:
        print(f"└ ✅ 제품 이미지에서 텍스트 추출 완료 (총 {len(ocr_text)}자)")
        snippet = ocr_text.replace('\n', ' ')[:80]
        print(f" 추출 텍스트 요약: {snippet}...")
        if isinstance(ocr_result, dict) and "analysis" in ocr_result:
            claims = ocr_result["analysis"].get("core_claims", [])
            print(f" 식별된 AI 주장(Claims): {', '.join(claims) if claims else '없음'}")
    else:
        print(f"└ ❌ 추출된 OCR 텍스트 없음 (이미지 누락 또는 분석 실패)")

    sources = [
        ('DART 공시 실적', 'DART'),
        ('KIPRIS 특허 실적', 'KIPRIS'),
        ('RRA 전파인증 (로컬DB)', 'RRA'),
        ('TTA/GS 인증 (로컬DB)', 'TTA'),
        ('AI솔루션 공급기업', 'AI공급'),
        ('조달/나라장터', '조달몰'),
        ('한국인공지능인증센터', 'KAIAC'),
        ('NTIS 국가 R&D 실적', 'NTIS'),
        ('IITP 정보통신기획평가원 실적', 'IITP'),
    ]

    for title, key in sources:
        res = final_results.get(key, {})
        print(f"\n [{title} 분석]")
        if isinstance(res, dict):
            if res.get('error'):
                print(f"└ ❌ 에러: {res['error']}")
            else:
                print(f"└ {res.get('detail', '내역 없음')}")

                records = res.get('records', [])
                if records:
                    print(f" 주요 검색 결과:")
                    for i, rec in enumerate(records[:3], 1):
                        name_val = rec.get('발명의명칭(한글)') or rec.get('title') or rec.get('equip_name') or rec.get('product_name') or rec.get('model_name') or '확인된 실적'
                        
                        cert_type = rec.get('cert_type') or rec.get('인증종류') or rec.get('type', '')
                        cert_mark = f"[{cert_type}] " if cert_type else ""
                        
                        print(f" {i}. {cert_mark}{name_val}")
                        
                evidence = res.get('evidence', [])
                if evidence:
                    print(f" 주요 실적 내역:")
                    if isinstance(evidence, str):
                        print(f" - {evidence}")
                    elif isinstance(evidence, list):
                        for i, ev in enumerate(evidence[:3], 1):
                            print(f" {i}. {ev}")

    print("\n" + "=" * 85)
    print(" [2] 온톨로지 기반 AI 신뢰도 종합 보고서")
    print("=" * 85)
    print(f" 타겟 법인: {official_company} | 제품/모델: {official_model}")
    print("-" * 85)
    print("\n[지표별 점수 (100점 만점 기준)]")
    print(f"▶ HES (하드웨어 실체성): {analysis_result.hes:05.2f}점")
    print(f"▶ TES (기술적 근거성) : {analysis_result.tes:05.2f}점")
    print(f"▶ CES (인증/공공 신뢰성): {analysis_result.ces:05.2f}점")
    print(f"▶ ECS (근거 채널 다양성): {analysis_result.ecs:05.2f}점")
    print(f"▶ CONF (분석 신뢰도) : {analysis_result.conf:05.2f}점")
    print("-" * 85)
    print(f"⭐ 최종 AI 주장 신뢰도 (ACCS) : {analysis_result.accs:05.2f} / 100 점")

    verdict_icon = "🟢" if "신뢰" in analysis_result.verdict else "🟡" if "검토" in analysis_result.verdict else "🔴"
    print(f"{verdict_icon} 최종 판정 : {analysis_result.verdict} (위험도: {analysis_result.risk_level})")

    for reason in analysis_result.reasons:
        print(f" - {reason}")

    print("=" * 85 + "\n")

    product_info_for_save = {
        "category": product_category,
        "company": official_company,
        "model": official_model,
    }

    save_dynamic_weight_log(
        product_info=product_info_for_save,
        analysis_result=analysis_result,
        url=url,
    )

    save_to_dataset(
        product_info=product_info_for_save,
        scores={
            "hes": analysis_result.hes,
            "tes": analysis_result.tes,
            "ces": analysis_result.ces,
            "ecs": analysis_result.ecs,
            "has_dart": bool(has_dart),
        },
        final_score=analysis_result.accs,
        is_ai_product=is_ai_product,
        verdict=analysis_result.verdict,
        risk_level=analysis_result.risk_level,
    )

    return analysis_result


if __name__ == "__main__":
    target_url = "https://prod.danawa.com/info/?pcode=122626369"
    run_full_pipeline(target_url)