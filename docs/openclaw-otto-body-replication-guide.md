# OpenClaw 接管 Otto 身体复刻指南

## 1. 目标

本方案的目标不是把 `OpenClaw` 当成 `xiaozhi-server` 的一个普通 LLM Provider，而是让：

- `OpenClaw` 成为 Otto 的上层大脑
- `OpenClaw` 原生拥有身体工具
- `xiaozhi-server` 只负责语音链路、设备协议和工具执行
- Otto 板子继续沿用小智现有 WebSocket + MCP 协议

最终链路：

`OpenClaw tool -> xiaozhi body bridge -> device MCP -> Otto`

## 2. 为什么不走“小智动态注入工具给 OpenClaw”

当前验证确认了两个事实：

1. `xiaozhi-server` 确实可以拿到设备侧 `self.otto.*` MCP 工具。
2. 但当前 OpenClaw Gateway 的 `chat.send` / `agent` RPC 不支持按单次请求动态注入 `tools/functions`。

因此如果继续沿用以下链路：

`Otto -> xiaozhi-server -> OpenClawLLM(functions注入)`

会有两个问题：

- 工具属于 `xiaozhi-server`，不属于 `OpenClaw`
- `OpenClaw control-ui` 看不到 Otto 身体工具

这不符合“OpenClaw 真正接管 Otto 身体”的目标。

因此当前方案采用：

- Otto 身体工具注册为 `OpenClaw` 原生 plugin tools
- `xiaozhi-server` 退化为执行桥

## 3. 最终架构

### 3.1 分层职责

#### OpenClaw

- 维护对话会话
- 选择模型
- 决定何时调用身体工具
- 在 control-ui 中直接暴露 `otto_action` 等工具

#### xiaozhi-server

- 负责设备 WebSocket 链路
- 负责 ASR / TTS
- 负责设备 MCP `tools/call`
- 提供一个给 OpenClaw 调用的 body bridge HTTP API

#### Otto 固件

- 继续通过小智原生协议接入
- 继续通过设备侧 `McpServer` 暴露 `self.otto.*`
- 负责真正执行舵机、屏幕主题、状态查询

### 3.2 关键调用链

#### 文本对话链

`Otto -> xiaozhi-server -> OpenClaw -> xiaozhi-server -> Otto`

#### 身体动作链

`OpenClaw otto_action -> xiaozhi bridge -> self.otto.action -> Otto servo`

## 4. 这轮实际改了什么

### 4.1 OpenClaw 侧

在 OpenClaw workspace 下新增原生插件。

插件代码建议来自独立仓库：

- `openclaw-otto-body-plugin`

部署后在 OpenClaw workspace 中的落点应为：

- `workspace/.openclaw/extensions/otto-body/index.js`
- `workspace/.openclaw/extensions/otto-body/openclaw.plugin.json`

插件 id：

- `otto-body`

注册的原生工具：

- `otto_action`
- `otto_stop`
- `otto_get_status`
- `otto_set_theme`

OpenClaw 配置文件：

- `openclaw.json`

关键配置：

- `plugins.allow = ["otto-body"]`
- `plugins.entries.otto-body.enabled = true`
- `plugins.entries.otto-body.config.bridgeBaseUrl = http://<server-ip>:8003/openclaw/body`
- `plugins.entries.otto-body.config.defaultDeviceId = <otto-device-id>`

### 4.2 xiaozhi-server 侧

新增和改动如下：

- [openclaw_body_handler.py](../main/xiaozhi-server/core/api/openclaw_body_handler.py)
- [http_server.py](../main/xiaozhi-server/core/http_server.py)
- [websocket_server.py](../main/xiaozhi-server/core/websocket_server.py)
- [connection.py](../main/xiaozhi-server/core/connection.py)
- [app.py](../main/xiaozhi-server/app.py)

核心改动分三块。

#### 1. 在线设备连接注册表

在 `WebSocketServer` 上增加：

- `device_connections`
- `register_device_connection(conn)`
- `unregister_device_connection(conn)`
- `get_device_connection(device_id)`

目的：

- body bridge 需要根据 `deviceId` 找到当前在线 Otto 连接

#### 2. 在连接建立和释放时维护注册表

在 `ConnectionHandler.handle_connection(...)` 中：

- 连接建立后注册当前设备连接
- 连接关闭时从注册表移除

#### 3. 新增 body bridge HTTP API

在 `aiohttp` HTTP 服务里增加：

- `POST /openclaw/body/v1/otto/action`
- `POST /openclaw/body/v1/otto/stop`
- `POST /openclaw/body/v1/otto/status`
- `POST /openclaw/body/v1/otto/theme`

这些接口内部不直接操作设备，而是复用现有设备 MCP 调用链：

- 通过 `deviceId` 找到在线连接
- 调用 `call_mcp_tool(...)`
- 转发到：
  - `self.otto.action`
  - `self.otto.stop`
  - `self.otto.get_status`
  - `self.screen.set_theme`

## 5. 配置要求

### 5.1 OpenClaw 配置

OpenClaw 的模型和插件配置位于：

- `openclaw.json`

当前示例中，模型使用：

- `minimax-internal/minimax`

插件配置必须满足：

```json
{
  "plugins": {
    "allow": ["otto-body"],
    "entries": {
      "otto-body": {
        "enabled": true,
        "config": {
          "bridgeBaseUrl": "http://<server-ip>:8003/openclaw/body",
          "defaultDeviceId": "<otto-device-id>",
          "timeoutMs": 15000
        }
      }
    }
  }
}
```

注意：

- `bridgeBaseUrl` 必须走小智 HTTP 端口 `8003`
- 不能写成设备 WebSocket 端口 `8000`

### 5.2 小智服务端配置

设备链路仍然走小智原有配置：

- `server.websocket = ws://<server-ip>:8000/xiaozhi/v1/`
- `server.ota = http://<server-ip>:8002/xiaozhi/ota/`

如果语音对话仍由 OpenClaw 负责，则设备差异化配置中：

- `selected_module.LLM = LLM_OpenClawLLM`
- `LLM_OpenClawLLM.base_url = ws://<openclaw-gateway-host>:18789`

注意区分：

- 设备连接小智：`8000`
- OpenClaw 调 body bridge：`8003`
- 小智调用 OpenClaw gateway：`18789`

### 5.3 固件 OTA 配置

真实 Otto 板子不能写 `127.0.0.1`。

应填写：

- `http://<server-ip>:8002/xiaozhi/ota/`

## 6. Otto 侧前置条件

### 6.1 板级配置

本方案基于 Otto 板级：

- [otto-robot](/home/dp/workspace/xiaozhi_row/xiaozhi-esp32/main/boards/otto-robot)

原因：

- Otto 板级已经原生把舵机能力做成设备 MCP 工具
- 无需继续沿用 `ServoActions::HandleText` 这种关键词本地触发方案

### 6.2 Otto 板子必须已经上报工具

服务端日志中应能看到：

- `客户端设备支持的工具数量: 12`
- `self.otto.action`
- `self.otto.stop`
- `self.otto.get_status`
- `self.screen.set_theme`

这一步没成立，body bridge 无法工作。

## 7. 复刻步骤

### 步骤 1：先把 Otto 正常接入小智

验证项：

- 板子能通过 OTA 获取 WebSocket 地址
- 板子串口里看到：
  - `Connecting to websocket server: ws://<server-ip>:8000/xiaozhi/v1/`
- 板子能正常语音问答

### 步骤 2：确认 Otto 的设备侧 MCP 正常

在小智日志中应看到：

- `收到mcp消息`
- `tools/list`
- `客户端设备支持的工具数量: 12`

### 步骤 3：部署 OpenClaw 原生插件

在 OpenClaw workspace 下放入：

- `workspace/.openclaw/extensions/otto-body/openclaw.plugin.json`
- `workspace/.openclaw/extensions/otto-body/index.js`

然后重启 `openclaw-gateway`。

验证：

```bash
docker exec openclaw-gateway node openclaw.mjs plugins list
docker exec openclaw-gateway node openclaw.mjs plugins info otto-body
```

预期：

- `otto-body` 状态为 `loaded`
- 能看到 `Tools: otto_action, otto_stop, otto_get_status, otto_set_theme`

### 步骤 4：部署 xiaozhi body bridge

把上面列出的 `xiaozhi-server` 改动同步到运行容器或镜像中，重启 `xiaozhi-esp32-server`。

验证：

先确认 `xiaozhi-server` 的 HTTP 服务已正常启动，再测 body bridge：

```bash
curl -H 'Content-Type: application/json' \
  -d '{"deviceId":"<otto-device-id>"}' \
  http://<server-ip>:8003/openclaw/body/v1/otto/status
```

预期：

- 在线时返回 `{"ok":true,...}`
- 离线时返回 `设备 当前不在线`

### 步骤 5：先手工验证动作桥

先绕开 OpenClaw，直接打桥：

```bash
curl -H 'Content-Type: application/json' \
  -d '{"deviceId":"<otto-device-id>","action":"greeting","steps":2}' \
  http://<server-ip>:8003/openclaw/body/v1/otto/action
```

这一步成功，说明：

- `OpenClaw body bridge -> xiaozhi -> Otto`

已经跑通。

### 步骤 6：再让 OpenClaw 调原生工具

此时 OpenClaw 已经拥有 `otto_action` 等工具。

后续要让 agent 自动调用，只需要继续调优：

- OpenClaw 侧系统提示词
- 工具选择策略
- 动作名映射

而不再需要改小智的工具注入逻辑。

## 8. 这轮验证结果

本轮已经实际验证成功：

### 8.1 Bridge 状态查询成功

请求：

```json
{"deviceId":"<otto-device-id>"}
```

返回：

```json
{"ok":true,"result":{"raw":"idle"}}
```

### 8.2 Bridge 动作调用成功

请求：

```json
{"deviceId":"<otto-device-id>","action":"greeting","steps":2}
```

返回：

```json
{"ok":true,"result":true}
```

同时小智日志确认：

- `发送客户端mcp工具调用请求: self.otto.action`
- `客户端mcp工具调用 self.otto.action 成功`

这说明不是“HTTP 接口假成功”，而是真正已经打到了 Otto 板子。

## 9. 常见坑

### 9.1 把 bridge 端口写成 `8000`

错误：

- `http://<server-ip>:8000/openclaw/body`

正确：

- `http://<server-ip>:8003/openclaw/body`

原因：

- `8000` 是设备 WebSocket
- `8003` 是 `aiohttp` HTTP 服务

### 9.2 把固件 OTA 写成 `127.0.0.1`

真实板子上 `127.0.0.1` 指向板子自己，不是服务器。

### 9.3 OpenClaw 默认设备 ID 还写着测试页 MAC

如果配置中仍保留测试页设备 ID，OpenClaw 将无法命中真实 Otto 设备。

因此：

- `defaultDeviceId` 应替换为真实 Otto 板子的 `device_id`
- 不应继续保留测试页模拟设备的 MAC

### 9.4 只看 OpenClaw 网页会话，以为工具没暴露

在这个方案里：

- OpenClaw control-ui 能看到 `otto_*` 工具
- 但 Otto 设备和 OpenClaw 网页聊天仍然是两个不同会话

不要再用“小智动态把设备 MCP 注入给 OpenClaw 会话”的思路理解这套架构。

### 9.5 Otto 没有真的连回当前小智服务

最直接判断方式：

- 板子串口里看 WebSocket 地址
- 小智日志里看是否出现该 `device-id` 的新连接

如果没有新连接，bridge 一定只会返回“不在线”。

## 10. 后续建议

本轮已经完成的是：

- `OpenClaw 原生工具拥有 Otto 身体能力`
- `xiaozhi-server 变成身体执行桥`

后续建议继续做两件事：

1. 给 OpenClaw agent 单独写一版 Otto 具身提示词
2. 继续把 `otto_action` 的动作名约束和映射做得更稳定

建议优先固定这几个高频动作：

- `greeting`
- `hand_wave`
- `showcase`
- `jump`
- `magic_circle`
- `home`
- `stop`

## 11. 两阶段演进路线

如果最终目标不是“验证 Otto 能被 OpenClaw 控制”，而是“做出一个面向消费者、最简易使用的 OpenClaw 硬件身体方案”，最适合的路径不是立刻去掉 `xiaozhi-server`，而是走两阶段演进。

### 阶段 1：先做可交付版本

目标：

- 保留当前 `xiaozhi-server + Otto 固件 + OpenClaw` 架构
- 先把“能稳定接入、能 OTA、能被 OpenClaw 控制、能复现部署”的第一版做出来
- 让消费者视角下的安装、配网、上线、恢复尽量简单

这一阶段的分工仍然是：

- `OpenClaw` 负责 Agent、模型、工具决策
- `xiaozhi-server` 负责设备接入、body bridge、设备协议、OTA
- `Otto` 固件继续复用当前小智 WebSocket + MCP 协议

为什么先做这一阶段：

- 这条链路已经在真机上验证通过
- 风险最低
- 最快能形成“固件 + 后端 + OpenClaw 插件”的参考方案
- 先解决消费者真正关心的问题：配网、在线、动作、升级、恢复

### 阶段 2：再把小智后端瘦身成最小设备网关

目标：

- 逐步把 ASR / TTS / 对话编排能力从 `xiaozhi-server` 迁走
- 让 `OpenClaw` 成为真正的上层大脑
- 把 `xiaozhi-server` 收缩为你自己的 `OpenClaw Device Gateway`

这一阶段小智后端保留的核心能力应只剩：

- 设备 WebSocket 接入
- 设备鉴权、在线状态、连接注册表
- 设备侧 MCP 工具执行
- body bridge
- OTA / 配置下发

这一阶段的价值：

- 架构更清晰
- 更接近你自己的“OpenClaw 硬件参考后端”
- 后续支持更多 ESP32 身体时，更容易统一

为什么不建议现在直接跳到彻底去小智：

- 你当前 Otto 固件就是按小智协议接入的
- 如果立刻完全去掉小智，相当于要同时重做固件接入协议、设备网关、OTA、实时音频链路和工具执行层
- 这会显著拉长做出消费者可用版本的时间

## 12. 当前完成度

截至当前，这个路线已经完成到“阶段 1 的核心链路打通”。

### 12.1 已完成

- `OpenClaw` 原生 `otto-body` 插件已接入
- OpenClaw 已能暴露：
  - `otto_action`
  - `otto_stop`
  - `otto_get_status`
  - `otto_set_theme`
- `xiaozhi-server` 已补齐 body bridge：
  - `/openclaw/body/v1/otto/action`
  - `/openclaw/body/v1/otto/stop`
  - `/openclaw/body/v1/otto/status`
  - `/openclaw/body/v1/otto/theme`
- `xiaozhi-server` 已支持按 `deviceId` 查找在线 Otto 连接
- Otto 板子已通过小智协议接入并上报 `self.otto.*` MCP 工具
- 已完成真机验证：
  - `otto_get_status`
  - `otto_action(greeting)`
- OpenClaw 默认设备已切到当前新 Otto 的 `device-id`

### 12.2 当前状态判断

现在已经不是“概念验证”阶段，而是：

- 真机链路已通
- 架构方向已确定
- 文档和复现路径已沉淀

但还没有到“消费者可直接使用”的程度。

### 12.3 还没完成的部分

还缺的主要不是单点技术验证，而是产品化工作：

- 更稳定的设备首连 / 重连体验
- 更清晰的默认设备与多设备切换机制
- 更简单的部署和配置方式
- 更稳的 Agent 动作映射与提示词
- 更完整的 OTA / 恢复 / 排障路径

## 13. 接下来要做的事情

按优先级建议如下。

### 13.1 第一优先级：把阶段 1 做完整

1. 固化高频动作集合
- 先把 `greeting`、`hand_wave`、`showcase`、`jump`、`home`、`stop` 做成稳定动作白名单

2. 补 Otto 专用 Agent 提示词
- 明确哪些用户表达应映射到哪些动作
- 减少模型乱造动作名

3. 做好多设备逻辑
- 说明 `xiaozhi-server` 可同时接多台 Otto
- `defaultDeviceId` 只是默认目标
- 后续在工具调用中允许显式传 `deviceId`

4. 固化部署与恢复流程
- OpenClaw 配置文件位置
- 小智配置文件位置
- 容器重启后如何恢复
- 新设备上线后如何确认 `device-id`

5. 补完整 OTA/首连流程
- 让“新板子烧录后如何接入”成为标准步骤
- 避免每次靠手工排日志找状态

### 13.2 第二优先级：启动阶段 2 的瘦身设计

1. 盘点 `xiaozhi-server` 中哪些模块未来要保留
- 设备接入
- MCP 工具执行
- body bridge
- OTA

2. 盘点哪些模块未来应迁走
- ASR
- TTS
- 对话主链路中的 Agent 编排

3. 定义未来的最小设备网关边界
- 什么留在 `OpenClaw`
- 什么留在设备网关
- 固件与网关之间的最小协议集是什么

### 13.3 暂时不要优先做的事情

在阶段 1 没产品化之前，不建议优先投入：

- 彻底重写 Otto 固件协议
- 完全去掉小智后端
- 同时引入新的 IoT 云平台替代当前设备执行链路

因为这些会让你过早进入“大重构”，而不是先拿到一个可交付版本。

## 14. 最终产品方向：云桥接模式

在进一步评估消费者场景后，当前更适合的最终产品方向不是“你们统一托管用户的 OpenClaw”，而是：

- 用户保留自己的 `OpenClaw`
- 你提供云端 `body gateway`
- 用户在自己的 OpenClaw 中安装 `otto-body` 插件
- 插件通过你提供的 `bridgeBaseUrl` 访问云端身体服务
- 用户完成登录/绑定后，插件自动找到属于他的 Otto 身体

这条路线的关键点是：

- Otto 不负责扩展 OpenClaw 的智能边界
- Otto 只是给 OpenClaw 增加“硬件身体”这一层表达能力
- 你的产品不是新的 Agent 平台，而是 OpenClaw 的身体扩展层

### 14.1 目标边界

按这个方向，系统边界应明确为：

#### 用户侧 OpenClaw

- 仍由用户自己管理
- 运行在用户自己的电脑、NAS 或云主机
- 保留用户自己的模型、记忆、工作流和插件体系

#### 你提供的能力

- 烧录好的 Otto / ESP32 固件
- 云端 body gateway
- `otto-body` OpenClaw 插件
- 设备绑定服务
- OTA 服务

### 14.2 推荐架构

推荐架构应演进为：

`User OpenClaw -> otto-body plugin -> cloud body gateway -> device bridge -> Otto`

其中：

- `OpenClaw` 负责决策和工具调用
- `cloud body gateway` 负责用户和身体之间的绑定、在线状态、默认身体解析、动作转发
- Otto 设备继续连接设备网关，不直接暴露给用户的 OpenClaw

### 14.3 为什么选云桥接模式

相较于“用户本地 OpenClaw 直接连本地身体网关”，云桥接模式更适合消费级第一版：

- 用户不需要自己处理设备公网接入
- 设备不需要暴露在公网
- 配网、绑定、OTA 都可以统一收敛到你们的服务
- 用户感知是“给自己的 OpenClaw 加了一个身体”，而不是“迁移到你们的平台”

### 14.4 用户视角的目标体验

理想使用流程应是：

1. 用户拿到烧录好的 Otto 设备
2. 上电并完成 Wi-Fi 配网
3. 设备连接到你们公网 body gateway
4. 设备屏幕显示二维码或绑定码
5. 用户在网页完成登录和绑定
6. 用户在自己的 OpenClaw 安装 `otto-body` 插件
7. 插件登录后自动发现“我的身体”
8. OpenClaw 后续调用 `otto_action` 时自动命中这台身体

在这个流程中，用户不应该手工接触：

- `device-id`
- Docker 配置
- `openclaw.json` 中的静态 `defaultDeviceId`

### 14.5 对插件的要求

按这个方向，`otto-body` 插件后续不应长期依赖静态：

- `defaultDeviceId`

而应逐步改成：

- 用户登录插件
- 插件向云端 body gateway 查询：
  - 当前用户绑定的身体列表
  - 默认身体
  - 当前在线状态
- 未显式传 `deviceId` 时，插件自动选中默认身体

也就是说，后续插件需要支持：

- `bridgeBaseUrl`
- 登录态 / access token
- `get default body`
- `list bodies`
- 可选的显式 `deviceId`

### 14.6 对后端的要求

按这个方向，后端需要新增的不再只是 body bridge，还包括：

1. 用户绑定体系
- 用户账号
- 设备 pairing code / 绑定码
- `device_id -> user_id` 绑定关系

2. 设备注册表
- 记录在线设备
- 记录设备型号、固件版本、最后上线时间
- 记录是否为 Otto 身体

3. 默认身体解析
- 为每个用户提供默认身体
- 支持多个身体时的切换

4. OTA 运营能力
- 记录当前固件版本
- 提供稳定升级入口
- 为后续灰度和升级回执留接口

### 14.6.1 六位绑定码的正确用法

这里要特别明确：

- 六位设备码应作为“一次性绑定码 / pairing code”使用
- 不建议把 `device_id` 继续暴露给用户手工配置
- 也不建议让用户长期把六位码写死在插件配置里

更合理的做法是：

1. 设备首次联网后，后端为该设备分配一个六位绑定码
2. 设备屏幕展示该绑定码或二维码
3. 用户在自己的 `otto-body` 插件中输入该绑定码
4. 插件把绑定码发给 cloud body gateway
5. 后端查到对应 `device_id`
6. 后端建立：
   - `OpenClaw 插件安装实例 / 用户`
   - `device_id`
   之间的绑定关系
7. 从这以后，插件不再依赖绑定码，而是通过登录态查询默认身体

因此，六位码的角色应是：

- 首次配对凭证

而不是：

- 长期设备 ID
- 长期插件配置项

### 14.6.2 建议的最小接口

按当前阶段，后端最小可以先提供：

- `POST /openclaw/body/v1/pair/confirm`
  - 输入：`installationId`、`pairCode`
  - 作用：完成 OpenClaw 插件实例与设备的首次绑定

- `POST /openclaw/body/v1/pair/devices`
  - 输入：可选 `bodyType`、`onlineOnly`
  - 作用：返回当前可绑定的身体设备列表，便于插件或调试页展示待绑定 Otto 与其六位码

- `POST /openclaw/body/v1/me/default`
  - 输入：`installationId`
  - 作用：返回当前插件实例的默认身体

- `POST /openclaw/body/v1/me/devices`
  - 输入：`installationId`
  - 作用：返回当前插件实例已绑定的身体列表

并让现有动作接口支持：

- 显式传 `deviceId`
- 或在未传 `deviceId` 时，通过 `installationId` 自动解析默认身体

这样后续 `otto-body` 插件就可以从“静态 `defaultDeviceId`”逐步过渡到“动态默认身体解析”。

### 14.6.3 Otto 表情控制

Otto 这块不应只暴露舵机动作，还应把屏幕表情作为身体表达的一部分开放给 OpenClaw。

当前 `otto-robot` 板级实际已经内置了一组 Otto GIF 表情，核心别名包括：

- `staticstate` / `neutral` / `idle`
- `happy` / `laughing`
- `sad` / `crying`
- `anger` / `angry`
- `scare` / `surprised` / `shocked`
- `thinking` / `confused` / `embarrassed`

因此推荐能力模型是：

- 固件侧暴露 `self.screen.set_emotion`

### 14.6.4 当前联调里最容易踩的坑

如果你当前看到的现象是：

- Otto 连上小智后端智控台后
- 智控台展示过的六位绑定码消失
- OpenClaw 的“连接新 Otto”流程又要求输入六位数验证码

那么要明确区分两套完全不同的“六位码”：

1. 智控台 `activation_code`
   - 由管理端 `DeviceServiceImpl.deviceActivation(...)` 消费
   - 设备一旦完成智控台绑定，Redis 中的 `activation_code` 会被删除
   - 这就是为什么设备绑定后你再也看不到原来的六码

2. OpenClaw body pairing `pair_code`
   - 由 `xiaozhi-server` 的 `BodyGatewayRegistry` 单独生成并持久化
   - 不依赖智控台 `activation_code`
   - 设备已经绑定到智控台后，仍然可以继续用于 OpenClaw body 配对

当前仓库实际上已经内置了第二套机制，代码位置如下：

- [body_gateway_registry.py](../main/xiaozhi-server/core/body_gateway_registry.py)
- [openclaw_body_handler.py](../main/xiaozhi-server/core/api/openclaw_body_handler.py)

也就是说，当前正确做法不是“复用智控台那枚已经消费掉的 activation_code”，而是：

1. 让 Otto 正常连上 `xiaozhi-server`
2. 由 `BodyGatewayRegistry` 为该设备分配独立的 `pair_code`
3. OpenClaw 插件调用 body bridge 的配对接口完成绑定

当前可以直接这样排查和使用。

先列出可配对 Otto：

```bash
curl -H 'Content-Type: application/json' \
  -d '{}' \
  http://<server-ip>:8003/openclaw/body/v1/pair/devices
```

如果 Otto 已正常在线，返回结果里的设备对象会包含：

- `device_id`
- `pair_code`
- `online`
- `body_type`

其中 `pair_code` 才是现在应该填给 OpenClaw “连接新 Otto”界面的六位码。

然后执行首次绑定：

```bash
curl -H 'Content-Type: application/json' \
  -d '{"installationId":"<openclaw-installation-id>","pairCode":"<pair_code>"}' \
  http://<server-ip>:8003/openclaw/body/v1/pair/confirm
```

绑定完成后，后续动作接口就可以不再显式传 `deviceId`，改为传：

- `installationId`

由后端自动解析默认身体。

一句话结论：

- 智控台六码消失是正常行为
- OpenClaw 不应再依赖它
- 现在应切到 `body bridge pair_code` 这条独立链路
- 小智后端桥接 `POST /openclaw/body/v1/otto/emotion`
- OpenClaw 插件暴露 `otto_set_emotion`

这样 OpenClaw 既可以控制 Otto 的动作，也可以独立控制 Otto 的表情，而不是把“身体”仅理解为舵机动作。

### 14.7 当前方案与终态的关系

当前已经跑通的这套：

`OpenClaw -> xiaozhi body bridge -> Otto`

可以视为云桥接模式的“设备执行内核”。

也就是说，当前并不是走错方向，而是：

- 先完成了身体执行桥
- 后续只需在它上面再加：
  - 用户绑定
  - 默认身体解析
  - 插件登录态
  - 消费级配网与 OTA 体验

### 14.8 按这个方向接下来优先做什么

第一批最值得做的事情是：

1. 设计 body gateway 的设备注册表与绑定表
2. 设计“绑定码 / 二维码绑定”流程
3. 改造 `otto-body` 插件，使其支持从云端解析默认身体
4. 让设备首次联网后自动进入“待绑定”状态
5. 固化消费者首次使用流程文档

## 15. 一句话总结

这套方案的关键，不是让 `xiaozhi-server` 把设备工具“喂给” OpenClaw，而是让 `OpenClaw` 原生拥有 Otto 身体工具，再通过 `xiaozhi-server` 这层语音与设备桥把动作真正执行到板子上。
