#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/projects/EASy_ML"
cd "$PROJECT_DIR"

echo "[1/4] 최신 코드 가져오기"
git fetch origin main
git checkout main
git merge --ff-only origin/main

echo "[2/4] 가상환경 확인"
test -f .venv/bin/python

echo "[3/4] 패키지 설치"
.venv/bin/python -m pip install -r requirements.txt

echo "[4/4] Python 문법 확인"
.venv/bin/python -m compileall -q .

echo "배포 완료"
