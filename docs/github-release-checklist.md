# GitHub 发布检查单

这份清单面向仓库发布前和同事接手前的最后确认。

## 代码与结构

- 仓库只保留 Otto + OpenClaw 所需核心模块
- 不包含真实数据库、上传文件、日志、缓存和模型权重
- `main/manager-api`、`main/manager-web`、`main/xiaozhi-server` 均在仓库内
- 文档入口是 [README.md](../README.md) 和 [README.md](./README.md)

## 启动路径

- 同事只需要执行 `bash scripts/bootstrap_local_runtime.sh`
- 同事只需要执行 `bash scripts/rebuild_local_docker_stack.sh`
- 本地构建镜像名固定为：
  - `xiaozhi-local/server-openclaw:dev`
  - `xiaozhi-local/web-openclaw:dev`
- 不依赖官方 `ghcr ... latest` 镜像作为运行结果

## OpenClaw 能力

- `xiaozhi-server` 包含 body bridge 与 Otto 身体注册逻辑
- `manager-api` 包含 `pairCode` 下发逻辑
- `manager-web` 包含 `OpenClaw配对码` 展示与复制
- `scripts/verify_openclaw_stack.sh` 可以验证这些关键点

## 配置与运行态

- `main/xiaozhi-server/data/.config.yaml` 由脚本初始化
- 文档明确要求覆盖：
  - `server.websocket`
  - `server.vision_explain`
- 文档明确说明缺少 `models/SenseVoiceSmall/model.pt` 时服务端默认配置无法完整启动

## 发布前自检

依次执行：

```bash
bash scripts/bootstrap_local_runtime.sh
bash scripts/rebuild_local_docker_stack.sh
bash scripts/verify_openclaw_stack.sh
```

预期结果：

- `docker inspect xiaozhi-esp32-server --format '{{.Config.Image}}'` 返回 `xiaozhi-local/server-openclaw:dev`
- `docker inspect xiaozhi-esp32-server-web --format '{{.Config.Image}}'` 返回 `xiaozhi-local/web-openclaw:dev`
- 智控台设备页存在 `OpenClaw配对码` 栏
- Otto 连入后能在 body bridge 中看到 `pair_code`

## 不要做的事

- 不要只执行 `docker restart`
- 不要把 `/opt/xiaozhi-server` 这类本机运行态目录写死进新仓库默认启动方式
- 不要提交真实密钥、真实数据库和本地运行数据
