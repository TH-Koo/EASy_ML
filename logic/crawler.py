"""
crawler.py — 다나와 상품 페이지 크롤러

속도 개선 방향:
- undetected_chromedriver 사용하지 않음
- 일반 Selenium WebDriver만 사용
- 고정 time.sleep()을 WebDriverWait 기반 대기로 최대한 대체
- 상세 이미지 lazy loading 스크롤 시간을 단축하되, 이미지 개수/페이지 높이가 안정화될 때까지 확인
- 동일 URL 재분석 시 선택적으로 크롤링 캐시 사용

정확도 유지 원칙:
- 상세 영역 캡처와 스펙 추출 로직은 유지
- 더보기 버튼 클릭, lazy loading 스크롤, 상세 영역 캡처는 모두 수행
- 캐시는 URL과 스크린샷 파일 존재 여부를 확인하고, TTL 안에서만 재사용
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


# =====================================================================
# 설정값
# =====================================================================
# 같은 URL 재분석 시 Selenium 크롤링 자체를 건너뛰기 위한 캐시.
# 정확도 확인이 중요한 실험에서는 환경변수 EASY_USE_CRAWLER_CACHE=0 으로 끌 수 있다.
USE_CRAWLER_CACHE = os.getenv("EASY_USE_CRAWLER_CACHE", "1").strip().lower() not in {"0", "false", "no", "off"}
CRAWLER_CACHE_TTL_SECONDS = int(os.getenv("EASY_CRAWLER_CACHE_TTL_SECONDS", str(24 * 60 * 60)))

PAGE_READY_TIMEOUT = int(os.getenv("EASY_CRAWLER_PAGE_READY_TIMEOUT", "12"))
DETAIL_READY_TIMEOUT = int(os.getenv("EASY_CRAWLER_DETAIL_READY_TIMEOUT", "8"))


# =====================================================================
# 공통 유틸
# =====================================================================
def _now_ts() -> float:
    return time.time()


def _safe_filename(name: str) -> str:
    """
    Windows 파일명으로 사용할 수 없는 문자를 제거한다.
    """
    safe_name = re.sub(r'[\\/*?:"<>|]', "", str(name or ""))
    safe_name = re.sub(r"\s+", " ", safe_name).strip()

    if not safe_name:
        safe_name = "unknown_product"

    return safe_name


def _extract_pcode_or_hash(url: str) -> str:
    """
    다나와 URL의 pcode를 우선 캐시 키로 사용하고, 없으면 URL 해시를 사용한다.
    """
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        pcode = (query.get("pcode") or [""])[0]
        if pcode:
            return f"pcode_{_safe_filename(pcode)}"
    except Exception:
        pass

    digest = hashlib.sha256(str(url).encode("utf-8")).hexdigest()[:16]
    return f"url_{digest}"


def _cache_dir() -> str:
    path = os.path.join("product_images", "_crawler_cache")
    os.makedirs(path, exist_ok=True)
    return path


def _cache_path_for_url(url: str) -> str:
    return os.path.join(_cache_dir(), f"{_extract_pcode_or_hash(url)}.json")


def _is_cache_valid(cache_data: Dict[str, Any], url: str) -> bool:
    """
    URL, TTL, 스크린샷 파일 존재 여부를 기준으로 캐시 재사용 가능 여부를 판단한다.
    """
    if not isinstance(cache_data, dict):
        return False

    if cache_data.get("url") != url:
        return False

    created_at = float(cache_data.get("created_at", 0) or 0)
    if CRAWLER_CACHE_TTL_SECONDS > 0 and (_now_ts() - created_at) > CRAWLER_CACHE_TTL_SECONDS:
        return False

    screenshot_path = str(cache_data.get("screenshot_path") or "")
    if screenshot_path and not os.path.exists(screenshot_path):
        return False

    return True


def _load_cached_product_data(url: str) -> Optional[Dict[str, Any]]:
    if not USE_CRAWLER_CACHE:
        return None

    path = _cache_path_for_url(url)
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        if not _is_cache_valid(cache_data, url):
            return None

        product_data = cache_data.get("product_data")
        if not isinstance(product_data, dict):
            return None

        print(f"[Crawler Cache] 기존 크롤링 결과 재사용: {path}")
        return product_data

    except Exception as e:
        print(f"[Crawler Cache] 캐시 로드 실패, 새로 크롤링합니다: {e}")
        return None


def _save_cached_product_data(url: str, product_data: Dict[str, Any]) -> None:
    if not USE_CRAWLER_CACHE:
        return

    path = _cache_path_for_url(url)
    cache_data = {
        "url": url,
        "created_at": _now_ts(),
        "created_at_text": time.strftime("%Y-%m-%d %H:%M:%S"),
        "screenshot_path": product_data.get("screenshot_path", ""),
        "product_data": product_data,
    }

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        print(f"[Crawler Cache] 크롤링 결과 저장: {path}")
    except Exception as e:
        print(f"[Crawler Cache] 캐시 저장 실패: {e}")


# =====================================================================
# Chrome WebDriver
# =====================================================================
def _build_chrome_options(headless: bool = True) -> Options:
    """
    Chrome 실행 옵션 생성.
    Selenium 안정성을 유지하면서 이미지 로딩은 보존한다.
    """
    options = Options()

    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ko-KR")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")

    # 크롤링 정확도에 필요한 이미지는 막지 않는다.
    # 불필요한 확장/로그만 줄인다.
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    return options


def _setup_driver():
    """
    Chrome WebDriver 초기화.

    1차: headless 모드
    2차: 일반 창 모드
    """
    last_error = None

    for headless in [True, False]:
        mode_text = "headless" if headless else "normal-window"
        print(f"Chrome 드라이버 초기화 시도: selenium, {mode_text}")

        try:
            options = _build_chrome_options(headless=headless)

            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(60)
            driver.implicitly_wait(2)

            print(f"Chrome 드라이버 초기화 성공: selenium, {mode_text}")
            return driver

        except Exception as e:
            last_error = e
            print(f"Chrome 드라이버 초기화 실패: selenium, {mode_text}")
            print(e)
            time.sleep(1)

    raise last_error


# =====================================================================
# 페이지 로딩 / 상품 정보 추출
# =====================================================================
def _wait_for_initial_page(driver) -> None:
    """
    페이지 접속 직후 상품명 또는 본문이 나타날 때까지만 기다린다.
    기존 고정 5초 대기를 조건부 대기로 대체한다.
    """
    selectors = [
        "h3.prod_tit",
        ".prod_tit",
        "h2.title",
        "h1",
        "body",
    ]

    for selector in selectors:
        try:
            WebDriverWait(driver, PAGE_READY_TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            return
        except Exception:
            continue

    # 완전히 실패해도 뒤 단계에서 driver.title 등을 fallback으로 쓰기 위해 종료하지 않는다.
    time.sleep(1)


def _extract_product_title(driver) -> str:
    """
    다나와 상품명 추출
    """
    title_selectors = [
        "h3.prod_tit",
        ".prod_tit",
        "h2.title",
        "h1",
    ]

    raw_title = ""

    for selector in title_selectors:
        try:
            title_elem = WebDriverWait(driver, 4).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )

            raw_title = title_elem.text.strip()

            if raw_title:
                break

        except Exception:
            continue

    if not raw_title:
        raw_title = driver.title

    raw_title = (
        raw_title.replace("상세정보", "")
        .replace("상품비교", "")
        .replace("Ai 가격비교 Beta", "")
        .replace("AI 가격비교 Beta", "")
        .replace("가격비교", "")
        .replace("다나와", "")
    )

    model_name = re.sub(r"\s+", " ", raw_title).strip()

    if not model_name:
        model_name = "unknown_product"

    return model_name


def _click_more_button_if_exists(driver) -> bool:
    """
    다나와 상세페이지의 '상품정보 더보기' 버튼이 있으면 클릭한다.
    클릭 후에는 상세 영역이 나타날 때까지만 짧게 기다린다.
    """
    xpaths = [
        "//*[contains(text(), '상품정보 더보기')]",
        "//*[contains(text(), '상세정보 더보기')]",
        "//*[contains(text(), '더보기')]",
    ]

    for xpath in xpaths:
        try:
            buttons = driver.find_elements(By.XPATH, xpath)

            if not buttons:
                continue

            for button in buttons:
                try:
                    if not button.is_displayed():
                        continue

                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});",
                        button,
                    )
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", button)

                    print("[더보기] 버튼 클릭 성공")
                    _wait_for_detail_area(driver, timeout=DETAIL_READY_TIMEOUT)
                    return True

                except Exception:
                    continue

        except Exception:
            continue

    print("[더보기] 버튼 없음 또는 클릭 실패")
    return False


def _detail_image_count(driver) -> int:
    """
    상세 영역 내부 이미지 개수를 세어 lazy loading 완료 여부 판단에 사용한다.
    """
    script = """
        return document.querySelectorAll(
            '#detail_content_wrap img, #productDescriptionArea img, .product_detail_area img, .detail_content_wrap img, .prod_detail img, .product_detail img'
        ).length;
    """
    try:
        return int(driver.execute_script(script) or 0)
    except Exception:
        return 0


def _wait_for_detail_area(driver, timeout: int = DETAIL_READY_TIMEOUT) -> bool:
    detail_selectors = [
        "#detail_content_wrap",
        "#productDescriptionArea",
        ".product_detail_area",
        ".detail_content_wrap",
        ".prod_detail",
        ".product_detail",
    ]

    end_time = time.time() + timeout
    while time.time() < end_time:
        for selector in detail_selectors:
            try:
                elems = driver.find_elements(By.CSS_SELECTOR, selector)
                if elems:
                    return True
            except Exception:
                continue
        time.sleep(0.25)

    return False


def _slow_scroll_to_bottom(driver) -> None:
    """
    상세 이미지 lazy loading을 위해 페이지를 스크롤한다.

    기존 방식:
    - 800px씩 이동
    - 매번 1초 대기
    - 높이만 기준으로 종료

    개선 방식:
    - 1000px씩 이동
    - 0.45초 대기
    - 페이지 높이와 상세 이미지 개수가 모두 안정화되면 종료
    - 최대 스크롤 횟수를 둬서 비정상적으로 오래 도는 것을 방지
    """
    print("로딩 짤림 방지: 상세 이미지 로딩 확인 중...")

    last_height = driver.execute_script("return document.body.scrollHeight")
    last_img_count = _detail_image_count(driver)
    stable_count = 0
    max_scroll = 30

    for _ in range(max_scroll):
        driver.execute_script("window.scrollBy(0, 1000);")
        time.sleep(0.45)

        new_height = driver.execute_script("return document.body.scrollHeight")
        new_img_count = _detail_image_count(driver)

        if new_height == last_height and new_img_count == last_img_count:
            stable_count += 1
        else:
            stable_count = 0

        if stable_count >= 2:
            break

        last_height = new_height
        last_img_count = new_img_count

    # 마지막 lazy image가 렌더링되는 시간을 아주 짧게 확보한다.
    time.sleep(0.5)


# =====================================================================
# 상세 영역 캡처 / 스펙 추출
# =====================================================================
def _find_detail_area(driver):
    detail_selectors = [
        "#detail_content_wrap",
        "#productDescriptionArea",
        ".product_detail_area",
        ".detail_content_wrap",
        ".prod_detail",
        ".product_detail",
    ]

    for selector in detail_selectors:
        try:
            detail_area = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )

            if detail_area:
                return detail_area

        except Exception:
            continue

    return None


def _capture_detail_area(driver, model_name: str) -> str:
    """
    다나와 상세 이미지 영역을 찾아 스크린샷으로 저장한다.
    """
    print("[2/3] 마케팅 영역 스캔 중...")

    safe_name = _safe_filename(model_name)

    folder_path = os.path.join("product_images", safe_name)
    os.makedirs(folder_path, exist_ok=True)

    screenshot_file = os.path.join(folder_path, "detail_scan.png")

    detail_area = _find_detail_area(driver)

    if detail_area is None:
        print("[스킵] 상세 이미지 영역을 찾을 수 없습니다.")
        return ""

    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'start'});",
            detail_area,
        )
        time.sleep(0.5)

        area_height = int(detail_area.size.get("height", 0) or 0)
        print(f"타겟 영역 세로 길이: {area_height}px")

        if area_height < 500:
            print("[스킵] 이 상품은 다나와 내부에 제공되는 상세 이미지가 부족합니다.")
            return ""

        detail_area.screenshot(screenshot_file)

        print(f"[성공] 상세페이지 스크린샷 완료: {screenshot_file}")
        return screenshot_file

    except Exception as e:
        print(f"마케팅 영역 캡처 실패: {e}")
        return ""


def _extract_specs(driver) -> Tuple[Dict[str, str], str]:
    """
    다나와 상품 스펙 정보를 수집한다.
    """
    print("[3/3] 스펙 정보 수집 중...")

    specs: Dict[str, str] = {}
    raw_specs = ""

    try:
        spec_tables = driver.find_elements(By.CLASS_NAME, "prod_spec_table")

        if spec_tables:
            rows = spec_tables[0].find_elements(By.TAG_NAME, "tr")

            for row in rows:
                ths = row.find_elements(By.TAG_NAME, "th")
                tds = row.find_elements(By.TAG_NAME, "td")

                for i, th in enumerate(ths):
                    key = th.text.strip()

                    if not key:
                        continue

                    value = "지원"

                    if i < len(tds):
                        value = tds[i].text.strip()

                    specs[key] = value

        if len(specs) < 3:
            spec_lists = driver.find_elements(By.CLASS_NAME, "spec_list")

            if spec_lists:
                raw_specs = re.sub(r"\s+", " ", spec_lists[0].text).strip()

                for item in raw_specs.split(" / "):
                    item = item.strip()

                    if not item:
                        continue

                    if ":" in item:
                        key, value = item.split(":", 1)
                        specs[key.strip()] = value.strip()
                    else:
                        specs[item] = "지원"

        if not raw_specs:
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text
                raw_specs = re.sub(r"\s+", " ", body_text).strip()[:3000]
            except Exception:
                raw_specs = ""

    except Exception as e:
        print(f"스펙 정보 수집 실패: {e}")

    return specs, raw_specs


# =====================================================================
# 공개 함수
# =====================================================================
def get_product_data(url: str) -> Optional[Dict[str, Any]]:
    """
    다나와 상품 URL을 크롤링하여 상품 데이터를 반환한다.

    반환 dict:
    {
        "source": "Danawa",
        "url": url,
        "model_name": 상품명,
        "specs": 스펙 dict,
        "raw_specs": 스펙 원문,
        "screenshot_path": 상세 이미지 스크린샷 경로
    }
    """
    url = str(url or "").strip()

    if "danawa.com" not in url:
        print("다나와 URL이 아니므로 크롤링을 건너뜁니다.")
        return None

    cached_data = _load_cached_product_data(url)
    if cached_data:
        return cached_data

    driver = None

    product_data: Dict[str, Any] = {
        "source": "Danawa",
        "url": url,
        "model_name": "",
        "specs": {},
        "raw_specs": "",
        "screenshot_path": "",
    }

    try:
        driver = _setup_driver()

        print("[1/3] 페이지 접속 및 로딩 중...")
        driver.get(url)
        _wait_for_initial_page(driver)

        model_name = _extract_product_title(driver)
        product_data["model_name"] = model_name

        print(f"상품명: {model_name}")

        _click_more_button_if_exists(driver)
        _slow_scroll_to_bottom(driver)

        screenshot_path = _capture_detail_area(driver, model_name)
        product_data["screenshot_path"] = screenshot_path

        specs, raw_specs = _extract_specs(driver)
        product_data["specs"] = specs
        product_data["raw_specs"] = raw_specs

        print("상품 크롤링 완료")
        _save_cached_product_data(url, product_data)
        return product_data

    except Exception as e:
        print(f"크롤링 오류 발생: {e}")
        return None

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
