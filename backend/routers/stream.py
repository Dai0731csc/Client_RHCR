"""Backward-compatible re-exports; prefer routers.webrtc and routers.ws_publish."""

from .webrtc import (
    close_webrtc_peers,
    webrtc_config_handler,
    webrtc_signaling_websocket_handler,
)
from .ws_publish import apriltag_publish_websocket_handler

__all__ = [
    "apriltag_publish_websocket_handler",
    "close_webrtc_peers",
    "webrtc_config_handler",
    "webrtc_signaling_websocket_handler",
]
