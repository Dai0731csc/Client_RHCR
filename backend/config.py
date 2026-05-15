import os
import ssl
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
PAGES_DIR = FRONTEND_DIR / "pages"
STATIC_DIR = FRONTEND_DIR / "static"
CONFIG_DIR = BASE_DIR / "config"
HOST = "0.0.0.0"
PORT = 8000
MASTER_UDP_HOST = os.getenv("MASTER_UDP_HOST", "0.0.0.0")
MASTER_UDP_PORT = int(os.getenv("MASTER_UDP_PORT", "9001"))
MASTER_UDP_MAX_PACKET_BYTES = int(os.getenv("MASTER_UDP_MAX_PACKET_BYTES", "65507"))
GRIPPER_SERVICE_HOST = os.getenv("GRIPPER_SERVICE_HOST", "127.0.0.1")
GRIPPER_SERVICE_PORT = int(os.getenv("GRIPPER_SERVICE_PORT", "9002"))

CLOUD_BASE_URL = os.getenv("CLOUD_BASE_URL", "http://86.50.169.179:8443").rstrip("/")


def relay_url_from_cloud_base(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.startswith("https://"):
        return base.replace("https://", "wss://", 1) + "/relay"
    if base.startswith("http://"):
        return base.replace("http://", "ws://", 1) + "/relay"
    if base.startswith(("ws://", "wss://")):
        return base if base.endswith("/relay") else f"{base}/relay"
    return f"ws://{base}/relay"


TRANSPORT_MODE = os.getenv("TRANSPORT_MODE", "relay").strip().lower()
RELAY_URL = os.getenv("RELAY_URL", relay_url_from_cloud_base(CLOUD_BASE_URL))
RELAY_SESSION_ID = os.getenv("RELAY_SESSION_ID", "default")
RELAY_TOKEN = os.getenv("RELAY_TOKEN", "")
RELAY_RECONNECT_DELAY_S = float(os.getenv("RELAY_RECONNECT_DELAY_S", "2.0"))


def get_webrtc_ice_servers():
    stun_urls = [
        url.strip()
        for url in os.getenv("WEBRTC_STUN_URLS", "stun:stun.l.google.com:19302").split(",")
        if url.strip()
    ]
    turn_urls = [
        url.strip()
        for url in os.getenv("WEBRTC_TURN_URLS", "").split(",")
        if url.strip()
    ]

    ice_servers = []
    if stun_urls:
        ice_servers.append({"urls": stun_urls})

    if turn_urls:
        turn_server = {"urls": turn_urls}
        username = os.getenv("WEBRTC_TURN_USERNAME")
        credential = os.getenv("WEBRTC_TURN_PASSWORD")
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
