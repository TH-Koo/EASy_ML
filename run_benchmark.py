import pandas as pd
import time
import sys
import traceback
import os

from pipeline_main import run_full_pipeline

DATASET_DIR = "dataset"
os.makedirs(DATASET_DIR, exist_ok=True)

PROCESSED_FILE = os.path.join(DATASET_DIR, "processed_urls.txt")

def load_processed_urls():
    """진행 상황을 불러옵니다."""
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def mark_as_processed(url):
    """분석이 끝난 URL을 출석부에 기록합니다."""
    with open(PROCESSED_FILE, 'a', encoding='utf-8') as f:
        f.write(url + '\n')

def run_benchmark_automation(csv_file_path):
    print("\n" + "="*85)
    print(f"📊 [EASy] 벤치마크 데이터셋 '{csv_file_path}' 자동 검증 가동 (이어하기 모드)")
    print("="*85)
    
    try:
        df = pd.read_csv(csv_file_path, encoding='utf-8-sig')
    except UnicodeDecodeError:
        df = pd.read_csv(csv_file_path, encoding='cp949')
    except Exception as e:
        print(f"❌ CSV 파일을 읽는 중 오류가 발생했습니다: {e}")
        return

    if '주소' not in df.columns:
        print("❌ CSV 파일에 '주소' 열(Column)이 없습니다. 파일 형식을 확인해주세요.")
        return

    urls = df['주소'].dropna().tolist()
    total_urls = len(urls)
    
    processed_urls = load_processed_urls()
    remaining_count = total_urls - len(processed_urls)
    
    print(f"✅ 총 {total_urls}개의 타겟 중, 이미 완료된 {len(processed_urls)}개를 건너뛰고 남은 {remaining_count}개를 분석합니다!\n")
    print("="*85)

    for i, url in enumerate(urls, 1):
        if url in processed_urls:
            print(f"⏩ [{i}/{total_urls}] 이미 분석 완료된 URL입니다. 스킵: {url}")
            continue
            
        print(f"\n🚀 [전체 진행률: {i}/{total_urls}] ============================")
        print(f"👉 타겟 URL: {url}")
        
        try:
            run_full_pipeline(url)
            mark_as_processed(url)
            
        except Exception as e:
            print(f"\n🚨 [{i}번째 상품 분석 중 치명적 에러 발생]")
            print(f"원인: {e}")
            traceback.print_exc()
            print("👉 에러를 무시하고 다음 상품으로 넘어갑니다.\n")
        
        if i < total_urls:
            print(f"⏳ 서버 부하 방지를 위해 5초 대기합니다...")
            time.sleep(5)

    print("\n" + "="*85)
    print("🎉 진행률 100%! 모든 벤치마크 URL 분석이 완료되었습니다.")
    print("="*85)

if __name__ == "__main__":
    TARGET_CSV = os.path.join(DATASET_DIR, "test.csv") 
    run_benchmark_automation(TARGET_CSV)