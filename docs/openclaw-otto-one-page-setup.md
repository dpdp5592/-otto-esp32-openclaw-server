# OpenClaw + Otto 一页式安装流程

## 目标

该流程用于从零部署以下链路：

`OpenClaw -> body bridge -> xiaozhi-server -> Otto / test_page`

目标结果：

- OpenClaw 拥有 `otto_action` 等原生工具
- 小智测试页或 Otto 板子能够通过 `xiaozhi-server` 连上 OpenClaw
- Otto 身体动作可以通过 body bridge 成功执行

## 前置条件

需要准备以下内容：

1. 一台可运行 Docker 的 Linux 主机
2. `otto-esp32-openclaw-server` 仓库
3. `openclaw-otto-body-plugin` 仓库
4. 一套可用的 OpenClaw 模型配置
5. 一台 Otto 板子，或先使用 `test_page.html`

## 第一步：拉取仓库

### Bridge 仓库

```bash
git clone <your-git-url>/otto-esp32-openclaw-server.git
```

### Otto 插件仓库

```bash
git clone git@github.com:997180gf-dp/openclaw-otto-body-plugin.git
```

## 第二步：启动 xiaozhi-server

进入：

```bash
cd otto-esp32-openclaw-server
```

推荐直接使用仓库根目录脚本启动：

```bash
bash scripts/bootstrap_local_runtime.sh
bash scripts/rebuild_local_docker_stack.sh
```

如果你要手动看 compose 文件，再进入：

```bash
cd main/xiaozhi-server
```

项目实际采用的是：

- 单服务：`docker-compose.yml`
- 全模块：`docker-compose_all.yml`
- 本地源码覆盖：`docker-compose_all.local.yml`

至少需要保证这几个端口可用：

- `8000`：设备 WebSocket
- `8002`：智控台 / OTA
- `8003`：body bridge / vision HTTP

## 第三步：配置小智地址

在小智后台或配置中心中确认：

- `server.websocket = ws://<server-ip>:8000/xiaozhi/v1/`
- `server.ota = http://<server-ip>:8002/xiaozhi/ota/`

如果语音链路由 OpenClaw 负责，还需要：

- `selected_module.LLM = LLM_OpenClawLLM`
- `LLM_OpenClawLLM.base_url = ws://<openclaw-gateway-host>:18789`

## 第四步：部署 OpenClaw

确保 OpenClaw gateway 正常运行，并且已有可用模型。

确认健康状态：

```bash
curl http://127.0.0.1:18789/healthz
```

如果 OpenClaw 通过 Docker 运行，建议同时准备以下两个操作：

### 4.1 获取 dashboard 登录 URL

```bash
docker exec -it openclaw-gateway node openclaw.mjs dashboard --no-open
```

该命令会输出带 `#token=...` 的完整 URL，用于首次进入 Control UI。

### 4.2 处理首次设备配对

如果浏览器中出现 `pairing required`，可在主机上执行：

```bash
docker exec -it openclaw-gateway node openclaw.mjs devices list
docker exec -it openclaw-gateway node openclaw.mjs devices approve <requestId>
```

该步骤属于 OpenClaw gateway 自身的设备配对机制，与 Otto 设备接入小智的 WebSocket/MCP 会话不是同一层。

## 第五步：安装 otto-body 插件

将插件复制到 OpenClaw workspace：

```bash
mkdir -p <openclaw-workspace>/.openclaw/extensions
cp -r openclaw-otto-body-plugin <openclaw-workspace>/.openclaw/extensions/otto-body
```

然后把插件配置合并进 `openclaw.json`：

```json
{
  "plugins": {
    "allow": ["otto-body"],
    "entries": {
      "otto-body": {
        "enabled": true,
        "config": {
          "bridgeBaseUrl": "http://<server-ip>:8003/openclaw/body",
          "bridgeToken": "",
          "timeoutMs": 15000
        }
      }
    }
  }
}
```

重启 OpenClaw。

验证插件是否加载：

```bash
docker exec openclaw-gateway node openclaw.mjs plugins list
docker exec openclaw-gateway node openclaw.mjs plugins info otto-body
```

## 第六步：连接 Otto 或测试页

### 测试页

打开：

- `main/xiaozhi-server/test/test_page.html`

填入：

- OTA：`http://<server-ip>:8002/xiaozhi/ota/`

说明：

- 测试页会自动按项目要求发起 OTA 请求
- 手工 `curl` 调 OTA 时，需要额外带上 `Device-Id` 请求头，否则服务端会返回错误
- 一次成功的 OTA 请求应返回：
  - `websocket.url`
  - `websocket.token`

### 真实 Otto 板子

固件 OTA 地址应写为：

- `http://<server-ip>:8002/xiaozhi/ota/`

不能写 `127.0.0.1`。

## 第七步：验证设备侧 MCP

在小智日志中确认已收到 Otto 工具列表：

- `self.otto.action`
- `self.otto.stop`
- `self.otto.get_status`
- `self.screen.set_theme`

如果这一步失败，body bridge 不会工作。

## 第八步：验证 body bridge

### 状态查询

```bash
curl -H 'Content-Type: application/json' \
  -d '{"deviceId":"<otto-device-id>"}' \
  http://<server-ip>:8003/openclaw/body/v1/otto/status
```

### 动作调用

```bash
curl -H 'Content-Type: application/json' \
  -d '{"deviceId":"<otto-device-id>","action":"greeting","steps":2}' \
  http://<server-ip>:8003/openclaw/body/v1/otto/action
```

如果返回：

- `{"ok":true,...}`

则说明：

- body bridge 已打通
- Otto 的身体动作已能通过小智执行桥被调用

## 第九步：验证 OpenClaw 工具调用

此时 OpenClaw 已拥有：

- `otto_action`
- `otto_stop`
- `otto_get_status`
- `otto_set_theme`

接下来即可在 OpenClaw 会话中继续验证：

- 是否能看到这些工具
- 是否能根据指令自动调用这些工具

## 第十步：用 body pair code 绑定 Otto

这里不要再使用智控台设备激活时展示的那枚六码。

原因是：

- 智控台 `activation_code` 只用于设备首次绑定到管理端
- 绑定成功后该码会被消费并删除
- OpenClaw 侧应使用 body bridge 自己维护的 `pair_code`

先查看当前可配对设备：

```bash
curl -H 'Content-Type: application/json' \
  -d '{}' \
  http://<server-ip>:8003/openclaw/body/v1/pair/devices
```

返回的设备对象里会包含：

- `device_id`
- `pair_code`
- `online`
- `body_type`

然后把其中的 `pair_code` 填给 OpenClaw 的“连接新 Otto”流程，或者手工调用：

```bash
curl -H 'Content-Type: application/json' \
  -d '{"installationId":"<openclaw-installation-id>","pairCode":"<pair_code>"}' \
  http://<server-ip>:8003/openclaw/body/v1/pair/confirm
```

绑定完成后，插件后续应优先通过 `installationId` 解析默认身体，而不是继续依赖静态 `defaultDeviceId`。

## 最常见问题

### 1. body bridge 地址写成了 `8000`

错误：

- `http://<server-ip>:8000/openclaw/body`

正确：

- `http://<server-ip>:8003/openclaw/body`

### 2. 设备不在线

如果 bridge 返回：

- `device not online`

说明：

- Otto 没连回当前 `xiaozhi-server`
- 或 `deviceId` 填错了

### 3. OpenClaw 工具已加载，但动作不执行

此时应先确认：

- OpenClaw 插件是否已加载
- body bridge 是否返回成功
- Otto 是否已上报设备 MCP 工具

## 推荐继续阅读

- [README.md](../README.md)
- [openclaw-otto-body-replication-guide.md](./openclaw-otto-body-replication-guide.md)
- [ottoj-openclaw-reconnect-runbook.md](./ottoj-openclaw-reconnect-runbook.md)
