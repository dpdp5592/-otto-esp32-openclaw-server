# 小智服务端外部 Agent 对接说明

> 如果目标不是“把 OpenClaw 当作小智的一个 LLM Provider”，而是“让 OpenClaw 原生拥有 Otto 身体工具、小智只做执行桥”，请直接参考：
> [openclaw-otto-body-replication-guide.md](./openclaw-otto-body-replication-guide.md)

## 1. 文档目的

本文档面向外部 Agent 开发团队，说明以下内容：

1. `xiaozhi-esp32-server` 在整体系统中的职责与边界。
2. 当前 `openclaw` 接入小智服务端的实现方式。
3. 后续如将 `openclaw` 替换为其他 Agent，需要满足的接口行为与兼容要求。

本文档的核心结论如下：

- ESP32 设备 **不会直接对接 `openclaw` 或其他 Agent**。
- ESP32 设备始终连接 `xiaozhi-esp32-server` 的 WebSocket 接口。
- `openclaw` 当前扮演的是 **小智服务端内部的 LLM Provider / Agent 网关适配层**。
- 后续其他 Agent 的推荐接入方式，是复用当前 Provider 适配模式，或提供与当前 Provider 兼容的网关接口，再由小智服务端统一转发。

## 2. 项目整体摘要

根据仓库根目录 [README.md](../README.md)，`xiaozhi-esp32-server` 是开源硬件项目 `xiaozhi-esp32` 的后端服务，技术栈包含 Python、Java、Vue，支持 WebSocket、MQTT+UDP、MCP 接入点、语音识别、语音合成、视觉模型、插件和知识库。

从实际架构看，该项目可分为三层。

### 2.1 Python 核心服务 `main/xiaozhi-server`

Python 核心服务负责实时设备交互主链路，包括：

- 接收 ESP32 的 WebSocket 连接。
- 接收设备上行音频流。
- 调用 ASR 将语音转换为文本。
- 调用 LLM / Agent 生成回复或工具调用。
- 执行工具、插件、MCP、设备 IoT 指令。
- 调用 TTS 生成语音并下发给设备。

该部分采用 **Provider 模式** 设计：

- ASR、LLM、VLLM、TTS、Intent、Memory 都有统一抽象接口。
- 不同厂商或不同实现以 provider 类形式接入。
- 切换模型或外部服务时，无需改动主流程代码。

### 2.2 Java 管理端 `main/manager-api`

Java 管理端主要负责：

- 模型配置管理。
- 智能体配置管理。
- 设备管理。
- 参数校验。
- 向 Python 服务端提供配置。

在完整模块部署模式下，Python 服务端的部分配置并不只读取本地 `config.yaml`，还会通过 Java API 拉取。

### 2.3 Vue 控制台 `main/manager-web`

控制台主要负责：

- 页面化配置模型。
- 为智能体选择 LLM / ASR / TTS / Intent。
- 对可选项做约束，例如仅部分 LLM 类型允许 `function_call`。

## 3. 设备链路工作方式

当前面向 ESP32 的主链路如下：

1. ESP32 连接 `xiaozhi-server` 的 WebSocket 地址，例如 `/xiaozhi/v1/`。
2. 设备将语音音频流上传到服务端。
3. 服务端完成 VAD、ASR。
4. 服务端将当前对话上下文交给 LLM Provider。
5. 如果 LLM 返回普通文本，服务端进入 TTS 并下发语音。
6. 如果 LLM 返回工具调用，服务端执行工具，再将工具结果继续交给 LLM。
7. 最终文本转为语音后返回给 ESP32。

因此，对设备侧而言，外部 Agent 的存在是透明的。设备始终面对的是小智原生协议，而不是第三方 Agent 协议。

## 4. 当前 ESP32 板级配置的定位

当前设备板级目录为：

- `/home/dp/workspace/xiaozhi_row/xiaozhi-esp32/main/boards/bread-compact-wifi-lcd`

根据该目录下的 [config.h](/home/dp/workspace/xiaozhi_row/xiaozhi-esp32/main/boards/bread-compact-wifi-lcd/config.h)，当前板级配置主要定义：

- 音频输入采样率 `16000`
- 音频输出采样率 `24000`
- I2S 引脚
- LCD 引脚
- 板载按键 / LED
- 是否禁用 LVGL 显示和 LCD Push Server

这说明当前板级差异主要属于 **硬件驱动层**，并不改变小智设备与服务端之间的协议本质。  
因此，后续 Agent 接入工作的重点仍然是 **服务端 LLM/工具调用适配**，而非该板级目录本身。

## 5. 当前 `openclaw` 的接入方式

### 5.1 接入位置

`openclaw` 当前已经作为 Python 侧 LLM Provider 接入：

- [main/xiaozhi-server/core/providers/llm/openclaw/openclaw.py](../main/xiaozhi-server/core/providers/llm/openclaw/openclaw.py)

Provider 的动态加载入口为：

- [main/xiaozhi-server/core/utils/llm.py](../main/xiaozhi-server/core/utils/llm.py)

该入口会根据配置中的 `type` 或 provider 名称动态实例化对应实现。

### 5.2 配置层

默认配置中已经加入 `OpenClawLLM`：

- [main/xiaozhi-server/config.yaml](../main/xiaozhi-server/config.yaml)

关键配置项包括：

- `type: openclaw`
- `base_url`: OpenClaw 网关 WebSocket 地址
- `token`
- `password`
- `session_key`
- `session_per_device`
- `timeout`

说明如下：

- `session_key` 为会话前缀。
- `session_per_device=true` 时，服务端会将设备会话 ID 拼接到 `session_key` 后面，以避免多设备串会话。

### 5.3 管理后台层

除 Python 核心服务外，管理端也已补充 `openclaw` 相关识别逻辑。

涉及位置包括：

- [main/manager-api/src/main/resources/db/changelog/202603051730.sql](../main/manager-api/src/main/resources/db/changelog/202603051730.sql)
  - 新增 `OpenClaw` 模型提供商与默认模型配置。
- [main/manager-api/src/main/java/xiaozhi/modules/agent/service/impl/AgentServiceImpl.java](../main/manager-api/src/main/java/xiaozhi/modules/agent/service/impl/AgentServiceImpl.java)
  - 将 `openclaw` 视为允许 `function_call` 的 LLM 类型。
- [main/manager-api/src/main/java/xiaozhi/modules/model/service/impl/ModelConfigServiceImpl.java](../main/manager-api/src/main/java/xiaozhi/modules/model/service/impl/ModelConfigServiceImpl.java)
  - 将 `openclaw` 作为合法 LLM 类型。
- [main/manager-web/src/views/roleConfig.vue](../main/manager-web/src/views/roleConfig.vue)
  - 当 LLM 类型为 `openclaw` 时，前端允许选择 `Intent_function_call`。

这意味着当前 `openclaw` 接入已贯通以下层面：

- Python 运行时
- Java 配置校验
- Web 控制台可选项

### 5.4 运行机制

`openclaw.py` 的核心流程如下：

1. 读取配置中的 OpenClaw 网关地址和认证信息。
2. 建立到 OpenClaw Gateway 的 WebSocket 连接。
3. 等待 `connect.challenge`。
4. 发送 `connect` 请求完成握手。
5. 发送 `chat.send`，将用户当前问题发给 OpenClaw。
6. 持续监听 `chat` 事件，并提取：
   - 增量文本回复
   - tool call 信息
   - 结束状态
7. 如最终事件中未取得完整 assistant 消息，则调用 `chat.history` 做兜底。

## 6. 当前 `openclaw` Provider 的输入输出约束

这是后续 Agent 团队最需要关注的部分。

### 6.1 小智服务端传给 `openclaw` 的内容

当前 `openclaw` provider 并未直接传递完整对话数组，而是做了简化处理：

- 优先提取最近一条 `user` 文本消息作为 prompt。
- 在没有明确用户文本时，退化为最近几轮上下文摘要。

因此，当前 OpenClaw 接口拿到的主输入本质上是：

- `sessionKey`
- 一段用户文本 `message`

而不是 OpenAI 风格完整 `messages[]`。

这也是当前实现的重要边界：

- 小智服务端维护本地对话历史。
- `openclaw` 主要依赖自身的 `sessionKey` 保持会话状态。

因此，如后续 Agent 沿用该模式，则需要支持 **按 `sessionKey` 维持服务端会话状态**。

### 6.2 小智服务端期望 `openclaw` 返回的内容

当前 provider 会从 OpenClaw 事件中提取两类结果。

#### 1. 文本结果

服务端接受流式文本增量，并在本地拼接为完整回复文本。

#### 2. 工具调用结果

服务端会从返回消息结构中提取 `tool_call` 风格内容，并转换为小智内部统一格式：

- `id`
- `name`
- `arguments`

之后交给小智统一工具处理器执行。

### 6.3 返回工具调用后的后续流程

后续流程如下：

1. `ConnectionHandler` 收到 provider 的 `tool_calls`。
2. 小智服务端根据 `name + arguments` 执行本地注册工具。
3. 工具结果按统一格式回写到对话历史。
4. 如工具结果要求继续交给 LLM，总流程会再次递归进入 LLM。

因此，外部 Agent 当前并不直接执行 ESP32 设备动作，而是：

- 负责决策调用哪个工具；
- 实际执行工具的是小智服务端。

这一边界对后续系统分工非常重要。

## 7. 当前 `openclaw` 接入对 ESP32 的真实意义

从系统边界看，当前实现并不是“`openclaw` 直接接入 ESP32”，而是：

**ESP32 -> 小智服务端 -> OpenClaw Gateway -> 小智工具系统 -> ESP32**

因此，当前 `openclaw` 的作用主要是：

- 验证外部 Agent / 网关是否可以替代原有 LLM 决策层。
- 验证工具调用链路是否可运行。
- 验证多设备会话隔离是否成立。
- 为后续正式 Agent 留出标准接入位。

## 8. 后续正式 Agent 需要满足的最小对接能力

如果后续将 `openclaw` 替换为其他 Agent，建议至少满足以下能力。

### 8.1 必备能力

1. 支持按会话标识维持上下文
   - 最好支持 `sessionKey`
   - 至少支持“小智每个设备一个独立会话”

2. 支持返回普通文本
   - 可为流式
   - 也可先从非流式兼容开始

3. 支持返回结构化工具调用
   - 至少包含 `name`
   - 至少包含 `arguments`
   - 最好包含 `id`

4. 支持明确结束态
   - 否则服务端难以判断本轮何时完成

5. 支持异常可观测
   - 鉴权失败
   - 超时
   - 会话不存在
   - 参数非法
   - 内部错误

### 8.2 强烈建议能力

1. 支持流式输出
   - 小智链路中 TTS 为边收边播，流式输出体验更好

2. 工具调用与文本输出分离
   - 可避免服务端再从自然语言中解析 JSON

3. 支持会话历史回查
   - 当前 `openclaw` provider 已使用 `chat.history` 作为兜底逻辑

4. 支持幂等请求
   - 当前接法中已带 `idempotencyKey`

## 9. 推荐的 Agent 网关接口契约

如果后续不继续使用 OpenClaw 协议，建议按照最小网关契约提供能力，以降低小智侧适配成本。

### 9.1 请求侧

建议至少包含：

- `session_key`
- `message`
- `device_id`
- `request_id`
- `capabilities`

其中 `capabilities` 可用于声明是否允许工具调用等能力。

可选字段包括：

- `history`
- `system_prompt`
- `tools`

### 9.2 响应侧

建议统一成事件流，并至少包含以下事件类型：

- `message_delta`
  - 文本增量
- `tool_call`
  - 工具名和参数
- `final`
  - 最终结束
- `error`
  - 错误

其中 `tool_call` 最少应包含：

- `id`
- `name`
- `arguments`

## 10. 推荐分工方式

### 10.1 小智服务端负责

- 设备 WebSocket 协议保持不变。
- ASR / TTS / 工具执行 / IoT / MCP 继续由小智侧负责。
- 外部 Agent 仅接入“文本问题 + 会话”这一层。
- 将 Agent 输出统一转换为小智内部 `text` 或 `tool_calls`。

### 10.2 Agent 团队负责

- 维护多轮上下文。
- 决策是否调用工具。
- 输出结构化工具调用。
- 保证接口稳定、时延可接受、异常可追踪。

这种分工的优势是：

- ESP32 固件无需随 Agent 频繁调整协议。
- 小智现有工具生态无需迁移。
- 后续替换不同 Agent 时影响面最小。

## 11. 当前实现中的注意点和风险

### 11.1 当前 `openclaw` provider 未显式下发完整 `functions` 描述

`response_with_functions()` 虽然接收 `functions` 参数，但当前 [openclaw.py](../main/xiaozhi-server/core/providers/llm/openclaw/openclaw.py) 并未将这份工具 schema 发送给 OpenClaw。  
这意味着：

- 要么 OpenClaw 侧已预置可用工具信息；
- 要么当前阶段仅验证基础调用链；
- 如后续 Agent 需要动态感知工具列表，则仍需扩展协议。

### 11.2 当前 prompt 组装方式偏轻量

当前 provider 主要取“最近一条用户消息”，而不是完整 `messages[]`。  
如果后续 Agent 很依赖显式历史输入，而不是依赖 `sessionKey` 持久化状态，则该部分还需升级。

### 11.3 真正设备控制仍位于小智内部工具层

当前 Agent 的职责是输出工具调用意图，而不是直接控制 ESP32。  
如果后续某一 Agent 方案希望直接控制设备，需要重新划分系统边界，否则容易与小智现有工具体系重复。

## 12. 建议的后续实施路线

### 阶段一：继续使用 `openclaw` 完成联调

建议先完成以下验证：

- 会话隔离
- 工具调用格式
- 整体时延
- 异常重试与超时表现

### 阶段二：抽象通用 `Agent Gateway Provider`

建议将当前 [openclaw.py](../main/xiaozhi-server/core/providers/llm/openclaw/openclaw.py) 视为第一版样板，后续进一步抽象为：

- `agent_gateway_base.py`
- `openclaw.py`
- `custom_agent.py`

这样在替换不同 Agent 时，无需将协议细节继续混入主流程。

### 阶段三：与正式 Agent 团队冻结接口

建议尽早冻结以下内容：

- 鉴权方式
- 会话字段
- 消息事件格式
- 工具调用结构
- 超时和错误码
- 是否需要动态下发 tools schema

## 13. 结论

当前实现并不是“让 `openclaw` 直接操控 ESP32 固件”，而是“将 `openclaw` 接成小智服务端中的外部 Agent / LLM 决策层”。  
后续正式 Agent 只要满足这一 Provider 层的输入输出契约，即可在不修改 ESP32 主协议的前提下替换 `openclaw`。
