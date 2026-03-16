# OpenClaw 接管 Otto 身体方案简版说明

## 1. 方案结论

当前方案采用的不是“由小智服务端把设备工具动态注入给 OpenClaw”，而是：

- `OpenClaw` 原生持有 Otto 身体工具
- `xiaozhi-server` 负责语音链路、设备协议和执行转发
- Otto 板子继续走小智原生 WebSocket + MCP 协议

一句话概括：

**OpenClaw 是大脑，Otto 是身体，小智后端是语音和执行桥。**

## 2. 为什么这样做

如果继续沿用“小智把设备工具注入给 OpenClaw”的做法，会产生两个问题：

1. 工具归属仍然在 `xiaozhi-server`，不在 `OpenClaw`
2. `OpenClaw control-ui` 无法直接看到 Otto 身体工具

这不符合“由 OpenClaw 真正接管 Otto 身体”的目标。

因此当前方案改为：

- Otto 的身体能力以 `OpenClaw` 原生 plugin tools 的形式注册
- OpenClaw 调用这些工具时，再通过小智后端执行到真实设备

## 3. 最终架构

### OpenClaw

负责：

- 对话理解
- 决策
- 工具选择
- 原生暴露 Otto 身体工具

### xiaozhi-server

负责：

- 设备接入
- ASR / TTS
- WebSocket / MCP 协议
- 把 OpenClaw 的身体工具调用转成设备侧 MCP 调用

### Otto

负责：

- 执行舵机动作
- 执行屏幕主题/表情相关控制
- 上报设备状态

## 4. 关键链路

### 文本对话

`Otto -> xiaozhi-server -> OpenClaw -> xiaozhi-server -> Otto`

### 身体动作

`OpenClaw otto_action -> xiaozhi body bridge -> self.otto.action -> Otto`

## 5. 本次实际落地内容

### OpenClaw 侧

新增原生插件：

- `otto-body`

暴露工具：

- `otto_action`
- `otto_stop`
- `otto_get_status`
- `otto_set_theme`

效果：

- 这些工具直接属于 OpenClaw
- 在 OpenClaw 插件系统中可以被发现和调用

### xiaozhi-server 侧

新增一层 `body bridge` HTTP API，用来承接 OpenClaw 调用：

- `POST /openclaw/body/v1/otto/action`
- `POST /openclaw/body/v1/otto/stop`
- `POST /openclaw/body/v1/otto/status`
- `POST /openclaw/body/v1/otto/theme`

它的作用不是自己实现动作，而是：

- 找到当前在线 Otto 设备连接
- 调用设备侧 MCP 工具
- 把执行结果返回给 OpenClaw

## 6. 验证结果

当前已经验证成功两件事：

1. `OpenClaw` 原生 Otto 工具已经加载成功
2. 通过 `body bridge` 已经可以真实调用 Otto 板子的设备 MCP 动作

实际验证通过的调用包括：

- `otto_get_status`
- `otto_action(greeting)`

服务端日志已确认：

- `self.otto.get_status` 调用成功
- `self.otto.action` 调用成功

这说明链路不是停留在接口层，而是已经真实到板子执行层。

## 7. 复刻前提

复刻该方案需要满足以下条件：

1. Otto 板子本身基于 `otto-robot` 板级，已经支持 `self.otto.*` MCP 工具
2. Otto 能正常连上当前 `xiaozhi-server`
3. `xiaozhi-server` 能收到设备的 `tools/list`
4. OpenClaw 已部署并支持自定义 plugin

## 8. 配置关键点

### 小智设备链路

- 设备 WebSocket：`ws://<server-ip>:8000/xiaozhi/v1/`
- OTA：`http://<server-ip>:8002/xiaozhi/ota/`

### Body bridge

- `http://<server-ip>:8003/openclaw/body`

注意：

- `8000` 是设备 WebSocket
- `8003` 是 HTTP bridge
- 这两个端口不能混用

## 9. 当前方案的意义

这套方案的核心价值，不是简单“让小智多接了一个模型”，而是把系统职责重新理顺：

- OpenClaw 负责大脑和身体工具
- 小智负责语音和执行通道
- Otto 负责实体表达

这使得后续演进方向更清晰：

- 如果换模型，主要改 OpenClaw
- 如果换身体能力，主要改 Otto 工具或 bridge
- 小智后端仍可稳定复用其现有语音和协议能力

## 10. 一句话同步口径

**当前方案已将 Otto 的身体能力改造成 OpenClaw 原生工具，小智后端仅保留语音链路和设备执行桥，因此 OpenClaw 可以作为 Otto 的上层大脑直接控制动作和状态。**
