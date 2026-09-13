#!/usr/bin/env python3
"""RRA 모델 매칭 수정(6c742ef) 이후, 그 버그로 겹침 구간에 몰렸던 정상 라벨
제품 102건만 골라 재크롤링한다. 전체 371건을 다시 돌 필요 없이 이 서브셋만
run_full_pipeline() 으로 다시 실행해 evidence_cache/*.json 을 새 RRA 결과로
덮어쓴다 (파일명이 url 해시라 같은 URL 은 자동으로 갱신된다).

이어하기 로직은 run_benchmark.py 와 동일한 방식(처리한 URL 을 파일에 적어
두고 다음 실행에서 건너뜀)을 쓰되, 별도 출석부를 써서 원래 벤치마크 진행
기록(dataset/processed_urls.txt)을 건드리지 않는다.
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline_main import run_full_pipeline

DATASET_DIR = "dataset"
TARGET_FILE = os.path.join(DATASET_DIR, "recrawl_targets.txt")
PROCESSED_FILE = os.path.join(DATASET_DIR, "recrawl_processed.txt")


def load_processed():
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def mark_processed(url):
    with open(PROCESSED_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")


def main():
    with open(TARGET_FILE, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    processed = load_processed()
    total = len(urls)
    print(f"재크롤링 대상 {total}건, 이미 완료 {len(processed)}건 스킵")

    for i, url in enumerate(urls, 1):
        if url in processed:
            print(f"⏩ [{i}/{total}] 이미 완료: {url}")
            continue

        print(f"\n🚀 [{i}/{total}] {url}")
        try:
            run_full_pipeline(url)
            mark_processed(url)
        except Exception as e:
            print(f"🚨 [{i}] 실패: {e}")
            traceback.print_exc()

        if i < total:
            time.sleep(5)

    print("\n재크롤링 완료.")


if __name__ == "__main__":
    main()
