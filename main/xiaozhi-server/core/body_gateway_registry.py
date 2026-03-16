import json
import os
import random
import time
from copy import deepcopy

from config.config_loader import get_project_dir
from config.logger import setup_logging

TAG = __name__


class BodyGatewayRegistry:
    """Lightweight registry for devices, pair codes, and OpenClaw body bindings."""

    def __init__(self):
        self.logger = setup_logging()
        self._lock = None
        self._data_path = os.path.join(get_project_dir(), "data", "body_gateway_registry.json")
        self._state = {
            "devices": {},
            "bindings": {},
        }

    async def start(self):
        import asyncio

        if self._lock is None:
            self._lock = asyncio.Lock()
        await self._load()

    async def _load(self):
        async with self._lock:
            os.makedirs(os.path.dirname(self._data_path), exist_ok=True)
            if not os.path.exists(self._data_path):
                await self._save_unlocked()
                return
            try:
                with open(self._data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._state["devices"] = data.get("devices", {}) or {}
                    self._state["bindings"] = data.get("bindings", {}) or {}
            except Exception as e:
                self.logger.bind(tag=TAG).warning(f"加载 body gateway registry 失败，使用空状态: {e}")

    async def _save_unlocked(self):
        tmp_path = self._data_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, self._data_path)

    def _generate_pair_code_unlocked(self):
        used = {
            device.get("pair_code", "")
            for device in self._state["devices"].values()
            if isinstance(device, dict)
        }
        for _ in range(20):
            code = f"{random.randint(0, 999999):06d}"
            if code not in used:
                return code
        raise RuntimeError("无法生成唯一的六位绑定码")

    async def upsert_device_connection(self, device_id: str, client_id: str = "", client_ip: str = ""):
        if not device_id:
            return
        async with self._lock:
            device = self._state["devices"].get(device_id, {})
            if not device.get("pair_code"):
                device["pair_code"] = self._generate_pair_code_unlocked()
            device["device_id"] = device_id
            device["client_id"] = client_id or device.get("client_id", "")
            device["client_ip"] = client_ip or device.get("client_ip", "")
            device["online"] = True
            device["last_seen_at"] = int(time.time())
            self._state["devices"][device_id] = device
            await self._save_unlocked()

    async def mark_device_offline(self, device_id: str):
        if not device_id:
            return
        async with self._lock:
            device = self._state["devices"].get(device_id)
            if not isinstance(device, dict):
                return
            device["online"] = False
            device["last_seen_at"] = int(time.time())
            await self._save_unlocked()

    async def update_device_profile(self, device_id: str, **fields):
        if not device_id:
            return
        async with self._lock:
            device = self._state["devices"].get(device_id, {})
            if not device.get("pair_code"):
                device["pair_code"] = self._generate_pair_code_unlocked()
            device["device_id"] = device_id
            device["last_seen_at"] = int(time.time())
            for key, value in fields.items():
                if value is not None:
                    device[key] = value
            self._state["devices"][device_id] = device
            await self._save_unlocked()

    async def get_device_by_pair_code(self, pair_code: str):
        if not pair_code:
            return None
        async with self._lock:
            for device in self._state["devices"].values():
                if isinstance(device, dict) and device.get("pair_code") == pair_code:
                    return deepcopy(device)
        return None

    async def list_devices(self, body_type: str = "", online_only: bool = False):
        async with self._lock:
            results = []
            for device in self._state["devices"].values():
                if not isinstance(device, dict):
                    continue
                if body_type and device.get("body_type") != body_type:
                    continue
                if online_only and not device.get("online"):
                    continue
                results.append(deepcopy(device))
            results.sort(
                key=lambda item: (
                    0 if item.get("online") else 1,
                    -int(item.get("last_seen_at") or 0),
                )
            )
            return results

    async def bind_installation(self, installation_id: str, pair_code: str, label: str = ""):
        if not installation_id:
            raise ValueError("installationId不能为空")
        if not pair_code:
            raise ValueError("pairCode不能为空")
        async with self._lock:
            target_device = None
            for device in self._state["devices"].values():
                if isinstance(device, dict) and device.get("pair_code") == pair_code:
                    target_device = device
                    break
            if target_device is None:
                raise ValueError("pairCode无效")

            binding = self._state["bindings"].get(installation_id, {})
            devices = binding.get("devices", [])
            device_id = target_device["device_id"]
            if device_id not in devices:
                devices.append(device_id)

            binding["installation_id"] = installation_id
            binding["devices"] = devices
            binding["default_device_id"] = device_id
            binding["updated_at"] = int(time.time())
            if label:
                binding["label"] = label
            self._state["bindings"][installation_id] = binding
            await self._save_unlocked()
            return deepcopy(binding)

    async def get_default_device(self, installation_id: str):
        if not installation_id:
            return None
        async with self._lock:
            binding = self._state["bindings"].get(installation_id)
            if not isinstance(binding, dict):
                return None
            device_id = binding.get("default_device_id")
            if not device_id:
                return None
            device = self._state["devices"].get(device_id)
            if not isinstance(device, dict):
                return None
            return deepcopy(device)

    async def list_bound_devices(self, installation_id: str):
        if not installation_id:
            return []
        async with self._lock:
            binding = self._state["bindings"].get(installation_id)
            if not isinstance(binding, dict):
                return []
            results = []
            for device_id in binding.get("devices", []):
                device = self._state["devices"].get(device_id)
                if isinstance(device, dict):
                    results.append(deepcopy(device))
            return results
