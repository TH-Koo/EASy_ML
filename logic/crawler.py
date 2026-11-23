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
import logging
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
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
    # 상세 이미지를 못 찍은 결과는 다시 크롤링한다. 그대로 쓰면 OCR 이 0자라
    # 광고 이미지 속 AI 문구를 하나도 못 읽는데, 그 상태가 TTL 동안 굳는다.
    if not screenshot_path or not os.path.exists(screenshot_path):
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
    # 외부 리소스 전체 완료 대신 DOM 준비 후 상품 요소를 직접 기다린다.
    options.page_load_strategy = "eager"

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
            driver.implicitly_wait(0)

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
    ]

    WebDriverWait(driver, PAGE_READY_TIMEOUT).until(
        lambda d: any(element.text.strip() for element in
                      d.find_elements(By.CSS_SELECTOR, ", ".join(selectors)))
    )


def _open_product_page(driver, url: str) -> None:
    """접속 실패는 한 번 재시도하며 상품 DOM 준비 여부를 확인한다."""
    for attempt in range(2):
        try:
            try:
                driver.get(url)
            except TimeoutException:
                driver.execute_script("window.stop();")
            _wait_for_initial_page(driver)
            return
        except WebDriverException:
            if attempt == 1:
                raise
            logging.getLogger(__name__).warning("페이지 접속 재시도", exc_info=True)
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
_OLD_DETAIL_SELECTORS = [
    "#detail_content_wrap",
    "#productDescriptionArea",
    ".product_detail_area",
    ".detail_content_wrap",
    ".prod_detail",
    ".product_detail",
]

# 새 화면(React) 상품 페이지의 제조사 제공 상세 이미지.
# 예: 세탁기 pcode=77965100. 위 옛 선택자가 하나도 없고, 이미지는 lazy 로딩에
# 높이 제한(max-height) 상자 안에 접혀 있어 요소 스크린샷으로는 찍히지 않는다.
_NEW_DETAIL_IMAGE_SELECTOR = (
    '#manufacturer-tabpanel-1 img, '
    '[data-testid="ProductDetailSection"] img[src*="catalog-content"]'
)


def _find_detail_area(driver):
    """옛 화면의 상세 영역을 찾는다. 선택자 전체를 한 번에 기다린다.

    예전에는 선택자마다 3초씩 따로 기다려서, 상세 영역이 없는 새 화면
    페이지에서는 아무것도 못 찾은 채 18초를 버렸다.
    """
    combined = ", ".join(_OLD_DETAIL_SELECTORS)
    try:
        WebDriverWait(driver, 3).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, combined)
        )
    except Exception:
        return None
    for selector in _OLD_DETAIL_SELECTORS:
        found = driver.find_elements(By.CSS_SELECTOR, selector)
        if found:
            return found[0]
    return None


# 새 화면 상세 이미지를 이어 붙일 최대 높이(px). OCR 은 2000px 조각마다
# CPU 로 15초 안팎이 걸려, 이미지 28장(3.3만 px)을 다 읽으면 4~5분이 된다.
# 광고의 AI 문구는 앞쪽에 몰려 있다: 세탁기 pcode=77965100 은 앞 30%(약 1만 px)
# 만 읽어도 잡히는 주장 5개와 ACCS 가 전부 읽을 때와 같았다.
DETAIL_MAX_HEIGHT = int(os.getenv("EASY_DETAIL_MAX_HEIGHT", "12000"))


def _new_layout_detail_image_urls(driver) -> List[str]:
    """새 화면의 상세 이미지 주소를 순서대로 모은다. 없으면 빈 목록."""
    try:
        urls = driver.execute_script(
            "return [...document.querySelectorAll(arguments[0])]"
            ".map(i => i.currentSrc || i.src || i.getAttribute('data-src') || '')"
            ".filter(u => u.startsWith('http'));",
            _NEW_DETAIL_IMAGE_SELECTOR,
        ) or []
    except Exception:
        return []
    return list(dict.fromkeys(urls))


def _stitch_detail_images(urls: List[str], out_path: str, referer: str) -> str:
    """상세 이미지를 내려받아 세로로 이어 한 장으로 저장한다.

    요소 스크린샷 대신 원본을 받는 이유: 이어 붙인 높이가 3만 px 를 넘는데,
    headless Chrome 은 그렇게 긴 요소를 한 번에 찍지 못한다.
    """
    import io

    import requests
    from PIL import Image

    target_width = 860
    tiles = []
    total = 0
    for url in urls[:60]:
        if total >= DETAIL_MAX_HEIGHT:
            break
        try:
            res = requests.get(
                url,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0", "Referer": referer},
            )
            res.raise_for_status()
            img = Image.open(io.BytesIO(res.content)).convert("RGB")
        except Exception as e:
            print(f"   상세 이미지 받기 실패: {url[:80]} ({e})")
            continue
        if img.width < 200 or img.height < 50:
            continue  # 아이콘·구분선
        if img.width != target_width:
            img = img.resize((target_width, max(1, round(img.height * target_width / img.width))))
        tiles.append(img)
        total += img.height

    if not tiles:
        return ""
    canvas = Image.new("RGB", (target_width, total), "white")
    y = 0
    for t in tiles:
        canvas.paste(t, (0, y))
        y += t.height
    canvas.save(out_path)
    print(f"[성공] 새 화면 상세 이미지 {len(tiles)}장을 이어 저장: {out_path} ({total}px)")
    return out_path


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
        urls = _new_layout_detail_image_urls(driver)
        if urls:
            try:
                return _stitch_detail_images(urls, screenshot_file, driver.current_url)
            except Exception as e:
                print(f"새 화면 상세 이미지 저장 실패: {e}")
                return ""
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


_NEW_SPEC_TABLE_SELECTOR = '[data-testid="ProductDetailSection"] table'
# 새 화면 상단의 요약 스펙. 옛 spec_list 와 같은 "항목 / 항목 : 값" 모양이다.
_NEW_SPEC_SUMMARY_SELECTOR = '[data-testid="ProductHeader-specs"]'


def _extract_specs(driver) -> Tuple[Dict[str, str], str]:
    """
    다나와 상품 스펙 정보를 수집한다.
    """
    print("[3/3] 스펙 정보 수집 중...")

    specs: Dict[str, str] = {}
    raw_specs = ""

    try:
        # 새 화면(React)은 prod_spec_table 대신 상세 섹션 안의 이름 없는
        # 표에 스펙을 둔다(예: 세탁기 pcode=109483526). 이걸 못 읽으면 스펙이
        # 0개가 돼 "상품 페이지로 보이지 않아요"로 분석이 멈췄다.
        spec_tables = driver.find_elements(By.CLASS_NAME, "prod_spec_table")
        if not spec_tables:
            try:
                spec_tables = WebDriverWait(driver, 5).until(
                    lambda d: d.find_elements(By.CSS_SELECTOR, _NEW_SPEC_TABLE_SELECTOR)
                )
            except Exception:
                spec_tables = []

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
            spec_lists = (driver.find_elements(By.CLASS_NAME, "spec_list")
                          or driver.find_elements(By.CSS_SELECTOR, _NEW_SPEC_SUMMARY_SELECTOR))

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
            summary = driver.find_elements(By.CSS_SELECTOR, _NEW_SPEC_SUMMARY_SELECTOR)
            if summary:
                raw_specs = re.sub(r"\s+", " ", summary[0].text).strip()

        if not raw_specs:
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text
                raw_specs = re.sub(r"\s+", " ", body_text).strip()[:3000]
            except Exception:
                raw_specs = ""

    except Exception as e:
        print(f"스펙 정보 수집 실패: {e}")

    return specs, raw_specs


# 분류 경로 읽는 방식이 바뀔 때 올린다. 이보다 낮은 크롤링 캐시는 다시 수집한다.
# 2: location_wrap(textContent·HTML 원문) + JSON-LD BreadcrumbList
CATEGORY_VERSION = 2


def _breadcrumb_from_jsonld(html: str) -> List[str]:
    """<script type="application/ld+json"> 의 BreadcrumbList 에서 분류 이름을 순서대로 꺼낸다."""
    for raw in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        for node in data if isinstance(data, list) else [data]:
            if not isinstance(node, dict) or node.get("@type") != "BreadcrumbList":
                continue
            items = sorted(node.get("itemListElement") or [], key=lambda x: x.get("position", 0))
            names = [str((it.get("item") or {}).get("name") or it.get("name") or "").strip() for it in items]
            names = [n for n in names if n]
            if names:
                return names
    return []


def _extract_category(driver) -> List[str]:
    """상단 분류 경로(예: 태블릿/모바일/디카 > 이어폰/헤드폰 > 무선 이어폰)를 단계별로 읽는다.

    예전에는 스펙 원문의 첫 토막을 카테고리로 썼는데, 스펙 표가 있는 상품은 원문이
    페이지 본문 전체로 채워져 다나와 상단 메뉴 글자가 카테고리로 들어갔다.
    """
    try:
        buttons = driver.find_elements(By.CSS_SELECTOR, ".location_wrap .loca_item > button.arw")
        # .text 는 화면에 안 보이는 요소에서 빈 문자열을 돌려준다. 서버(EC2)의 headless
        # 창에서는 분류 경로가 접혀 있어 늘 비었으므로 textContent 로 읽는다.
        levels = [
            re.sub(r"\s+", " ", b.get_attribute("textContent") or "").strip()
            for b in buttons
        ]
        levels = [t for t in levels if t and t != "선택하세요"]
        if not levels:
            # 요소를 못 찾으면 HTML 원문에서 같은 자리를 꺼낸다.
            html = driver.page_source or ""
            start = html.find("location_wrap")
            if start >= 0:
                found = re.findall(
                    r'class="loca_item"[^>]*>\s*<button class="arw">([^<]+)<',
                    html[start:start + 80000],
                )
                levels = [t.strip() for t in found if t.strip() and t.strip() != "선택하세요"]
        if not levels:
            # 새 화면 구조의 상품 페이지(예: 세탁기)는 location_wrap 이 없고,
            # 분류 경로를 검색엔진용 JSON-LD BreadcrumbList 로만 싣는다.
            levels = _breadcrumb_from_jsonld(driver.page_source or "")
        print(f"[Category] {' > '.join(levels) if levels else '분류 경로를 찾지 못함'}")
        return levels
    except Exception as e:
        print(f"[Category] 분류 경로 읽기 실패: {e}")
        return []


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
    # 분류 경로 읽는 방식이 바뀌기 전에 만든 캐시는 category 가 없거나 비어 있다.
    # 판정 버전이 지금보다 낮으면 한 번 다시 수집해 채운다.
    if cached_data and cached_data.get("category_version", 0) >= CATEGORY_VERSION:
        return cached_data

    driver = None

    product_data: Dict[str, Any] = {
        "source": "Danawa",
        "url": url,
        "model_name": "",
        "specs": {},
        "raw_specs": "",
        "screenshot_path": "",
        # 분류 경로를 못 찾아도 키는 남겨, 캐시가 매번 다시 수집되지 않게 한다
        "category": "",
        "category_path": "",
        "category_version": CATEGORY_VERSION,
    }

    try:
        driver = _setup_driver()

        print("[1/3] 페이지 접속 및 로딩 중...")
        _open_product_page(driver, url)

        model_name = _extract_product_title(driver)
        product_data["model_name"] = model_name

        print(f"상품명: {model_name}")

        levels = _extract_category(driver)
        if levels:
            product_data["category"] = levels[-1]
            product_data["category_path"] = " > ".join(levels)

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
        logging.getLogger(__name__).exception("상품 크롤링 실패")
        return None

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
