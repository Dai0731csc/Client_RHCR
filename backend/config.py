import json
import ssl
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
PAGES_DIR = FRONTEND_DIR
STATIC_DIR = FRONTEND_DIR
CONFIG_DIR = BASE_DIR / "config"
CLOUD_CONFIG_PATH = CONFIG_DIR / "cloud.json"
HOST = "0.0.0.0"
PORT = 8000

TRANSPORT_MODE_ALIASES = {
    "cloud_tcp": "cloud_tcp",
    "cloud_udp": "cloud_udp",
    "local_udp": "local_udp",
    "local_tcp": "local_tcp",
}
SUPPORTED_TRANSPORT_MODES = frozenset(TRANSPORT_MODE_ALIASES.values())
DEFAULT_TRANSPORT_MODE = "local_udp"
DEFAULT_TRANSPORT_MODES = {
    "local_udp": True,
    "local_tcp": False,
    "cloud_tcp": False,
    "cloud_udp": False,
}


def _as_bool(value, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _load_cloud_file() -> dict:
    if not CLOUD_CONFIG_PATH.exists():
        return {}

    with CLOUD_CONFIG_PATH.open(encoding="utf-8") as config_file:
        data = json.load(config_file)

    if not isinstance(data, dict):
        raise ValueError(f"{CLOUD_CONFIG_PATH} must contain a JSON object")
    return data


_CLOUD_FILE = _load_cloud_file()


def _cloud_top(key: str):
    """Top-level key from ``config/cloud.json`` (defaults live in the JSON file)."""
    return _CLOUD_FILE.get(key)


def _cfg(key: str, default):
    """Read ``config/cloud.json`` only (no env overrides). Runtime changes use ``/settings`` or POST ``/api/settings``."""
    file_value = _CLOUD_FILE.get(key)
    if file_value is not None and file_value != "":
        return file_value
    return default


def _resolve_status_selection(
    selections,
    *,
    selection_name: str,
    fallback: str,
) -> str:
    if isinstance(selections, dict):
        enabled_items: list[str] = []
        for item_id, item_data in selections.items():
            status = item_data.get("status") if isinstance(item_data, dict) else item_data
            if bool(status):
                enabled_items.append(str(item_id).strip())

        enabled_items = [item_id for item_id in enabled_items if item_id]
        if len(enabled_items) > 1:
            raise ValueError(
                f"{CLOUD_CONFIG_PATH} has multiple {selection_name} entries with status=true: "
                + ", ".join(enabled_items)
            )
        if len(enabled_items) == 1:
            return enabled_items[0]

    return fallback


def _resolve_local_topology() -> str:
    topology = _resolve_status_selection(
        _CLOUD_FILE.get("local_topologies"),
        selection_name="local_topologies",
        fallback="same_machine",
    ).strip()
    if topology not in {"same_machine", "same_lan"}:
        raise ValueError(
            f"Unsupported local topology={topology!r} in {CLOUD_CONFIG_PATH}; "
            "use one of: same_machine, same_lan"
        )
    return topology


def _value_path(raw_value) -> str:
    raw = str(raw_value or "").strip()
    if not raw:
        return ""
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = CONFIG_DIR / path
    return str(path.resolve())


def _config_path(key: str) -> str:
    return _value_path(_cloud_top(key))


def _default_tls_ca_path_for_scope(scope: str) -> str:
    if scope == "cloud":
        candidates = (
            CONFIG_DIR / "certificate" / "cloud" / "ca.crt",
            CONFIG_DIR / "ca.crt",
        )
    else:
        candidates = (
            CONFIG_DIR / "certificate" / "local" / "ca.crt",
            CONFIG_DIR / "ca.crt",
        )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return ""


def _webrtc_scalar(key: str, default: str = "") -> str:
    webrtc = _CLOUD_FILE.get("webrtc")
    if not isinstance(webrtc, dict):
        return default
    v = webrtc.get(key)
    if v is None or v == "":
        return default
    if isinstance(v, list):
        return ",".join(str(x).strip() for x in v if str(x).strip())
    return str(v).strip()


def normalize_transport_mode(value: str) -> str:
    mode = value.strip().lower()
    return TRANSPORT_MODE_ALIASES.get(mode, mode)


def _tls_scope_for_transport_mode(transport_mode: str) -> str:
    mode = str(transport_mode or "").strip().lower()
    return "cloud" if mode in {"cloud_tcp", "cloud_udp"} else "local"


def _resolve_tls_verify_for_transport_mode(transport_mode: str) -> bool:
    scope = _tls_scope_for_transport_mode(transport_mode)
    scoped_key = f"{scope}_tls_verify"
    if scoped_key in _CLOUD_FILE:
        return _as_bool(_cloud_top(scoped_key), default=True)
    return _as_bool(_cloud_top("tls_verify"), default=True)


def _resolve_tls_ca_file_for_transport_mode(transport_mode: str) -> str:
    scope = _tls_scope_for_transport_mode(transport_mode)
    scoped_key = f"{scope}_tls_ca_file"
    raw = _cloud_top(scoped_key)
    if raw is None or raw == "":
        raw = _cloud_top("tls_ca_file")
    resolved = _value_path(raw)
    if resolved:
        return resolved
    return _default_tls_ca_path_for_scope(scope)


TRANSPORT_MODE = _resolve_status_selection(
    _CLOUD_FILE.get("transport_modes") or DEFAULT_TRANSPORT_MODES,
    selection_name="transport_modes",
    fallback=DEFAULT_TRANSPORT_MODE,
)
TRANSPORT_MODE = normalize_transport_mode(TRANSPORT_MODE)
if TRANSPORT_MODE and TRANSPORT_MODE not in SUPPORTED_TRANSPORT_MODES:
    raise ValueError(
        f"Unsupported transport mode={TRANSPORT_MODE!r} in {CLOUD_CONFIG_PATH}; "
        "use one of: local_udp, local_tcp, cloud_tcp, cloud_udp"
    )

LOCAL_TOPOLOGY = _resolve_local_topology()
LOCAL_LAN_HOST = str(_cloud_top("local_lan_host") or "").strip()

_cloud_host = str(_cloud_top("cloud_host") or "").strip()
_cloud_tcp_port = int(_cloud_top("cloud_tcp_port"))
_cloud_udp_port = int(_cloud_top("cloud_udp_port"))
_cloud_tls_raw = _CLOUD_FILE.get("cloud_use_tls")
# Default HTTPS/WSS; omitting the key is equivalent to true; set ``cloud_use_tls: false`` for plain WS debugging.
_cloud_use_tls = _as_bool(_cloud_tls_raw, default=True)
TLS_VERIFY = _resolve_tls_verify_for_transport_mode(TRANSPORT_MODE)
TLS_CA_FILE = _resolve_tls_ca_file_for_transport_mode(TRANSPORT_MODE)
LOCAL_TLS_CERT_FILE = _value_path(
    _cloud_top("local_tls_cert_file") or "certificate/local/cert.pem"
)
LOCAL_TLS_KEY_FILE = _value_path(
    _cloud_top("local_tls_key_file") or "certificate/local/key.pem"
)

# Relay: ``cloud_tcp`` uses outbound cloud /relay; ``local_tcp`` exposes GET /relay on this client.
_ws_host = _cloud_host
if TRANSPORT_MODE == "cloud_tcp" and _ws_host:
    _http_scheme = "https" if _cloud_use_tls else "http"
    _ws_scheme = "wss" if _cloud_use_tls else "ws"
    CLOUD_BASE_URL = f"{_http_scheme}://{_ws_host}:{_cloud_tcp_port}"
    RELAY_URL = f"{_ws_scheme}://{_ws_host}:{_cloud_tcp_port}/relay"
elif TRANSPORT_MODE == "cloud_udp":
    CLOUD_BASE_URL = ""
    RELAY_URL = ""
else:
    CLOUD_BASE_URL = ""
    RELAY_URL = ""

RELAY_SESSION_ID = str(_cloud_top("session_id") or "")
RELAY_TOKEN = str(_cloud_top("token") or "")
RELAY_RECONNECT_DELAY_S = float(_cloud_top("reconnect_delay_s"))

if TRANSPORT_MODE == "cloud_udp" and _cloud_host:
    CLOUD_UDP_HOST = _cloud_host
    CLOUD_UDP_PORT = int(_cloud_top("udp_port") or _cloud_udp_port)
else:
    CLOUD_UDP_HOST = str(_cfg("udp_host", _cloud_host or "127.0.0.1")).strip()
    CLOUD_UDP_PORT = int(_cloud_top("udp_port"))

_master_udp_host = str(_cloud_top("master_udp_host") or "").strip()
if not _master_udp_host:
    _master_udp_host = "127.0.0.1" if LOCAL_TOPOLOGY == "same_machine" else "0.0.0.0"
MASTER_UDP_HOST = _master_udp_host
MASTER_UDP_PORT = int(_cfg("master_udp_port", 9001))
MASTER_UDP_MAX_PACKET_BYTES = int(_cfg("master_udp_max_packet_bytes", 65507))
GRIPPER_SERVICE_HOST = str(_cfg("gripper_service_host", "127.0.0.1"))
GRIPPER_SERVICE_PORT = int(_cfg("gripper_service_port", 9002))


def _runtime():
    from .runtime_settings import get_runtime_settings

    return get_runtime_settings()


def get_transport_mode() -> str:
    return _runtime().transport_mode


def get_relay_url() -> str:
    return _runtime().relay_url


def get_relay_session_id() -> str:
    return _runtime().session_id


def get_relay_token() -> str:
    return _runtime().token


def get_relay_reconnect_delay_s() -> float:
    return _runtime().reconnect_delay_s


def get_cloud_udp_host() -> str:
    return _runtime().cloud_udp_host


def get_cloud_udp_port() -> int:
    return _runtime().cloud_udp_port


def get_master_udp_host() -> str:
    return _runtime().master_udp_host


def get_master_udp_port() -> int:
    return _runtime().master_udp_port


def get_gripper_service_host() -> str:
    return _runtime().gripper_service_host


def get_gripper_service_port() -> int:
    return _runtime().gripper_service_port


def get_runtime_tls_verify() -> bool:
    return _runtime().tls_verify()


def get_runtime_tls_ca_file() -> str:
    return _runtime().tls_ca_file()


def use_cloud_tcp_transport() -> bool:
    return _runtime().use_cloud_tcp_transport()


def use_cloud_udp_transport() -> bool:
    return _runtime().use_cloud_udp_transport()


def use_local_udp_transport() -> bool:
    return _runtime().use_local_udp_transport()


def use_local_tcp_transport() -> bool:
    return _runtime().use_local_tcp_transport()


def use_cloud_profile() -> bool:
    return _runtime().use_cloud_profile()


def get_webrtc_ice_servers():
    stun_urls = [
        url.strip()
        for url in _webrtc_scalar("stun_urls", "stun:stun.l.google.com:19302").split(",")
        if url.strip()
    ]
    turn_urls = [
        url.strip() for url in _webrtc_scalar("turn_urls", "").split(",") if url.strip()
    ]

    ice_servers = []
    if stun_urls:
        ice_servers.append({"urls": stun_urls})

    if turn_urls:
        turn_server = {"urls": turn_urls}
        username = _webrtc_scalar("turn_username", "")
        credential = _webrtc_scalar("turn_password", "")
        if username:
            turn_server["username"] = username
        if credential:
            turn_server["credential"] = credential
        ice_servers.append(turn_server)

    return ice_servers


def build_webrtc_client_config():
    return {
        "iceServers": get_webrtc_ice_servers(),
    }


def create_rtc_configuration(RTCConfiguration, RTCIceServer):
    ice_servers = []
    for server in get_webrtc_ice_servers():
        ice_servers.append(
            RTCIceServer(
                urls=server["urls"],
                username=server.get("username"),
                credential=server.get("credential"),
            )
        )
    return RTCConfiguration(iceServers=ice_servers)


def create_ssl_context():
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(LOCAL_TLS_CERT_FILE, LOCAL_TLS_KEY_FILE)
    return ssl_ctx
