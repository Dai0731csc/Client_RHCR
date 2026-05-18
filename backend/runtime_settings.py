"""Mutable client settings (transport, cloud, local topology) applied without restart."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .config import (
    CLOUD_CONFIG_PATH,
    CONFIG_DIR,
    DEFAULT_TRANSPORT_MODE,
    DEFAULT_TRANSPORT_MODES,
    SUPPORTED_TRANSPORT_MODES,
    _as_bool,
    normalize_transport_mode,
)

_RUNTIME: "ClientRuntimeSettings | None" = None


def _read_cloud_file() -> dict[str, Any]:
    if not CLOUD_CONFIG_PATH.is_file():
        return {}
    with CLOUD_CONFIG_PATH.open(encoding="utf-8") as config_file:
        data = json.load(config_file)
    if not isinstance(data, dict):
        raise ValueError(f"{CLOUD_CONFIG_PATH} must contain a JSON object")
    return data


def _resolve_status_selection(selections, *, selection_name: str, fallback: str) -> str:
    if isinstance(selections, dict):
        enabled_items: list[str] = []
        for item_id, item_data in selections.items():
            status = item_data.get("status") if isinstance(item_data, dict) else item_data
            if bool(status):
                enabled_items.append(str(item_id).strip())
        enabled_items = [item_id for item_id in enabled_items if item_id]
        if len(enabled_items) > 1:
            raise ValueError(
                f"{selection_name} has multiple entries with status=true: "
                + ", ".join(enabled_items)
            )
        if len(enabled_items) == 1:
            return enabled_items[0]
    return fallback


def _transport_modes_for_mode(mode: str) -> dict[str, bool]:
    normalized = normalize_transport_mode(mode)
    if normalized not in SUPPORTED_TRANSPORT_MODES:
        raise ValueError(f"Unsupported transport_mode={mode!r}")
    return {key: key == normalized for key in SUPPORTED_TRANSPORT_MODES}


def _normalize_transport_modes(raw_modes: Any) -> dict[str, bool]:
    base = {key: bool(DEFAULT_TRANSPORT_MODES.get(key)) for key in SUPPORTED_TRANSPORT_MODES}
    if isinstance(raw_modes, dict):
        for key in SUPPORTED_TRANSPORT_MODES:
            if key in raw_modes:
                base[key] = _as_bool(raw_modes.get(key), default=False)
    return base


class ClientRuntimeSettings:
    def __init__(self, data: dict[str, Any] | None = None):
        self._data = deepcopy(data) if data else {}

    @classmethod
    def from_cloud_file(cls) -> "ClientRuntimeSettings":
        return cls(_read_cloud_file())

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    @property
    def transport_mode(self) -> str:
        modes = _normalize_transport_modes(
            self._data.get("transport_modes") or DEFAULT_TRANSPORT_MODES
        )
        enabled = [mode for mode, on in modes.items() if on]
        if len(enabled) == 1:
            return enabled[0]
        if len(enabled) > 1:
            raise ValueError(
                "transport_modes has multiple entries set to true: " + ", ".join(enabled)
            )
        return DEFAULT_TRANSPORT_MODE

    @property
    def local_topology(self) -> str:
        topology = _resolve_status_selection(
            self._data.get("local_topologies"),
            selection_name="local_topologies",
            fallback="same_machine",
        ).strip()
        if topology not in {"same_machine", "same_lan"}:
            raise ValueError(f"Unsupported local topology={topology!r}")
        return topology

    @property
    def cloud_host(self) -> str:
        return str(self._data.get("cloud_host") or "").strip()

    @property
    def cloud_tcp_port(self) -> int:
        return int(self._data.get("cloud_tcp_port") or 8443)

    @property
    def cloud_udp_port(self) -> int:
        return int(self._data.get("cloud_udp_port") or 8440)

    @property
    def cloud_use_tls(self) -> bool:
        return _as_bool(self._data.get("cloud_use_tls"), default=True)

    @property
    def session_id(self) -> str:
        return str(self._data.get("session_id") or "default")

    @property
    def token(self) -> str:
        return str(self._data.get("token") or "")

    @property
    def reconnect_delay_s(self) -> float:
        return float(self._data.get("reconnect_delay_s") or 2.0)

    @property
    def local_lan_host(self) -> str:
        return str(self._data.get("local_lan_host") or "").strip()

    @property
    def master_udp_port(self) -> int:
        return int(self._data.get("master_udp_port") or 9001)

    @property
    def master_udp_host(self) -> str:
        explicit = str(self._data.get("master_udp_host") or "").strip()
        if explicit:
            return explicit
        return "127.0.0.1" if self.local_topology == "same_machine" else "0.0.0.0"

    @property
    def gripper_service_host(self) -> str:
        return str(self._data.get("gripper_service_host") or "127.0.0.1")

    @property
    def gripper_service_port(self) -> int:
        return int(self._data.get("gripper_service_port") or 9002)

    @property
    def master_udp_max_packet_bytes(self) -> int:
        return int(self._data.get("master_udp_max_packet_bytes") or 65507)

    def tls_scope(self) -> str:
        return "cloud" if self.transport_mode in {"cloud_tcp", "cloud_udp"} else "local"

    def tls_verify(self) -> bool:
        scope = self.tls_scope()
        scoped_key = f"{scope}_tls_verify"
        if scoped_key in self._data:
            return _as_bool(self._data.get(scoped_key), default=True)
        return _as_bool(self._data.get("tls_verify"), default=True)

    def tls_ca_file(self) -> str:
        scope = self.tls_scope()
        scoped_key = f"{scope}_tls_ca_file"
        raw = self._data.get(scoped_key)
        if raw is None or raw == "":
            raw = self._data.get("tls_ca_file")
        resolved = self._value_path(raw)
        if resolved:
            return resolved
        candidates = (
            (CONFIG_DIR / "certificate" / scope / "ca.crt", CONFIG_DIR / "ca.crt")
            if scope == "cloud"
            else (CONFIG_DIR / "certificate" / "local" / "ca.crt", CONFIG_DIR / "ca.crt")
        )
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate.resolve())
        return ""

    @property
    def relay_url(self) -> str:
        mode = self.transport_mode
        host = self.cloud_host
        if mode == "cloud_tcp" and host:
            scheme = "wss" if self.cloud_use_tls else "ws"
            return f"{scheme}://{host}:{self.cloud_tcp_port}/relay"
        return ""

    @property
    def cloud_udp_host(self) -> str:
        mode = self.transport_mode
        host = self.cloud_host
        if mode == "cloud_udp" and host:
            return host
        return str(self._data.get("udp_host") or host or "127.0.0.1").strip()

    @property
    def cloud_udp_port(self) -> int:
        if self.transport_mode == "cloud_udp" and self.cloud_host:
            return int(self._data.get("udp_port") or self.cloud_udp_port)
        return int(self._data.get("udp_port") or self.cloud_udp_port)

    def use_cloud_tcp_transport(self) -> bool:
        return self.transport_mode == "cloud_tcp"

    def use_cloud_udp_transport(self) -> bool:
        return self.transport_mode == "cloud_udp"

    def use_local_udp_transport(self) -> bool:
        return self.transport_mode == "local_udp"

    def use_local_tcp_transport(self) -> bool:
        return self.transport_mode == "local_tcp"

    def use_cloud_profile(self) -> bool:
        return self.transport_mode in {"cloud_tcp", "cloud_udp"}

    def active_outbound_name(self) -> str:
        return "cloud" if self.use_cloud_profile() else "local"

    @staticmethod
    def _value_path(raw_value) -> str:
        raw = str(raw_value or "").strip()
        if not raw:
            return ""
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = CONFIG_DIR / path
        return str(path.resolve())

    def apply_patch(self, patch: dict[str, Any]) -> None:
        if "transport_mode" in patch and patch["transport_mode"]:
            mode = normalize_transport_mode(str(patch["transport_mode"]).strip())
            self._data["transport_modes"] = _transport_modes_for_mode(mode)

        if "session_id" in patch:
            self._data["session_id"] = str(patch.get("session_id") or "default").strip() or "default"
        if "cloud_host" in patch:
            self._data["cloud_host"] = str(patch.get("cloud_host") or "").strip()
        if "local_lan_host" in patch:
            self._data["local_lan_host"] = str(patch.get("local_lan_host") or "").strip()

        local_topologies = patch.get("local_topologies")
        if isinstance(local_topologies, dict):
            same_machine = _as_bool(local_topologies.get("same_machine"), default=False)
            same_lan = _as_bool(local_topologies.get("same_lan"), default=False)
            if same_machine and same_lan:
                raise ValueError("Enable only one local topology")
            if not same_machine and not same_lan:
                same_machine = True
            self._data["local_topologies"] = {
                "same_machine": same_machine,
                "same_lan": same_lan,
            }

    def to_snapshot(self) -> dict[str, Any]:
        local_topologies = self._data.get("local_topologies")
        if not isinstance(local_topologies, dict):
            local_topologies = {"same_machine": True, "same_lan": False}
        return {
            "transport_mode": self.transport_mode,
            "transport_modes": _normalize_transport_modes(self._data.get("transport_modes")),
            "session_id": self.session_id,
            "cloud_host": self.cloud_host,
            "relay_url": self.relay_url,
            "cloud_udp_endpoint": f"udp://{self.cloud_udp_host}:{self.cloud_udp_port}",
            "master_udp_endpoint": f"udp://{self.master_udp_host}:{self.master_udp_port}",
            "local_topologies": {
                "same_machine": _as_bool(local_topologies.get("same_machine"), default=True),
                "same_lan": _as_bool(local_topologies.get("same_lan"), default=False),
            },
            "local_lan_host": self.local_lan_host,
            "active_outbound": self.active_outbound_name(),
            "config_path": str(CLOUD_CONFIG_PATH),
            "requires_restart": False,
        }

    def persist(self) -> None:
        CLOUD_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CLOUD_CONFIG_PATH.open("w", encoding="utf-8") as config_file:
            json.dump(self._data, config_file, indent=2, ensure_ascii=False)
            config_file.write("\n")


def get_runtime_settings() -> ClientRuntimeSettings:
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = ClientRuntimeSettings.from_cloud_file()
    return _RUNTIME


def set_runtime_settings(settings: ClientRuntimeSettings) -> None:
    global _RUNTIME
    _RUNTIME = settings


def init_runtime_settings() -> ClientRuntimeSettings:
    settings = ClientRuntimeSettings.from_cloud_file()
    set_runtime_settings(settings)
    return settings
