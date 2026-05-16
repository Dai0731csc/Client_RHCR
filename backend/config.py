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
    "cloud": "cloud_tcp",
    "relay": "cloud_tcp",
    "tcp": "cloud_tcp",
    "ws": "cloud_tcp",
    "wss": "cloud_tcp",
    "cloud_tcp": "cloud_tcp",
    "cloud_udp": "cloud_udp",
    "local": "local_udp",
    "udp": "local_udp",
    "local_udp": "local_udp",
    "local_tcp": "local_tcp",
    "lan_ws": "local_tcp",
}


def _as_bool(value, *, default: bool) -> bool:
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
    """``config/cloud.json`` 顶层键（默认值在 JSON 中维护）。"""
    return _CLOUD_FILE.get(key)


def _cfg(key: str, default):
    """只读 ``config/cloud.json``，不用环境变量覆盖（换模式请改配置文件）。"""
    file_value = _CLOUD_FILE.get(key)
    if file_value is not None and file_value != "":
        return file_value
    return default


def _config_path(key: str) -> str:
    raw = str(_cloud_top(key) or "").strip()
    if not raw:
        return ""
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = CONFIG_DIR / path
    return str(path.resolve())


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


TRANSPORT_MODE = str(_cloud_top("transport_mode") or "").strip()
TRANSPORT_MODE = normalize_transport_mode(TRANSPORT_MODE)

_cloud_host = str(_cloud_top("cloud_host") or "").strip()
_cloud_tcp_port = int(_cloud_top("cloud_tcp_port"))
_cloud_udp_port = int(_cloud_top("cloud_udp_port"))
_cloud_tls_raw = _CLOUD_FILE.get("cloud_use_tls")
# 默认 HTTPS/WSS；JSON 不写该键等价 true；明文调试设 ``cloud_use_tls: false``
_cloud_use_tls = _as_bool(_cloud_tls_raw, default=True)
_cloud_tls_verify_raw = _CLOUD_FILE.get("tls_verify")
TLS_VERIFY = _as_bool(_cloud_tls_verify_raw, default=True)
TLS_CA_FILE = _config_path("tls_ca_file")

# relay：cloud_tcp / local_tcp → 拼 https/wss 或 http/ws（与 ``cloud_use_tls`` 一致）
_ws_host = _cloud_host
if TRANSPORT_MODE == "local_tcp" and not _ws_host:
    _ws_host = "127.0.0.1"

if TRANSPORT_MODE in {"cloud_tcp", "local_tcp"} and _ws_host:
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

MASTER_UDP_HOST = str(_cfg("master_udp_host", "0.0.0.0"))
MASTER_UDP_PORT = int(_cfg("master_udp_port", 9001))
MASTER_UDP_MAX_PACKET_BYTES = int(_cfg("master_udp_max_packet_bytes", 65507))
GRIPPER_SERVICE_HOST = str(_cfg("gripper_service_host", "127.0.0.1"))
GRIPPER_SERVICE_PORT = int(_cfg("gripper_service_port", 9002))


def use_relay_transport() -> bool:
    """经 WebSocket ``/relay`` 出站（``cloud_tcp`` 与 ``local_tcp``）。"""
    return use_relay_ws_transport()


def use_cloud_transport() -> bool:
    return TRANSPORT_MODE in {"cloud_tcp", "cloud_udp", "local_tcp"}


def use_relay_ws_transport() -> bool:
    """WebSocket relay 路径（云上或本地中继均为同一客户端逻辑）。"""
    return TRANSPORT_MODE in {"cloud_tcp", "local_tcp"}


def use_cloud_tcp_transport() -> bool:
    """兼容旧名：等价于 ``use_relay_ws_transport()``。"""
    return use_relay_ws_transport()


def use_cloud_udp_transport() -> bool:
    return TRANSPORT_MODE == "cloud_udp"


def use_local_udp_transport() -> bool:
    return TRANSPORT_MODE == "local_udp"


def use_local_tcp_transport() -> bool:
    return TRANSPORT_MODE == "local_tcp"


def use_local_profile() -> bool:
    return TRANSPORT_MODE == "local_udp"


def use_cloud_profile() -> bool:
    return TRANSPORT_MODE in {"cloud_tcp", "cloud_udp", "local_tcp"}


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
    ssl_ctx.load_cert_chain(CONFIG_DIR / "cert.pem", CONFIG_DIR / "key.pem")
    return ssl_ctx
