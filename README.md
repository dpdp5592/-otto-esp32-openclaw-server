# otto-esp32-openclaw-server

本仓库是从 `xiaozhi-esp32-server` 裁剪出的 Otto + OpenClaw 专用项目子集。

目标很明确：

- 保留 Otto + OpenClaw 链路真正需要的源码
- 保留当前项目需要的核心文档
- 去掉与你本机强绑定的运行态数据、大模型文件和无关模块
- 使协作者在 `git clone` 后可按固定脚本启动，并默认运行该仓库中的最新 OpenClaw 网关代码

## 项目结构

- `main/xiaozhi-server`
  - Python 设备服务端
  - OpenClaw body bridge
  - Otto 身体注册与配对码逻辑
- `main/manager-api`
  - 智控台后端
  - OpenClaw 配对码下发逻辑
- `main/manager-web`
  - 智控台前端
  - `OpenClaw配对码` 展示与复制
- `docs/`
  - Otto/OpenClaw 方案、部署、迁移、联调文档
- `scripts/`
  - 本地运行目录初始化与 Docker 重建脚本

## 标准启动路径

### 1. 安装基础依赖

至少需要：

- Docker / Docker Compose
- Git

如果需要本地编译验证，建议额外安装：

- JDK 21
- Maven
- Node.js 18+

### 2. 初始化本地运行目录

```bash
cd /path/to/otto-esp32-openclaw-server
bash scripts/check_prereqs.sh
bash scripts/bootstrap_local_runtime.sh
```

这一步会创建：

- `main/xiaozhi-server/data`
- `main/xiaozhi-server/mysql/data`
- `main/xiaozhi-server/uploadfile`
- `main/xiaozhi-server/models/SenseVoiceSmall`

并生成以下可编辑文件：

- `main/xiaozhi-server/data/.config.yaml`
- 来源模板：`main/xiaozhi-server/data/.config.yaml.example`

### 3. 准备必要模型文件

当前默认配置仍使用 FunASR 本地模型，因此至少需要准备：

- `main/xiaozhi-server/models/SenseVoiceSmall/model.pt`

如果缺少该文件，服务端大概率无法按当前默认配置正常启动。

模型下载方式可参考 [Deployment_all.md](docs/Deployment_all.md) 中的 `SenseVoiceSmall` 说明。

### 4. 覆盖设备真正要拿到的地址

`main/xiaozhi-server/data/.config.yaml` 至少应覆盖：

```yaml
server:
  websocket: ws://<你的局域网IP>:8000/xiaozhi/v1/
  vision_explain: http://<你的局域网IP>:8003/mcp/vision/explain
```

这样可以避免设备拿到 Docker 容器内网地址。

### 5. 启动本地源码镜像

```bash
bash scripts/rebuild_local_docker_stack.sh
```

启动后默认端口：

- `8000` 设备 WebSocket
- `8002` 智控台
- `8003` body bridge / manager-api 内嵌接口

首次启动会拉起四个容器：

- `xiaozhi-esp32-server-db`
- `xiaozhi-esp32-server-redis`
- `xiaozhi-esp32-server`
- `xiaozhi-esp32-server-web`

不应使用 `docker restart` 代替这条命令。

只要源码有改动，就应重新执行：

```bash
bash scripts/rebuild_local_docker_stack.sh
```

这样才能保证运行中的镜像始终来自当前仓库的最新本地源码，而不是旧容器状态。

首次构建还需要联网拉取：

- `ghcr.io/xinnan-tech/xiaozhi-esp32-server:server-base`
- `node:18`
- `maven:3.9.4-eclipse-temurin-21`
- `bellsoft/liberica-runtime-container:jre-21-glibc`
- npm / Maven 依赖

### 6. 验证

至少检查：

```bash
docker inspect xiaozhi-esp32-server --format '{{.Config.Image}}'
docker inspect xiaozhi-esp32-server-web --format '{{.Config.Image}}'
```

预期结果：

```bash
xiaozhi-local/server-openclaw:dev
xiaozhi-local/web-openclaw:dev
```

浏览器访问：

- `http://localhost:8002`

如需确认“运行中的就是该仓库的最新 OpenClaw 版本，并且已经带有 `OpenClaw配对码` 功能”，可继续执行：

```bash
bash scripts/verify_openclaw_stack.sh
```

该脚本会检查：

- 当前容器是否是本地源码镜像，而不是官方 `latest`
- 前端打包产物是否包含 `OpenClaw配对码` / `openClawPairCode`
- 仓库源码是否包含智控台 `pairCode` 下发逻辑
- body bridge 配对设备接口是否可访问

## OpenClaw 与 Otto 动作链路

OpenClaw 侧并不直接控制舵机。

当前链路是：

`OpenClaw 插件工具 -> xiaozhi body bridge -> 设备侧 MCP -> Otto 固件动作实现`

服务端 body bridge 已暴露以下 Otto 接口：

- `POST /openclaw/body/v1/otto/action`
- `POST /openclaw/body/v1/otto/stop`
- `POST /openclaw/body/v1/otto/status`
- `POST /openclaw/body/v1/otto/theme`
- `POST /openclaw/body/v1/otto/emotion`

它们在设备侧分别映射到：

- `self.otto.action`
- `self.otto.stop`
- `self.otto.get_status`
- `self.screen.set_theme`
- `self.screen.set_emotion`

因此，OpenClaw 调 Otto “前进 / 后退 / 太空步 / 跳跃 / 摇摆”这一类动作，实际都走 `otto_action`。

典型动作映射如下：

- 前进：`otto_action(action=\"walk\", direction=1, steps=3, speed=700, arm_swing=50)`
- 后退：`otto_action(action=\"walk\", direction=-1, steps=3, speed=700, arm_swing=50)`
- 左右转：`otto_action(action=\"turn\", direction=1 或 -1, steps=2, speed=700, arm_swing=50)`
- 太空步：`otto_action(action=\"moonwalk\", direction=1 或 -1, steps=4, speed=700, amount=30)`
- 跳跃：`otto_action(action=\"jump\", steps=2, speed=700)`
- 摇摆：`otto_action(action=\"swing\", steps=3, speed=700, amount=30)`

当前 Otto 固件已实现的主要动作集合包括：

- `walk`
- `turn`
- `jump`
- `swing`
- `moonwalk`
- `bend`
- `shake_leg`
- `updown`
- `whirlwind_leg`
- `sit`
- `showcase`
- `home`
- `hands_up`
- `hands_down`
- `hand_wave`
- `windmill`
- `takeoff`
- `fitness`
- `greeting`
- `shy`
- `radio_calisthenics`
- `magic_circle`

OpenClaw 插件源码当前位于独立项目：

- `openclaw-otto-body-plugin`

该插件负责把上面的 bridge API 包装成 OpenClaw 原生工具：

- `otto_action`
- `otto_stop`
- `otto_get_status`
- `otto_set_theme`
- `otto_set_emotion`

## 最小交付标准

一名新的协作者成功接手该项目后，至少应满足：

- `bash scripts/check_prereqs.sh` 能完成环境自检
- `bash scripts/rebuild_local_docker_stack.sh` 可以成功完成构建和启动
- `http://localhost:8002` 可以打开智控台
- `bash scripts/verify_openclaw_stack.sh` 返回成功
- 智控台设备管理页包含 `OpenClaw配对码` 栏
- Otto 连接后，`POST /openclaw/body/v1/pair/devices` 能返回设备和 `pair_code`

## 关于 OpenClaw 网关版本

该仓库包含 Otto + OpenClaw 所需的服务端、智控台和 body bridge 逻辑。

该仓库保证：

- 当前构建出的 `xiaozhi-local/server-openclaw:dev`
- 当前构建出的 `xiaozhi-local/web-openclaw:dev`
- 当前源码里的 `OpenClaw配对码` 下发与展示能力

如果 OpenClaw 网关本体在另一仓库中维护，仍应在网关仓库中单独进行版本发布和 tag 管理。

## 推荐阅读顺序

- 文档入口：[docs/README.md](docs/README.md)
- 一页式搭建：[docs/openclaw-otto-one-page-setup.md](docs/openclaw-otto-one-page-setup.md)
- 完整方案：[docs/openclaw-otto-body-replication-guide.md](docs/openclaw-otto-body-replication-guide.md)
- 重连排障：[docs/ottoj-openclaw-reconnect-runbook.md](docs/ottoj-openclaw-reconnect-runbook.md)
- 发布检查：[docs/github-release-checklist.md](docs/github-release-checklist.md)
