#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/projects/EASy_ML"
PYTHON="/home/projects/.venv/bin/python"

cd "$PROJECT_DIR"

echo "[1/6] 최신 코드 가져오기"
git fetch origin main
git checkout main
git merge --ff-only origin/main

echo "[2/6] Python 가상환경 확인"
test -x "$PYTHON"

echo "[3/6] Python 문법 확인"
"$PYTHON" -m compileall -q \
  -x '(^|/)(node_modules|\.venv|venv|\.git)(/|$)' .

echo "[4/6] 프런트엔드 빌드"
cd "$PROJECT_DIR/frontend"
pnpm install --frozen-lockfile

sudo -n /usr/local/sbin/easy-restart stop

# 빌드가 실패해도 서비스를 다시 시작하도록 처리
trap 'sudo -n /usr/local/sbin/easy-restart start' EXIT

pnpm build


echo "[5/6] 서비스 재시작"
sudo -n /usr/local/sbin/easy-restart start
trap - EXIT

echo "[6/6] 서비스 응답 확인"

"$PYTHON" "$PROJECT_DIR/scripts/check_deployment.py" \
  --frontend-url http://127.0.0.1:3000 \
  --backend-url http://127.0.0.1:8000 \
  --timeout 60

echo "자동 배포 완료"