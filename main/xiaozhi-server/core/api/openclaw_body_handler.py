import json
from aiohttp import web

from core.api.base_handler import BaseHandler
from core.providers.tools.device_mcp.mcp_handler import call_mcp_tool
from core.utils.util import sanitize_tool_name

TAG = __name__


class OpenClawBodyHandler(BaseHandler):
    """给 OpenClaw 原生 body tools 复用的小智设备执行桥。"""

    def __init__(self, config: dict, websocket_server):
        super().__init__(config)
        self.websocket_server = websocket_server
        self.bridge_token = (
            config.get("openclaw_body_bridge", {}).get("token", "").strip()
        )

    def _json_response(self, payload: dict, status: int = 200):
        response = web.Response(
            text=json.dumps(payload, separators=(",", ":")),
            content_type="application/json",
            status=status,
        )
        self._add_cors_headers(response)
        return response

    def _check_auth(self, request) -> bool:
        if not self.bridge_token:
            return True

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:] == self.bridge_token
        return False

    def _extract_installation_id(self, request, body: dict) -> str:
        return (
            body.get("installationId")
            or body.get("installation_id")
            or request.headers.get("X-OpenClaw-Installation", "")
        ).strip()

    async def _resolve_device_id(self, request, body: dict):
        device_id = body.get("deviceId") or body.get("device_id")
        if device_id:
            return device_id

        installation_id = self._extract_installation_id(request, body)
        if not installation_id:
            raise ValueError("deviceId不能为空，且未提供installationId")

        device = await self.websocket_server.body_registry.get_default_device(
            installation_id
        )
        if not device:
            raise ValueError(f"installationId={installation_id} 当前没有默认身体")
        return device.get("device_id")

    async def _get_active_conn(self, device_id: str):
        if not device_id:
            raise ValueError("deviceId不能为空")

        conn = await self.websocket_server.get_device_connection(device_id)
        if conn is None:
            raise ValueError(f"设备 {device_id} 当前不在线")
        if not hasattr(conn, "mcp_client") or conn.mcp_client is None:
            raise ValueError(f"设备 {device_id} 的MCP客户端未初始化")
        if not await conn.mcp_client.is_ready():
            raise ValueError(f"设备 {device_id} 的MCP工具尚未准备就绪")
        return conn

    async def _call_device_tool(self, device_id: str, tool_name: str, arguments: dict):
        conn = await self._get_active_conn(device_id)
        sanitized_name = sanitize_tool_name(tool_name)
        result = await call_mcp_tool(
            conn,
            conn.mcp_client,
            sanitized_name,
            arguments or {},
        )

        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return {"raw": result}
        return result

    async def handle_action(self, request):
        try:
            if not self._check_auth(request):
                return self._json_response({"ok": False, "error": "unauthorized"}, 401)

            body = await request.json()
            device_id = await self._resolve_device_id(request, body)
            action = body.get("action")
            if not action:
                raise ValueError("action不能为空")

            arguments = {"action": action}
            for source_key, target_key in (
                ("speed", "speed"),
                ("steps", "steps"),
                ("amount", "amount"),
                ("armSwing", "arm_swing"),
                ("arm_swing", "arm_swing"),
            ):
                value = body.get(source_key)
                if value is not None:
                    arguments[target_key] = value

            result = await self._call_device_tool(
                device_id, "self.otto.action", arguments
            )
            return self._json_response({"ok": True, "result": result})
        except ValueError as e:
            return self._json_response({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"otto action bridge error: {e}")
            return self._json_response({"ok": False, "error": str(e)}, 500)

    async def handle_stop(self, request):
        try:
            if not self._check_auth(request):
                return self._json_response({"ok": False, "error": "unauthorized"}, 401)

            body = await request.json()
            device_id = await self._resolve_device_id(request, body)
            result = await self._call_device_tool(device_id, "self.otto.stop", {})
            return self._json_response({"ok": True, "result": result})
        except ValueError as e:
            return self._json_response({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"otto stop bridge error: {e}")
            return self._json_response({"ok": False, "error": str(e)}, 500)

    async def handle_status(self, request):
        try:
            if not self._check_auth(request):
                return self._json_response({"ok": False, "error": "unauthorized"}, 401)

            body = await request.json()
            device_id = await self._resolve_device_id(request, body)
            result = await self._call_device_tool(device_id, "self.otto.get_status", {})
            return self._json_response({"ok": True, "result": result})
        except ValueError as e:
            return self._json_response({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"otto status bridge error: {e}")
            return self._json_response({"ok": False, "error": str(e)}, 500)

    async def handle_theme(self, request):
        try:
            if not self._check_auth(request):
                return self._json_response({"ok": False, "error": "unauthorized"}, 401)

            body = await request.json()
            device_id = await self._resolve_device_id(request, body)
            theme = body.get("theme")
            if not theme:
                raise ValueError("theme不能为空")

            result = await self._call_device_tool(
                device_id, "self.screen.set_theme", {"theme": theme}
            )
            return self._json_response({"ok": True, "result": result})
        except ValueError as e:
            return self._json_response({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"otto theme bridge error: {e}")
            return self._json_response({"ok": False, "error": str(e)}, 500)

    async def handle_emotion(self, request):
        try:
            if not self._check_auth(request):
                return self._json_response({"ok": False, "error": "unauthorized"}, 401)

            body = await request.json()
            device_id = await self._resolve_device_id(request, body)
            emotion = (body.get("emotion") or "").strip()
            if not emotion:
                raise ValueError("emotion不能为空")

            result = await self._call_device_tool(
                device_id, "self.screen.set_emotion", {"emotion": emotion}
            )
            return self._json_response({"ok": True, "result": result})
        except ValueError as e:
            return self._json_response({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"otto emotion bridge error: {e}")
            return self._json_response({"ok": False, "error": str(e)}, 500)

    async def handle_pair_confirm(self, request):
        try:
            if not self._check_auth(request):
                return self._json_response({"ok": False, "error": "unauthorized"}, 401)

            body = await request.json()
            installation_id = self._extract_installation_id(request, body)
            pair_code = (body.get("pairCode") or body.get("pair_code") or "").strip()
            label = (body.get("label") or "").strip()
            binding = await self.websocket_server.body_registry.bind_installation(
                installation_id, pair_code, label
            )
            return self._json_response({"ok": True, "binding": binding})
        except ValueError as e:
            return self._json_response({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"pair confirm error: {e}")
            return self._json_response({"ok": False, "error": str(e)}, 500)

    async def handle_pair_devices(self, request):
        try:
            if not self._check_auth(request):
                return self._json_response({"ok": False, "error": "unauthorized"}, 401)

            body = await request.json() if request.can_read_body else {}
            body_type = (body.get("bodyType") or body.get("body_type") or "otto").strip()
            online_only = body.get("onlineOnly")
            if online_only is None:
                online_only = True
            devices = await self.websocket_server.body_registry.list_devices(
                body_type=body_type,
                online_only=bool(online_only),
            )
            return self._json_response({"ok": True, "devices": devices})
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"pair devices error: {e}")
            return self._json_response({"ok": False, "error": str(e)}, 500)

    async def handle_default_body(self, request):
        try:
            if not self._check_auth(request):
                return self._json_response({"ok": False, "error": "unauthorized"}, 401)

            body = await request.json()
            installation_id = self._extract_installation_id(request, body)
            if not installation_id:
                raise ValueError("installationId不能为空")
            device = await self.websocket_server.body_registry.get_default_device(
                installation_id
            )
            if not device:
                return self._json_response({"ok": True, "device": None})
            return self._json_response({"ok": True, "device": device})
        except ValueError as e:
            return self._json_response({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"default body error: {e}")
            return self._json_response({"ok": False, "error": str(e)}, 500)

    async def handle_list_bodies(self, request):
        try:
            if not self._check_auth(request):
                return self._json_response({"ok": False, "error": "unauthorized"}, 401)

            body = await request.json()
            installation_id = self._extract_installation_id(request, body)
            if not installation_id:
                raise ValueError("installationId不能为空")
            devices = await self.websocket_server.body_registry.list_bound_devices(
                installation_id
            )
            return self._json_response({"ok": True, "devices": devices})
        except ValueError as e:
            return self._json_response({"ok": False, "error": str(e)}, 400)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"list bodies error: {e}")
            return self._json_response({"ok": False, "error": str(e)}, 500)
