import asyncio
import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.parse import urlparse, urlunparse

import websockets
from config.logger import setup_logging
from core.providers.llm.base import LLMProviderBase

TAG = __name__
logger = setup_logging()


class LLMProvider(LLMProviderBase):
    def __init__(self, config):
        self.base_url = config.get("base_url") or config.get("url") or "ws://localhost:18789"
        self.ws_url = self._normalize_ws_url(self.base_url)

        self.token = config.get("token") or config.get("api_key")
        self.password = config.get("password")

        timeout = config.get("timeout", 120)
        try:
            self.timeout = int(timeout)
        except (TypeError, ValueError):
            self.timeout = 120
        self.timeout = max(10, self.timeout)

        self.client_id = config.get("client_id", "gateway-client")
        self.client_mode = config.get("client_mode", "backend")
        self.client_version = config.get("client_version", "xiaozhi-openclaw")
        self.platform = config.get("platform", "linux")

        self.session_key = config.get("session_key", "agent:main:xiaozhi")
        self.session_per_device = self._to_bool(config.get("session_per_device", True))
        self.max_message_chars = self._to_int(config.get("max_message_chars", 12000), 12000)
        self.max_message_chars = max(2000, self.max_message_chars)

    @staticmethod
    def _to_bool(value):
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in ("true", "1", "yes", "on")

    @staticmethod
    def _to_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalize_ws_url(url):
        raw = str(url or "").strip()
        if not raw:
            return "ws://localhost:18789"
        if "://" not in raw:
            raw = f"ws://{raw}"
        parsed = urlparse(raw)
        scheme = parsed.scheme.lower()
        if scheme == "http":
            scheme = "ws"
        elif scheme == "https":
            scheme = "wss"
        path = parsed.path or "/"
        return urlunparse((scheme, parsed.netloc, path, "", parsed.query, ""))

    @staticmethod
    def _sanitize_session_fragment(text):
        safe = re.sub(r"[^0-9A-Za-z:_-]", "_", str(text or "default"))
        return safe[:80] if len(safe) > 80 else safe

    def _build_session_key(self, session_id):
        base = str(self.session_key or "").strip() or "agent:main:xiaozhi"
        if not self.session_per_device:
            return base
        suffix = self._sanitize_session_fragment(session_id or "default")
        return f"{base}:{suffix}"

    @staticmethod
    def normalize_dialogue(dialogue):
        for msg in dialogue:
            if "role" in msg and "content" not in msg:
                msg["content"] = ""
        return dialogue

    @staticmethod
    def _extract_plain_content(content):
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    text_parts.append(item["text"].strip())
            return "\n".join([x for x in text_parts if x]).strip()
        return ""

    def _compose_prompt(self, dialogue):
        # 优先取最近一条用户文本，避免把全部历史重复喂给 OpenClaw 会话。
        for msg in reversed(dialogue):
            if msg.get("role") != "user":
                continue
            user_text = self._extract_plain_content(msg.get("content"))
            if user_text:
                return user_text[: self.max_message_chars]

        # 没有用户输入时（例如工具递归轮次），退化为最近几条上下文摘要。
        lines = []
        for msg in dialogue[-6:]:
            role = str(msg.get("role", "user"))
            text = self._extract_plain_content(msg.get("content"))
            if not text:
                continue
            lines.append(f"{role}: {text}")
        if not lines:
            return "继续。"
        prompt = "请基于以下上下文继续回答：\n" + "\n".join(lines)
        return prompt[-self.max_message_chars :]

    @staticmethod
    def _extract_text_from_message(message):
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if str(item.get("type", "")).lower() == "text":
                    text = item.get("text")
                    if isinstance(text, str) and text:
                        text_parts.append(text)
            if text_parts:
                return "".join(text_parts)
        text = message.get("text")
        return text if isinstance(text, str) else ""

    @staticmethod
    def _extract_tool_calls_from_message(message):
        if not isinstance(message, dict):
            return []
        content = message.get("content")
        if not isinstance(content, list):
            return []

        tool_calls = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", "")).replace("_", "").lower()
            if item_type != "toolcall":
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            arguments = item.get("arguments")
            if isinstance(arguments, str):
                arguments_str = arguments
            elif arguments is None:
                arguments_str = "{}"
            else:
                arguments_str = json.dumps(arguments, ensure_ascii=False)
            tool_calls.append(
                {
                    "id": item.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                    "name": name.strip(),
                    "arguments": arguments_str,
                }
            )
        return tool_calls

    @staticmethod
    def _is_no_reply(text):
        return isinstance(text, str) and text.strip().upper() == "NO_REPLY"

    async def _recv_json(self, ws, timeout_s):
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout_s)
        return json.loads(raw)

    async def _send_req(self, ws, method, params, event_buffer, timeout_s):
        req_id = str(uuid.uuid4())
        await ws.send(
            json.dumps(
                {
                    "type": "req",
                    "id": req_id,
                    "method": method,
                    "params": params,
                },
                ensure_ascii=False,
            )
        )

        deadline = asyncio.get_running_loop().time() + timeout_s
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"OpenClaw request timeout: {method}")
            data = await self._recv_json(ws, remaining)
            msg_type = data.get("type")
            if msg_type == "event":
                event_buffer.append(data)
                continue
            if msg_type != "res" or data.get("id") != req_id:
                continue
            if data.get("ok"):
                return data.get("payload") or {}
            error = data.get("error") or {}
            raise RuntimeError(
                f"{method} failed: {error.get('code', 'UNKNOWN')} - {error.get('message', 'unknown error')}"
            )

    async def _connect_and_chat(self, session_key, prompt):
        event_buffer = []
        chunks = []
        full_text = ""
        tool_calls = []
        final_seen = False

        async with websockets.connect(
            self.ws_url,
            max_size=25 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        ) as ws:
            # 等待 connect.challenge
            challenge_deadline = asyncio.get_running_loop().time() + min(self.timeout, 15)
            while True:
                remaining = challenge_deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError("OpenClaw connect.challenge timeout")
                data = await self._recv_json(ws, remaining)
                if (
                    data.get("type") == "event"
                    and data.get("event") == "connect.challenge"
                ):
                    break
                event_buffer.append(data)

            auth = {}
            if self.token:
                auth["token"] = self.token
            if self.password:
                auth["password"] = self.password

            connect_params = {
                "minProtocol": 3,
                "maxProtocol": 3,
                "client": {
                    "id": self.client_id,
                    "version": self.client_version,
                    "platform": self.platform,
                    "mode": self.client_mode,
                    "instanceId": str(uuid.uuid4()),
                },
                "role": "operator",
                "scopes": ["operator.admin", "operator.approvals", "operator.pairing"],
                "caps": [],
                "auth": auth if auth else None,
            }
            if connect_params["auth"] is None:
                connect_params.pop("auth")

            await self._send_req(
                ws,
                "connect",
                connect_params,
                event_buffer=event_buffer,
                timeout_s=min(self.timeout, 20),
            )

            send_payload = await self._send_req(
                ws,
                "chat.send",
                {
                    "sessionKey": session_key,
                    "message": prompt,
                    "deliver": False,
                    "idempotencyKey": str(uuid.uuid4()),
                },
                event_buffer=event_buffer,
                timeout_s=min(self.timeout, 20),
            )
            run_id = send_payload.get("runId")

            deadline = asyncio.get_running_loop().time() + self.timeout
            while asyncio.get_running_loop().time() < deadline:
                if event_buffer:
                    data = event_buffer.pop(0)
                else:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        # OpenClaw 首个 chat 事件可能在 10 秒后才返回，
                        # 这里按总超时窗口轮询，避免把单次等待超时误判为整体失败。
                        data = await self._recv_json(ws, min(remaining, 10))
                    except (asyncio.TimeoutError, TimeoutError):
                        continue

                if data.get("type") != "event" or data.get("event") != "chat":
                    continue
                payload = data.get("payload") or {}
                if payload.get("sessionKey") != session_key:
                    continue
                event_run_id = payload.get("runId")
                if run_id and event_run_id and event_run_id != run_id:
                    continue

                message = payload.get("message")
                if isinstance(message, dict):
                    current_text = self._extract_text_from_message(message)
                    if current_text:
                        if current_text.startswith(full_text):
                            delta = current_text[len(full_text) :]
                            full_text = current_text
                        else:
                            delta = current_text
                            full_text = current_text
                        if delta:
                            chunks.append(delta)
                    latest_calls = self._extract_tool_calls_from_message(message)
                    if latest_calls:
                        tool_calls = latest_calls

                state = payload.get("state")
                if state == "error":
                    raise RuntimeError(payload.get("errorMessage") or "OpenClaw chat error")
                if state in ("final", "aborted"):
                    final_seen = True
                    break

            # 部分情况下 final 不带 message，兜底从 history 拿最后一条 assistant。
            if not full_text and not tool_calls:
                try:
                    history_payload = await self._send_req(
                        ws,
                        "chat.history",
                        {"sessionKey": session_key, "limit": 4},
                        event_buffer=event_buffer,
                        timeout_s=min(self.timeout, 15),
                    )
                    messages = history_payload.get("messages") or []
                    for msg in reversed(messages):
                        if str(msg.get("role", "")).lower() != "assistant":
                            continue
                        full_text = self._extract_text_from_message(msg)
                        tool_calls = self._extract_tool_calls_from_message(msg)
                        if full_text or tool_calls:
                            break
                except Exception as e:
                    logger.bind(tag=TAG).warning(f"OpenClaw history fallback failed: {e}")

        if not chunks and full_text:
            chunks = [full_text]

        return {
            "chunks": chunks,
            "text": full_text,
            "tool_calls": tool_calls,
        }

    @staticmethod
    def _make_tool_delta(tool_call, index):
        return SimpleNamespace(
            id=tool_call.get("id") or f"call_{uuid.uuid4().hex[:8]}",
            index=index,
            function=SimpleNamespace(
                name=tool_call.get("name") or "",
                arguments=tool_call.get("arguments") or "{}",
            ),
        )

    @staticmethod
    def _run_coro(coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        # 当前线程已有事件循环时，转到新线程执行，避免 RuntimeError。
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(lambda: asyncio.run(coro)).result()

    def response(self, session_id, dialogue, **kwargs):
        try:
            dialogue = self.normalize_dialogue(dialogue)
            prompt = self._compose_prompt(dialogue)
            session_key = self._build_session_key(session_id)
            result = self._run_coro(self._connect_and_chat(session_key, prompt))

            emitted = False
            for chunk in result.get("chunks", []):
                if chunk and not self._is_no_reply(chunk):
                    emitted = True
                    yield chunk

            if not emitted:
                text = result.get("text", "")
                if text and not self._is_no_reply(text):
                    yield text
        except Exception as e:
            logger.bind(tag=TAG).error(
                f"Error in OpenClaw response generation: {type(e).__name__}: {e!r}"
            )
            yield f"【OpenClaw服务响应异常: {e}】"

    def response_with_functions(self, session_id, dialogue, functions=None, **kwargs):
        try:
            dialogue = self.normalize_dialogue(dialogue)
            prompt = self._compose_prompt(dialogue)
            session_key = self._build_session_key(session_id)
            result = self._run_coro(self._connect_and_chat(session_key, prompt))

            emitted = False
            for chunk in result.get("chunks", []):
                if chunk and not self._is_no_reply(chunk):
                    emitted = True
                    yield chunk, None

            tool_calls = result.get("tool_calls") or []
            if tool_calls:
                tool_deltas = [
                    self._make_tool_delta(tool_call, idx)
                    for idx, tool_call in enumerate(tool_calls)
                ]
                yield None, tool_deltas
                return

            if not emitted:
                text = result.get("text", "")
                if text and not self._is_no_reply(text):
                    yield text, None
        except Exception as e:
            logger.bind(tag=TAG).error(
                f"Error in OpenClaw function call streaming: {type(e).__name__}: {e!r}"
            )
            yield f"【OpenClaw服务响应异常: {e}】", None
