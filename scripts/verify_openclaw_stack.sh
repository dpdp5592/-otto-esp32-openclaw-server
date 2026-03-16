#!/usr/bin/env bash
set -euo pipefail

SERVER_IMAGE="$(docker inspect xiaozhi-esp32-server --format '{{.Config.Image}}' 2>/dev/null || true)"
WEB_IMAGE="$(docker inspect xiaozhi-esp32-server-web --format '{{.Config.Image}}' 2>/dev/null || true)"

echo "server image: ${SERVER_IMAGE:-<missing>}"
echo "web image: ${WEB_IMAGE:-<missing>}"

if [[ "$SERVER_IMAGE" != "xiaozhi-local/server-openclaw:dev" ]]; then
  echo "ERROR: 当前 server 不是本地源码镜像"
  exit 1
fi

if [[ "$WEB_IMAGE" != "xiaozhi-local/web-openclaw:dev" ]]; then
  echo "ERROR: 当前 web 不是本地源码镜像"
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx 'xiaozhi-esp32-server-web'; then
  echo "ERROR: xiaozhi-esp32-server-web 未运行"
  exit 1
fi

PAIR_STRINGS="$(docker exec xiaozhi-esp32-server-web sh -lc "grep -R -o 'OpenClaw配对码\\|openClawPairCode\\|copyPairCode' /usr/share/nginx/html/js 2>/dev/null | sort -u" || true)"

echo
echo "frontend markers:"
echo "${PAIR_STRINGS:-<missing>}"

if [[ -z "${PAIR_STRINGS}" ]]; then
  echo "ERROR: 当前前端产物里没有 OpenClaw 配对码相关功能"
  exit 1
fi

if ! rg -n "fetchOpenClawPairDeviceMap|setPairCode|openClawPairCode|copyPairCode" \
  /home/dp/workspace/otto-esp32-openclaw-server/main/manager-api \
  /home/dp/workspace/otto-esp32-openclaw-server/main/manager-web >/dev/null 2>&1; then
  echo "ERROR: 当前仓库源码里没有完整的 OpenClaw 配对码下发/展示逻辑"
  exit 1
fi

echo
echo "pair devices endpoint:"
curl -s -X POST http://localhost:8003/openclaw/body/v1/pair/devices || true

echo
echo "OK: 当前运行的是本地最新源码镜像，并包含 OpenClaw 配对码前端功能。"
