from pathlib import Path

from aiohttp import web
from jinja2 import Environment, FileSystemLoader

from .calibration_handlers import (
    calibration_publish_websocket_handler,
    camera_calibration_handler,
    camera_calibration_validate_handler,
)
from .config import PAGES_DIR, STATIC_DIR
from .gripper_handlers import (
    close_gripper_command_transport,
    gripper_command_handler,
    start_gripper_command_transport,
)
from .config import TRANSPORT_MODE
from .master_stream import close_master_transport, start_master_transport
from .state import init_app_state
from .webrtc_handlers import (
    close_webrtc_peers,
    webrtc_config_handler,
    webrtc_signaling_websocket_handler,
)
from .ws_handlers import (
    apriltag_publish_websocket_handler,
)


def _normalize_base_path(base_path):
    base_path = (base_path or "").strip()
    if not base_path or base_path == "/":
        return ""
    return "/" + base_path.strip("/")


def _app_path(base_path, suffix):
    normalized = _normalize_base_path(base_path)
    if not suffix.startswith("/"):
        suffix = f"/{suffix}"
    return f"{normalized}{suffix}" if normalized else suffix


async def camera_page(_request):
    env = _request.app["jinja"]
    template = env.get_template("camera.html")
    html = template.render(**_request.app["template_context"])
    return web.Response(text=html, content_type="text/html")


def create_app(*, base_path="", hub_path="/"):
    app = web.Application()
    normalized_base_path = _normalize_base_path(base_path)
    init_app_state(app)
    app["template_context"] = {
        "base_path": normalized_base_path,
        "hub_path": hub_path or "/",
        "static_url_prefix": _app_path(normalized_base_path, "/static"),
    }
    app["jinja"] = Environment(loader=FileSystemLoader(str(Path(PAGES_DIR))))
    app.on_startup.append(start_master_transport)
    if TRANSPORT_MODE != "relay":
        app.on_startup.append(start_gripper_command_transport)
    app.on_shutdown.append(close_webrtc_peers)
    if TRANSPORT_MODE != "relay":
        app.on_shutdown.append(close_gripper_command_transport)
    app.on_shutdown.append(close_master_transport)
    app.router.add_get("/", camera_page)
    app.router.add_get("/ws/webrtc", webrtc_signaling_websocket_handler)
    app.router.add_get("/ws/publish", apriltag_publish_websocket_handler)
    app.router.add_get("/ws/calibration/publish", calibration_publish_websocket_handler)
    app.router.add_get("/api/webrtc/config", webrtc_config_handler)
    app.router.add_post("/api/gripper/command", gripper_command_handler)
    app.router.add_post("/api/camera-calibration/validate", camera_calibration_validate_handler)
    app.router.add_post("/api/camera-calibration", camera_calibration_handler)
    app.router.add_static("/static/", STATIC_DIR)
    return app
