# 运行态固化与迁移

> 说明：本文档主要记录原始环境的运行态固化与迁移思路，包含一些历史路径和旧环境信息。
> 如果你的目标是让新同事在这份精简仓库里直接启动最新本地 OpenClaw 版本，请优先看 [README.md](../README.md) 和 [github-release-checklist.md](./github-release-checklist.md)。

本文档针对当前这套已经接入 `OpenClaw` 的 `xiaozhi-esp32-server` 部署，目标是把“只有本机能跑”的状态固化成：

- 可追踪的源码改动
- 可打包的运行态数据
- 可在另一台机器上复现的部署材料

## 1. 先区分三类东西

当前有效状态分成三层，必须分别处理。

### 1.1 源码改动

这部分应该进入 Git 仓库。

- `xiaozhi-esp32-server`
- `xiaozhi-esp32`
- 如果改过 OpenClaw 源码，还要进入 OpenClaw 对应仓库

### 1.2 运行配置和业务数据

这部分通常不在 Git 里，而是在挂载目录和数据库里。

当前环境已确认的关键目录：

- `/opt/xiaozhi-server/data`
- `/opt/xiaozhi-server/uploadfile`
- `/opt/xiaozhi-server/mysql/data`
- `/home/dp/workspace/xiaozhi_row/openclaw-local/openclaw/config`
- `/home/dp/workspace/xiaozhi_row/openclaw-local/openclaw/workspace`

如果不迁这些目录，只迁源码，另一台机器启动后大概率会表现为一套新的智控台。

### 1.3 容器运行编排

当前小智全量部署 compose 文件在：

- [docker-compose_all.yml](/home/dp/workspace/xiaozhi-esp32-server/main/xiaozhi-server/docker-compose_all.yml)

当前确认的端口：

- `8000`: WebSocket 服务
- `8002`: 智控台
- `8003`: HTTP / vision / OTA
- `18789-18790`: OpenClaw Gateway

## 2. 第一步：先把源码固化进 Git

在每个有改动的仓库执行：

```bash
git status --short
git checkout -b feature/your-change-name
git add <你确认要提交的文件>
git commit -m "feat: describe your local customization"
git push origin feature/your-change-name
```

当前本机已经检测到以下仓库存在未提交改动：

- `/home/dp/workspace/xiaozhi-esp32-server`
- `/home/dp/workspace/xiaozhi_row/xiaozhi-esp32`

建议做法：

1. 先把“服务端 OpenClaw 接入改动”独立提交到 `xiaozhi-esp32-server`
2. 再把“固件板级改动”独立提交到 `xiaozhi-esp32`
3. 不要把数据库、模型、日志、缓存混进源码提交

## 3. 第二步：导出当前运行态

仓库已提供导出脚本：

- [export_runtime_bundle.sh](/home/dp/workspace/xiaozhi-esp32-server/scripts/export_runtime_bundle.sh)

执行方式：

```bash
cd /home/dp/workspace/xiaozhi-esp32-server
bash scripts/export_runtime_bundle.sh
```

如果想导出到指定目录：

```bash
cd /home/dp/workspace/xiaozhi-esp32-server
bash scripts/export_runtime_bundle.sh /tmp
```

脚本会打包：

- `/opt/xiaozhi-server/data`
- `/opt/xiaozhi-server/uploadfile`
- `/opt/xiaozhi-server/mysql/data`
- OpenClaw 的 `config` 和 `workspace`
- 当前 compose / config 文件
- 当前 `docker inspect` 结果

这一步的目标不是“长期版本管理”，而是先把当前有效运行态完整冻结，避免你之后忘记本机到底跑的是什么。

## 4. 第三步：整理出对外可交付材料

建议在你自己的 GitHub 仓库里至少保留这些内容：

- 源码提交
- 一个明确可用的 `docker-compose.yml` 或 `docker-compose_all.yml`
- 一个配置模板，比如 `.env.example` / `.config.yaml.example`
- 一份部署文档
- 一份数据库导出或初始化说明

最少应新增这些说明：

1. 小智服务端如何启动
2. OpenClaw Gateway 如何启动
3. 哪些目录必须做持久化挂载
4. 首次部署后如何恢复智控台数据
5. ESP32 固件要连接哪个地址

## 5. 第四步：迁移到另一台机器

### 5.1 Windows 机器准备

安装：

- Docker Desktop
- Git
- 如果要本地调试脚本，再装一个 shell 环境，例如 Git Bash

### 5.2 复制材料

至少复制两部分：

1. 你的源码仓库
2. 第 3 步导出的 runtime bundle

### 5.3 恢复目录

在新机器上恢复出与旧环境对应的目录，再修改 compose 挂载路径指向这些目录。

例如恢复为：

- `D:\xiaozhi-runtime\data`
- `D:\xiaozhi-runtime\uploadfile`
- `D:\xiaozhi-runtime\mysql\data`
- `D:\xiaozhi-runtime\openclaw\config`
- `D:\xiaozhi-runtime\openclaw\workspace`

### 5.4 启动前必须确认

1. 智控台数据库是否已恢复
2. OpenClaw 配置是否已恢复
3. Compose 中端口是否未冲突
4. 服务监听地址是否允许局域网访问
5. Windows 防火墙是否已放行 `8000`、`8002`、`8003`、`18789`

## 6. 第五步：验证不是“新的智控台”

启动后检查：

1. 打开智控台，确认原有模型、智能体、设备配置仍在
2. 确认 LLM 提供商里仍能看到并选中 `openclaw`
3. 确认设备接入后仍能调到原来的 OpenClaw 路径
4. 确认上传文件、角色资源、数据库记录都还在

如果启动后后台是空白的、管理员需要重新注册、模型配置全没了，说明数据库没有恢复成功，当前实例实际上已经变成一套新的智控台。

## 7. 实际执行顺序建议

按下面顺序做，不要乱序：

1. 先看 `git status`，把源码改动提交到各自仓库
2. 运行导出脚本，把当前运行态冻结成 bundle
3. 把 bundle 备份到安全位置
4. 在 GitHub 上推送源码分支
5. 在目标机器恢复 bundle 和代码
6. 调整 compose 挂载路径
7. 启动容器
8. 用浏览器验证智控台和 OpenClaw
9. 最后再让 ESP32 指向新服务地址

## 8. 你现在这套环境的关键提醒

当前本机检查结果表明：

- `xiaozhi-esp32-server` 代码有未提交改动
- `xiaozhi-esp32` 固件代码也有未提交改动
- 运行中的 OpenClaw 和智控台状态并不只存在源码目录中
- 很多关键状态实际落在 `/opt/xiaozhi-server/...` 和 `openclaw-local/...`

因此，**只推 GitHub 仓库不够，只拷容器数据也不够**。你必须同时固化：

- 源码
- 配置
- 数据
- 部署说明

否则别人拿到仓库后，最多只能“跑起来一个新实例”，而不是复现你当前已经调好的这一套。

## 9. 避免再次误用官方 latest 镜像

如果你已经对本地源码做了 `OpenClaw` 定制，那么后续不要再直接使用：

- `main/xiaozhi-server/docker-compose_all.yml`

原因是这份基础 compose 默认引用的是官方镜像：

- `ghcr.nju.edu.cn/xinnan-tech/xiaozhi-esp32-server:server_latest`
- `ghcr.nju.edu.cn/xinnan-tech/xiaozhi-esp32-server:web_latest`

这会导致一个常见误区：

- 你改了本地源码
- 你执行了 `docker compose up -d`
- 实际拉起的仍然是官方镜像，而不是你的本地代码

### 9.1 本仓库现在推荐的本地源码启动方式

新增的本地覆盖文件：

- [docker-compose_all.local.yml](/home/dp/workspace/xiaozhi-esp32-server/main/xiaozhi-server/docker-compose_all.local.yml)

它会把两个核心服务替换成“本地源码构建 + 固定本地 tag”：

- `xiaozhi-local/server-openclaw:dev`
- `xiaozhi-local/web-openclaw:dev`

### 9.2 以后统一使用这一条命令

仓库新增脚本：

- [rebuild_local_docker_stack.sh](/home/dp/workspace/xiaozhi-esp32-server/scripts/rebuild_local_docker_stack.sh)

每次你修改了源码并希望重启生效，都执行：

```bash
cd /home/dp/workspace/xiaozhi-esp32-server
bash scripts/rebuild_local_docker_stack.sh
```

这个脚本等价于：

```bash
cd /home/dp/workspace/xiaozhi-esp32-server/main/xiaozhi-server
docker compose \
  -f docker-compose_all.yml \
  -f docker-compose_all.local.yml \
  up -d --build xiaozhi-esp32-server xiaozhi-esp32-server-web
```

### 9.3 之后怎么判断自己有没有又切回官方镜像

执行：

```bash
docker inspect xiaozhi-esp32-server --format '{{.Config.Image}}'
docker inspect xiaozhi-esp32-server-web --format '{{.Config.Image}}'
```

正确结果应是：

- `xiaozhi-local/server-openclaw:dev`
- `xiaozhi-local/web-openclaw:dev`

如果你看到的仍然是：

- `ghcr.nju.edu.cn/xinnan-tech/xiaozhi-esp32-server:server_latest`
- `ghcr.nju.edu.cn/xinnan-tech/xiaozhi-esp32-server:web_latest`

说明当前运行的仍然不是你的本地定制版。

### 9.4 一个需要特别明确的点

`docker restart <container>` 不会重新构建镜像。

所以：

- 改了源码后，不能只执行 `docker restart`
- 必须重新执行 `docker compose ... up -d --build`
- 或直接运行上面的 `rebuild_local_docker_stack.sh`

只有这样，“重启后的运行内容”才会等于你当前工作区源码。
