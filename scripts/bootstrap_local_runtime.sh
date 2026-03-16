#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK_DIR="$REPO_ROOT/main/xiaozhi-server"
CONFIG_TEMPLATE="$STACK_DIR/data/.config.yaml.example"

mkdir -p \
  "$STACK_DIR/data" \
  "$STACK_DIR/mysql/data" \
  "$STACK_DIR/uploadfile" \
  "$STACK_DIR/models/SenseVoiceSmall"

if [ ! -f "$STACK_DIR/data/.config.yaml" ]; then
  if [ -f "$CONFIG_TEMPLATE" ]; then
    cp "$CONFIG_TEMPLATE" "$STACK_DIR/data/.config.yaml"
  else
    cat >"$STACK_DIR/data/.config.yaml" <<'EOF'
# 本文件优先级高于 config.yaml。
# 建议至少在这里覆盖 server.websocket 和 vision_explain，
# 保证设备拿到的是你机器的真实局域网地址，而不是 Docker 容器内网地址。
#
# 示例：
# server:
#   websocket: ws://192.168.1.10:8000/xiaozhi/v1/
#   vision_explain: http://192.168.1.10:8003/mcp/vision/explain
EOF
  fi
fi

echo "已初始化本地运行目录："
echo "  $STACK_DIR/data"
echo "  $STACK_DIR/mysql/data"
echo "  $STACK_DIR/uploadfile"
echo "  $STACK_DIR/models/SenseVoiceSmall"
echo

if [ ! -f "$STACK_DIR/models/SenseVoiceSmall/model.pt" ]; then
  cat <<'EOF'
缺少 ASR 本地模型：
  main/xiaozhi-server/models/SenseVoiceSmall/model.pt

当前默认配置使用 FunASR 本地模型，服务端启动前请准备该文件。
如果团队后续改为云 ASR，可以再调整配置与文档。
EOF
else
  echo "已检测到 model.pt，可继续构建和启动。"
fi
