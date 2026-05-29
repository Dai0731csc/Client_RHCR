"""Frontend link: HTTP / WebSocket / WebRTC from the browser."""

from pathlib import Path

from aiohttp import web
from jinja2 import Environment, FileSystemLoader

from ...config import PAGES_DIR, STATIC_DIR
from ...routers import (
    apriltag_publish_websocket_handler,
    app_path,
    build_template_context,
    calibration_publish_websocket_handler,
    camera_page,
    settings_page,
    settings_get_handler,
    settings_update_handler,
    camera_calibration_handler,
    camera_calibration_validate_handler,
    close_webrtc_peers,
    device_profile_by_ip_handler,
    device_profile_handler,
    full_chain_time_sync_handler,
    gripper_command_handler,
    local_relay_websocket_handler,
    webrtc_config_handler,
    webrtc_signaling_websocket_handler,
)


class FrontendLink:
    name = "frontend"

    def register_routes(self, app: web.Application, *, base_path: str = "") -> None:
        app["template_context"] = build_template_context(base_path=base_path)
        app["jinja"] = Environment(loader=FileSystemLoader(str(Path(PAGES_DIR))))

        app.router.add_get(app_path(base_path, "/"), camera_page)
        app.router.add_get(app_path(base_path, "/settings"), settings_page)
        app.router.add_get(app_path(base_path, "/api/settings"), settings_get_handler)
        app.router.add_post(app_path(base_path, "/api/settings"), settings_update_handler)
        app.router.add_get(app_path(base_path, "/ws/webrtc"), webrtc_signaling_websocket_handler)
        app.router.add_get(app_path(base_path, "/ws/publish"), apriltag_publish_websocket_handler)
        app.router.add_get(
            app_path(base_path, "/ws/calibration/publish"),
            calibration_publish_websocket_handler,
        )
        app.router.add_get(app_path(base_path, "/relay"), local_relay_websocket_handler)
        app.router.add_get(app_path(base_path, "/api/device-profile"), device_profile_handler)
        app.router.add_get(
            app_path(base_path, "/api/device-profile/{ip}"),
            device_profile_by_ip_handler,
        )
        app.router.add_get(app_path(base_path, "/api/webrtc/config"), webrtc_config_handler)
        app.router.add_post(app_path(base_path, "/api/gripper/command"), gripper_command_handler)
        app.router.add_post(
            app_path(base_path, "/api/time-sync/full-chain"),
            full_chain_time_sync_handler,
        )
        app.router.add_post(
            app_path(base_path, "/api/camera-calibration/validate"),
            camera_calibration_validate_handler,
        )
        app.router.add_post(
            app_path(base_path, "/api/camera-calibration"),
            camera_calibration_handler,
        )
        app.router.add_static(app_path(base_path, "/static/"), STATIC_DIR)

    async def shutdown(self, app: web.Application) -> None:
        await close_webrtc_peers(app)
