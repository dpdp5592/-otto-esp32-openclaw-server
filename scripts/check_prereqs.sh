#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK_DIR="$REPO_ROOT/main/xiaozhi-server"
CONFIG_FILE="$STACK_DIR/data/.config.yaml"
MODEL_FILE="$STACK_DIR/models/SenseVoiceSmall/model.pt"

check_command() {
  local cmd="$1"
  local label="$2"
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "OK: $label"
  else
    echo "ERROR: 缺少 $label"
    return 1
  fi
}

check_port_free() {
  local port="$1"
  if ss -ltn "( sport = :$port )" 2>/dev/null | tail -n +2 | grep -q .; then
    echo "WARN: 端口 $port 已被占用"
    ss -ltnp "( sport = :$port )" 2>/dev/null || true
  else
    echo "OK: 端口 $port 可用"
  fi
}

echo "检查基础命令..."
check_command docker "Docker"
check_command ss "ss"

if docker compose version >/dev/null 2>&1; then
  echo "OK: Docker Compose"
else
  echo "ERROR: 缺少 Docker Compose"
  exit 1
fi

echo
echo "检查 Docker 服务..."
if docker info >/dev/null 2>&1; then
  echo "OK: Docker daemon 可访问"
else
  echo "ERROR: Docker daemon 不可访问，请先启动 Docker"
  exit 1
fi

echo
echo "检查本地运行目录..."
mkdir -p \
  "$STACK_DIR/data" \
  "$STACK_DIR/mysql/data" \
  "$STACK_DIR/uploadfile" \
  "$STACK_DIR/models/SenseVoiceSmall"
echo "OK: 本地运行目录已就绪"

echo
echo "检查配置文件..."
if [ -f "$CONFIG_FILE" ]; then
  echo "OK: 已检测到 data/.config.yaml"
else
  echo "WARN: 未检测到 data/.config.yaml"
  echo "      建议先运行: bash scripts/bootstrap_local_runtime.sh"
fi

echo
echo "检查模型文件..."
if [ -f "$MODEL_FILE" ]; then
  echo "OK: 已检测到 SenseVoiceSmall/model.pt"
else
  echo "WARN: 缺少模型文件 $MODEL_FILE"
  echo "      当前默认配置使用 FunASR，本次完整启动大概率会失败"
fi

echo
echo "检查端口..."
check_port_free 8000
check_port_free 8002
check_port_free 8003

echo
echo "检查 Compose 配置..."
(
  cd "$STACK_DIR"
  docker compose -f docker-compose_all.yml -f docker-compose_all.local.yml config >/dev/null
)
echo "OK: Compose 配置可解析"

echo
echo "检查完成。"
echo "推荐下一步："
echo "  1. bash scripts/bootstrap_local_runtime.sh"
echo "  2. 编辑 main/xiaozhi-server/data/.config.yaml"
echo "  3. 准备 main/xiaozhi-server/models/SenseVoiceSmall/model.pt"
echo "  4. bash scripts/rebuild_local_docker_stack.sh"
