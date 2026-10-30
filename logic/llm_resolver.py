"""
llm_resolver.py — 로컬 LLM(Ollama) 및 마스터 맵 기반 엔티티 리졸루션
"""
import os
import json
import requests
import re

# 📂 로컬 캐시 파일 (한번 찾은건 다시 안묻게 저장)
CACHE_FILE = 'llm_company_cache.json'

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_cache(data):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def _ask_local_llm(prompt):
    """내 컴퓨터에서 돌아가는 Ollama 서버(localhost:11434)에 요청을 보냅니다."""
    url = "http://localhost:11434/api/generate"
    data = {
        "model": "gemma2:2b", # 방금 다운로드한 모델
        "prompt": prompt,
        "stream": False
    }
    try:
        # CPU 연산 속도를 고려해 타임아웃을 60초로 넉넉히 설정
        response = requests.post(url, json=data, timeout=60)
        return response.json().get('response', '').strip()
    except Exception as e:
        print(f"   ⚠️ 로컬 LLM 응답 실패: {e}")
        return ""

def _is_hallucinating(text):
    """🚀 [핵심 패치] 로컬 LLM이 헛소리(환각)를 하는지 판별합니다."""
    if not text:
        return True
    
    # 1. 핑계, 안내, 거절 등 LLM 특유의 답변 패턴 단어들 (금지어 대폭 추가)
    hallucination_keywords = [
        "제한적", "확인해야", "제공하는", "인공지능", "ai로서", "알 수 없",
        "지원하지", "미션", "텍스트 기반", "죄송합니다", "불가능", "안내", "알려드",
        "정보가 없", "유통업체", "제조사", "따라서", "추출한 결과",
        "입니다", "출력", "규칙", "명은", "다음과", "회사명", "순서대로"
    ]
    
    text_lower = text.lower()
    if any(hk in text_lower for hk in hallucination_keywords):
        return True
        
    # 2. 회사명/모델명 치고 너무 길면(30자 이상) 정상적인 단답형이 아님
    if len(text) > 30:
        return True
        
    return False

def resolve_real_company_name(brand_name, product_name=""):
    """쇼핑몰 브랜드명을 KIPRIS 검색용 공식 한국 법인명으로 변환합니다."""
    if not brand_name or brand_name in ["미확인", "없음", ""]:
        return brand_name

    # 🎯 [전략 1] 마스터 맵: LG/삼성 등 대기업은 즉시 반환 (API 한도 절약)
    master_map = {
        "LG": "엘지전자,LG전자",
        "LG전자": "엘지전자,LG전자",
        "삼성": "삼성전자",
        "삼성전자": "삼성전자"
    }
    key = brand_name.upper().replace(" ", "")
    if key in master_map:
        return master_map[key]

    # 🎯 [전략 2] 로컬 캐시 확인
    cache = load_cache()
    if brand_name in cache:
        print(f"   🗄️ [캐시 적중] '{brand_name}' -> '{cache[brand_name]}'")
        return cache[brand_name]
    
    # 🎯 [전략 3] 로컬 LLM 분석
    print(f"🧠 [로컬 LLM] '{brand_name}' 법인명 및 별칭 추론 중...")
    
    # 🚀 [패치] 프롬프트를 더욱 강력하고 엄격한 단답형 요구로 변경
    prompt = (
        f"브랜드 '{brand_name}'의 한국 공식 법인명과 영문명을 쉼표로 구분해서 단답형으로 추출해.\n"
        f"주의: '입니다', '출력', '회사명은' 같은 설명이나 문장을 절대 쓰지 마.\n"
        f"출력 예시: 크로스오버, Crossover\n"
        f"출력: "
    )
    result = _ask_local_llm(prompt)

    # 🚀 [안전망 작동] 헛소리 감지 시, LLM 답변을 버리고 원본 브랜드명을 반환
    if _is_hallucinating(result):
        print(f"   ⚠️ [LLM 헛소리/설명충 필터링 작동] 무의미한 응답 제거. 원본 브랜드명 '{brand_name}' 사용.")
        return brand_name

    if result:
        # 🚀 [클렌징 강화] 혹시 모를 줄바꿈 문자 및 마크다운(**, *) 등 완전 제거
        clean_result = result.replace('\n', ' ').replace('**', '').replace('*', '').strip()
        
        # 마지막으로 한 번 더 길이 체크 (마크다운 제거 후)
        if len(clean_result) > 30:
             print(f"   ⚠️ [LLM 길이 초과 필터링] 응답 길이 비정상. 원본 브랜드명 '{brand_name}' 사용.")
             return brand_name

        cache[brand_name] = clean_result
        save_cache(cache)
        print(f"   👉 결과 저장: [{clean_result}]")
        return clean_result

    return brand_name

def resolve_model_name(product_title, specs_text=""):
    """모델번호 추출도 로컬 LLM으로 안전하게 수행합니다."""
    cache_key = f"model_extract_{product_title}" 
    cache = load_cache()
    
    if cache_key in cache:
        print(f"   🗄️ [캐시 적중] 모델명 추출 재사용: '{product_title}' -> '{cache[cache_key]}'")
        return cache[cache_key]

    prompt = (
        f"제품명 '{product_title}'에서 전파인증 검색에 필요한 공식 모델번호만 출력해.\n"
        f"규칙: 부가 설명이나 인사말 없이 모델명 딱 하나만 단답형으로 출력해.\n"
        f"출력: "
    )
    result = _ask_local_llm(prompt)
    
    if _is_hallucinating(result):
        print(f"   ⚠️ [LLM 헛소리 필터링 작동] 모델명 추출 실패. 기본 정규화 로직으로 대체합니다.")
        return ""
        
    clean_result = result.replace('\n', '').replace('**', '').replace('*', '').strip()
    
    if clean_result:
        cache[cache_key] = clean_result
        save_cache(cache)
        print(f"   👉 결과 저장: [{clean_result}]")
        
    return clean_result