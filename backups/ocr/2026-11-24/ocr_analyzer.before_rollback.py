"""
ocr_analyzer.py — 상세 이미지 OCR 텍스트 추출

crawler.py가 캡처한 상세 이미지에서 텍스트를 추출합니다.
추출된 텍스트는 Gemini 정제 → AI 워싱 클레임 분석에 사용됩니다.

속도 개선 핵심:
- EasyOCR Reader를 전역 캐시로 재사용
- 모듈 import 시점이 아니라 실제 OCR 호출 시점에 Reader를 지연 초기화
- GPU(CUDA) 사용 가능 시 GPU 모드 사용, 실패하면 CPU로 자동 fallback
- 같은 이미지 파일은 OCR 결과 JSON 캐시를 재사용
- 이미지 파일 크기/수정시간이 바뀌면 캐시를 자동 무효화

정확도 유지:
- 기존과 동일하게 한글+영어 OCR 사용
- 기존과 동일하게 흑백 변환 후 청크 단위 OCR 수행
- 기본 chunk_size는 기존과 동일한 2000px 유지
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Tuple

import cv2
import easyocr
import numpy as np


# =====================================================================
# OCR Reader 전역 캐시
# =====================================================================
_READER_CACHE: Dict[str, Tuple[Any, str]] = {}


def _is_cuda_available() -> bool:
    """
    현재 환경에서 PyTorch CUDA 사용 가능 여부를 확인한다.

    EasyOCR은 내부적으로 PyTorch를 사용하므로,
    torch.cuda.is_available()이 True일 때 GPU 모드로 초기화한다.
    torch import 또는 CUDA 확인 과정에서 문제가 생기면 안전하게 CPU로 fallback한다.
    """
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _resolve_use_gpu(use_gpu: Optional[bool] = None) -> bool:
    """
    GPU 사용 여부를 결정한다.

    Args:
        use_gpu:
            - True: GPU 사용 시도
            - False: CPU 강제 사용
            - None: CUDA 사용 가능 여부에 따라 자동 결정
    """
    if use_gpu is None:
        return _is_cuda_available()
    return bool(use_gpu)


def get_ocr_reader(use_gpu: Optional[bool] = None):
    """
    EasyOCR Reader를 필요할 때 한 번만 초기화하고 재사용한다.

    기존 코드처럼 모듈 import 시점에 Reader를 바로 만들면
    서버 시작 또는 파일 import만으로도 OCR 모델 로딩 시간이 발생한다.
    이 함수는 실제 OCR이 필요한 순간에만 Reader를 초기화한다.
    """
    resolved_gpu = _resolve_use_gpu(use_gpu)
    cache_key = "gpu" if resolved_gpu else "cpu"

    if cache_key in _READER_CACHE:
        return _READER_CACHE[cache_key]

    device_name = "GPU(CUDA)" if resolved_gpu else "CPU"

    try:
        print(f"[OCR] EasyOCR Reader 초기화 중... 사용 디바이스: {device_name}")
        reader = easyocr.Reader(["ko", "en"], gpu=resolved_gpu)
        _READER_CACHE[cache_key] = (reader, device_name)
        return _READER_CACHE[cache_key]

    except Exception as e:
        if resolved_gpu:
            print(f"[OCR] GPU 모드 초기화 실패: {e}")
            print("[OCR] CPU 모드로 재시도합니다.")
            reader = easyocr.Reader(["ko", "en"], gpu=False)
            _READER_CACHE["cpu"] = (reader, "CPU(fallback)")
            return _READER_CACHE["cpu"]

        raise


# =====================================================================
# OCR 결과 캐시
# =====================================================================
def _get_image_signature(image_path: str) -> Dict[str, Any]:
    """
    이미지 변경 여부를 판단하기 위한 파일 메타데이터를 만든다.
    같은 경로라도 파일 크기나 수정 시간이 바뀌면 캐시를 사용하지 않는다.
    """
    stat = os.stat(image_path)
    return {
        "image_path": os.path.abspath(image_path),
        "size": int(stat.st_size),
        "mtime": float(stat.st_mtime),
    }


def _get_cache_path(image_path: str) -> str:
    """
    OCR 결과 캐시 파일 경로를 반환한다.
    detail_scan.png 옆에 detail_scan.ocr_cache.json 형태로 저장한다.
    """
    root, _ = os.path.splitext(image_path)
    return f"{root}.ocr_cache.json"


def _load_ocr_cache(image_path: str) -> Optional[Dict[str, Any]]:
    """
    이미지 파일이 변경되지 않았으면 기존 OCR 결과를 반환한다.
    """
    cache_path = _get_cache_path(image_path)

    if not os.path.exists(cache_path):
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)

        current_signature = _get_image_signature(image_path)
        cached_signature = cached.get("image_signature", {})

        if (
            cached_signature.get("image_path") == current_signature["image_path"]
            and int(cached_signature.get("size", -1)) == current_signature["size"]
            and abs(float(cached_signature.get("mtime", -1.0)) - current_signature["mtime"]) < 1e-6
        ):
            result = cached.get("result", {})
            if isinstance(result, dict):
                result["cache_hit"] = True
                result["cache_path"] = cache_path
                return result

    except Exception as e:
        print(f"[OCR Cache] 캐시 읽기 실패, OCR을 다시 수행합니다: {e}")

    return None


def _save_ocr_cache(image_path: str, result: Dict[str, Any]) -> None:
    """
    OCR 결과를 이미지 옆 JSON 파일로 저장한다.
    캐시 저장 실패는 분석 실패로 보지 않고 무시한다.
    """
    cache_path = _get_cache_path(image_path)

    try:
        payload = {
            "image_signature": _get_image_signature(image_path),
            "result": {
                "extracted_text": result.get("extracted_text", ""),
                "ocr_device": result.get("ocr_device", ""),
                "chunk_size": result.get("chunk_size"),
                "chunk_count": result.get("chunk_count"),
            },
        }

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"[OCR Cache] 캐시 저장 실패: {e}")


# =====================================================================
# OCR 분석 함수
# =====================================================================
def analyze_ai_washing(
    image_path: str,
    use_gpu: Optional[bool] = None,
    use_cache: bool = True,
    force_refresh: bool = False,
    chunk_size: int = 2000,
) -> Dict[str, Any]:
    """
    이미지 파일에서 텍스트를 OCR로 추출하여 반환합니다.

    Args:
        image_path:
            분석할 이미지 파일 경로
        use_gpu:
            - None: CUDA 사용 가능 여부에 따라 자동 선택
            - True: GPU 사용 시도
            - False: CPU 강제 사용
        use_cache:
            True이면 같은 이미지에 대해 저장된 OCR 캐시를 재사용한다.
        force_refresh:
            True이면 캐시가 있어도 OCR을 다시 수행한다.
        chunk_size:
            세로 방향 청크 크기(px). 기본값은 기존 코드와 동일한 2000px.

    Returns:
        {
            "extracted_text": str,
            "ocr_device": str,
            "cache_hit": bool,
            "cache_path": str,
            "chunk_size": int,
            "chunk_count": int
        }

        실패 또는 이미지가 없으면 extracted_text는 빈 문자열을 반환합니다.
    """
    if not image_path or not os.path.exists(image_path):
        return {
            "extracted_text": "",
            "ocr_device": "unknown",
            "cache_hit": False,
            "cache_path": "",
            "chunk_size": chunk_size,
            "chunk_count": 0,
        }

    if use_cache and not force_refresh:
        cached_result = _load_ocr_cache(image_path)
        if cached_result is not None:
            print(f"✅ [OCR Cache] 기존 OCR 결과 재사용: {cached_result.get('cache_path', '')}")
            return cached_result

    try:
        reader, ocr_device = get_ocr_reader(use_gpu=use_gpu)
    except Exception as e:
        print(f"❌ OCR Reader 초기화 실패: {e}")
        return {
            "extracted_text": "",
            "ocr_device": "reader_init_failed",
            "cache_hit": False,
            "cache_path": _get_cache_path(image_path),
            "chunk_size": chunk_size,
            "chunk_count": 0,
        }

    print(f" OCR 엔진 가동! (디바이스: {ocr_device}, 흑백 변환 + 청크 분할 스캔...)")

    try:
        # 한글 경로 지원: numpy로 읽어서 CV2로 디코딩
        img_array = np.fromfile(image_path, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        if img is None:
            print("❌ OCR 실패: 이미지를 OpenCV로 디코딩할 수 없습니다.")
            return {
                "extracted_text": "",
                "ocr_device": ocr_device,
                "cache_hit": False,
                "cache_path": _get_cache_path(image_path),
                "chunk_size": chunk_size,
                "chunk_count": 0,
            }

        gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        height = gray_img.shape[0]
        safe_chunk_size = max(500, int(chunk_size or 2000))
        all_texts = []
        chunk_count = 0

        for y in range(0, height, safe_chunk_size):
            chunk = gray_img[y:y + safe_chunk_size, :]
            texts = reader.readtext(chunk, detail=0, paragraph=True)

            if texts:
                all_texts.extend(texts)

            chunk_count += 1
            current_y = min(y + safe_chunk_size, height)
            print(f" 청크 스캔 중... ({y}px ~ {current_y}px) / 총 {height}px")

        result = {
            "extracted_text": " ".join(all_texts),
            "ocr_device": ocr_device,
            "cache_hit": False,
            "cache_path": _get_cache_path(image_path),
            "chunk_size": safe_chunk_size,
            "chunk_count": chunk_count,
        }

        if use_cache:
            _save_ocr_cache(image_path, result)

        return result

    except Exception as e:
        print(f"❌ OCR 실패: {e}")
        return {
            "extracted_text": "",
            "ocr_device": ocr_device,
            "cache_hit": False,
            "cache_path": _get_cache_path(image_path),
            "chunk_size": chunk_size,
            "chunk_count": 0,
        }
