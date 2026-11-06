#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/projects/EASy_ML"
PYTHON="/home/projects/venv/bin/python"

cd "$PROJECT_DIR"

echo "[1/4] 최신 코드 가져오기"
git fetch origin main
git checkout main
git merge --ff-only origin/main

echo "[2/4] 가상환경 확인"
test -x "$PYTHON" || {
    echo "ERROR: 가상환경 Python을 찾을 수 없습니다."
    exit 1
}

echo "[3/4] 패키지 설치"
"$PYTHON" -m pip install -r requirements.txt

echo "[4/4] Python 문법 확인"
"$PYTHON" -m compileall -q .

echo "배포 완료"