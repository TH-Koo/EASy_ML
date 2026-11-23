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

for i in {1..15}; do
    if curl --fail --silent \
        http://127.0.0.1:3000/ -o /dev/null; then
        echo "프런트엔드 정상 실행 확인"
        break
    fi

    if [ "$i" -eq 15 ]; then
        echo "ERROR: 프런트엔드 응답 실패"
        exit 1
    fi

    echo "서버 시작 대기 중... ($i/15)"
    sleep 2
done

echo "자동 배포 완료"