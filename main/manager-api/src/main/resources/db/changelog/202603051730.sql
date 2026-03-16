-- OpenClaw LLM provider
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_LLM_openclaw';
INSERT INTO `ai_model_provider`
(`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES
('SYSTEM_LLM_openclaw', 'LLM', 'openclaw', 'OpenClaw网关',
 '[{"key":"base_url","label":"网关地址(WS)","type":"string"},{"key":"token","label":"Gateway Token","type":"string"},{"key":"password","label":"Gateway Password","type":"string"},{"key":"session_key","label":"会话键前缀","type":"string"},{"key":"session_per_device","label":"按设备会话隔离","type":"boolean"},{"key":"timeout","label":"超时时间(秒)","type":"number"}]',
 15, 1, NOW(), 1, NOW());

DELETE FROM `ai_model_config` WHERE `id` = 'LLM_OpenClawLLM';
INSERT INTO `ai_model_config`
VALUES
('LLM_OpenClawLLM', 'LLM', 'OpenClawLLM', 'OpenClaw网关', 0, 1,
 '{"type": "openclaw", "base_url": "ws://openclaw-gateway:18789", "token": "", "session_key": "agent:main:xiaozhi", "session_per_device": true, "timeout": 120}',
 'https://github.com/cursor/openclaw',
 'OpenClaw 配置说明：\n1. base_url 填写 OpenClaw 网关 WebSocket 地址，如 ws://openclaw-gateway:18789\n2. token/password 至少填一个（按你的网关鉴权方式）\n3. 建议保留 session_per_device=true，避免多设备会话串扰',
 15, NULL, NULL, NULL, NULL);
