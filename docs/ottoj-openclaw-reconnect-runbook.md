# OttoJ 重连 OpenClaw 标准流程

## 1. 本轮结论

- 旧 Otto 的历史 `device-id` 是 `3c:dc:75:62:88:94`
- 2026-03-13 14:11 新烧录后重新接入的 OttoJ `device-id` 是 `1c:db:d4:b5:6b:1c`
- `openclaw-gateway` 当前 `otto-body` 插件已加载
- OpenClaw 默认设备已切换为 `1c:db:d4:b5:6b:1c`
- `xiaozhi-server` 可以同时接入多台 Otto
- `defaultDeviceId` 只是 OpenClaw `otto-body` 插件在未显式传 `deviceId` 时的默认目标，不代表系统只能接一台 Otto

## 2. 本轮关键证据

### 2.1 新 OttoJ 的 device-id

来自 `xiaozhi-esp32-server` 容器日志：

- `2026-03-13 14:11:37`
- `device-id: '1c:db:d4:b5:6b:1c'`
- 同时出现 `注册在线设备连接: 1c:db:d4:b5:6b:1c`

### 2.2 旧 Otto 历史记录

旧 Otto 的历史日志是：

- `device-id: '3c:dc:75:62:88:94'`

这台是上一轮设备，不应再作为当前 OttoJ 的默认设备。

### 2.3 OttoJ 已上报 Otto MCP 工具

新 OttoJ 在 `2026-03-13 14:11:38` 的连接日志显示：

- `serverInfo.name = "otto-robot"`
- `客户端设备支持的工具数量: 12`
- 工具中包含：
  - `self.otto.action`
  - `self.otto.stop`
  - `self.otto.get_status`
  - `self.screen.set_theme`

### 2.4 OpenClaw 当前已指向 OttoJ

当前 `openclaw-gateway` 内的 `openclaw.json` 为：

- `plugins.entries.otto-body.config.bridgeBaseUrl = http://192.168.19.225:8003/openclaw/body`
- `plugins.entries.otto-body.config.defaultDeviceId = 1c:db:d4:b5:6b:1c`

真实配置文件位置：

- `/home/dp/workspace/xiaozhi_row/openclaw-local/openclaw-v2/config/openclaw.json`

容器内对应位置：

- `/home/node/.openclaw/openclaw.json`

### 2.5 OpenClaw 插件当前状态

当前 `otto-body` 插件状态：

- `Status: loaded`
- `Tools: otto_action, otto_stop, otto_get_status, otto_set_theme`

### 2.6 本轮已验证过的真实动作

旧 Otto 的历史执行日志包括：

- `2026-03-13 11:18:11` `self.otto.get_status` 成功，返回 `idle`
- `2026-03-13 11:19:08` `self.otto.action` `home` 成功
- `2026-03-13 11:19:20` `self.otto.action` `greeting` 成功
- `2026-03-13 11:19:50` `self.otto.action` `showcase` 成功
- `2026-03-13 11:20:22` `self.otto.action` `hand_wave` 成功
- `2026-03-13 11:20:40` `self.otto.stop` 成功
- `2026-03-13 11:20:53` `self.otto.action` `jump` 成功
- `2026-03-13 11:24:29` `self.otto.action` `swing` 成功

新 OttoJ 本轮已确认完成的是：

- `2026-03-13 14:11:37` 在线连接成功
- `2026-03-13 14:11:38` `otto-robot` 工具上报成功
- `客户端设备支持的工具数量: 12`

## 3. 当前状态说明

旧设备 ID 已经离线，调用 bridge 会失败：

```bash
curl -s -H 'Content-Type: application/json' \
  -d '{"deviceId":"3c:dc:75:62:88:94"}' \
  http://127.0.0.1:8003/openclaw/body/v1/otto/status
```

返回：

```json
{"ok":false,"error":"设备 3c:dc:75:62:88:94 当前不在线"}
```

这表示：

- 旧 Otto 的历史接入和动作执行是成功的
- 但旧设备已经不再是当前目标设备

新 OttoJ 当前应改用：

```bash
curl -s -H 'Content-Type: application/json' \
  -d '{"deviceId":"1c:db:d4:b5:6b:1c"}' \
  http://127.0.0.1:8003/openclaw/body/v1/otto/status
```

如果不传 `deviceId`，OpenClaw 将命中 `defaultDeviceId`，也就是当前设置的 `1c:db:d4:b5:6b:1c`。

## 4. 标准重连流程

### 步骤 1：确认 OttoJ OTA 和 WebSocket 目标

OttoJ 固件应指向：

- OTA: `http://<server-ip>:8002/xiaozhi/ota/`
- WebSocket: `ws://<server-ip>:8000/xiaozhi/v1/`

注意：

- 不要把 OTA 写成 `127.0.0.1`
- 不要把 body bridge 的 `8003` 当成设备 WebSocket 端口

### 步骤 2：让 OttoJ 连上小智

最小成功判据：

- 串口出现连接到 `ws://<server-ip>:8000/xiaozhi/v1/`
- `xiaozhi-server` 日志出现：
  - `device-id: '1c:db:d4:b5:6b:1c'`
  - `注册在线设备连接: 1c:db:d4:b5:6b:1c`

建议命令：

```bash
docker logs --since 30m xiaozhi-esp32-server 2>&1 | rg -n "1c:db:d4:b5:6b:1c|注册在线设备连接|Headers:"
```

### 步骤 3：确认 Otto MCP 工具已就绪

最小成功判据：

- 日志出现 `收到mcp消息`
- 日志出现 `客户端设备支持的工具数量: 12`
- 工具中有 `self.otto.action` / `self.otto.stop` / `self.otto.get_status`

建议命令：

```bash
docker logs --since 30m xiaozhi-esp32-server 2>&1 | rg -n "tools/list|客户端设备支持的工具数量|self\\.otto\\.|self\\.screen\\.set_theme"
```

### 步骤 4：确认 OpenClaw 插件和默认设备配置

检查 `openclaw-gateway` 配置：

```bash
docker exec openclaw-gateway sh -lc 'sed -n "1,220p" /home/node/.openclaw/openclaw.json'
```

必须满足：

- `plugins.allow` 包含 `otto-body`
- `plugins.entries.otto-body.enabled = true`
- `bridgeBaseUrl = http://<server-ip>:8003/openclaw/body`
- `defaultDeviceId = 1c:db:d4:b5:6b:1c`

这里要特别说明：

- `xiaozhi-server` 能同时接多台 Otto
- `deviceId` 是每台设备自己的唯一标识
- `defaultDeviceId` 只是 OpenClaw 插件在没指定 `deviceId` 时的默认目标
- 如果你要控制多台 Otto，可以在工具调用时显式传 `deviceId`
- 所以系统不是“现在只能接一个 Otto”，而是“当前 OpenClaw 默认会先打到一台默认 Otto”

检查插件：

```bash
docker exec openclaw-gateway node /app/openclaw.mjs plugins info otto-body
```

成功判据：

- `Status: loaded`
- `Tools: otto_action, otto_stop, otto_get_status, otto_set_theme`

### 步骤 5：先手工验证 body bridge

先测状态：

```bash
curl -s -H 'Content-Type: application/json' \
  -d '{"deviceId":"1c:db:d4:b5:6b:1c"}' \
  http://127.0.0.1:8003/openclaw/body/v1/otto/status
```

成功时应返回：

```json
{"ok":true,"result":{"raw":"idle"}}
```

再测动作：

```bash
curl -s -H 'Content-Type: application/json' \
  -d '{"deviceId":"1c:db:d4:b5:6b:1c","action":"greeting"}' \
  http://127.0.0.1:8003/openclaw/body/v1/otto/action
```

成功时应返回：

```json
{"ok":true,"result":true}
```

同时服务端日志应出现：

- `发送客户端mcp工具调用请求: self.otto.action`
- `客户端mcp工具调用 self.otto.action 成功`

### 步骤 6：再验证 OpenClaw 侧调用

在 OpenClaw control-ui 或 agent 中调用：

- `otto_get_status`
- `otto_action(action="greeting")`
- `otto_action(action="showcase")`

如果这一步失败，但步骤 5 成功，问题通常在：

- OpenClaw agent 提示词
- OpenClaw 工具选择策略
- OpenClaw 当前会话未使用 `otto-body` 工具

而不是 Otto 设备链路本身。

## 5. 故障优先排查顺序

### 现象 1：bridge 返回“设备当前不在线”

先查：

1. OttoJ 是否真的连接到当前服务器
2. `device-id` 是否仍然是 `1c:db:d4:b5:6b:1c`
3. `xiaozhi-server` 是否出现 `注册在线设备连接`

### 现象 2：设备在线但 bridge 仍失败

先查：

1. 是否收到 `tools/list`
2. `mcp_client` 是否 ready
3. 工具里是否真的有 `self.otto.*`

### 现象 3：bridge 成功但 OpenClaw 不触发动作

先查：

1. `otto-body` 插件是否 loaded
2. `defaultDeviceId` 是否写对
3. agent 提示词是否明确要求优先调用动作工具

## 6. 固定资产

当前 OttoJ 相关固定值：

- `device-id`: `1c:db:d4:b5:6b:1c`
- body bridge: `http://192.168.19.225:8003/openclaw/body`
- OpenClaw gateway: `ws://openclaw-gateway:18789`

## 7. 推荐后续动作

为了让后续复现更稳，建议补两项：

1. 把 OttoJ 的 `device-id`、板子名称、用途单独登记到一个设备清单文档
2. 在 [openclaw-otto-body-replication-guide.md](./openclaw-otto-body-replication-guide.md) 增加“线上排障章节”，把 `device 当前不在线` 的判断流程合并进去
