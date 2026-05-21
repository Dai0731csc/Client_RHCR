import json
import uuid
from typing import Any, Mapping

from aiohttp import web

from ..links import get_links
from ..links.local.gripper_udp import send_gripper_command as send_local_gripper_udp
from ..models import GripperCommandPayload, GripperDispatchResult
from ..state import GRIPPER_COMMAND_TRANSPORT_KEY
from ..utils import current_utc_iso_timestamp

GRIPPER_PROTOCOL = "rhcr-oulu.gripper"
GRIPPER_COMMAND_MESSAGE_TYPE = "gripper_command"
GRIPPER_ALLOWED_ACTIONS = {"open", "close"}


def build_gripper_command_payload(payload: Mapping[str, Any]) -> GripperCommandPayload:
    action = payload.get("action")
    if action not in GRIPPER_ALLOWED_ACTIONS:
        raise web.HTTPBadRequest(
            text=json.dumps(
                {
                    "success": False,
                    "error": "invalid_action",
                    "message": "action must be one of: open, close",
                },
                ensure_ascii=False,
            ),
            content_type="application/json",
        )

    return {
        "type": GRIPPER_COMMAND_MESSAGE_TYPE,
        "protocol": GRIPPER_PROTOCOL,
        "request_id": payload.get("request_id") or str(uuid.uuid4()),
        "action": action,
        "client_time": payload.get("client_time") or current_utc_iso_timestamp(),
    }


def _try_local_gripper_udp(app, command_payload: GripperCommandPayload) -> bool:
    if app.get(GRIPPER_COMMAND_TRANSPORT_KEY) is None:
        return False
    return send_local_gripper_udp(app, command_payload)


def dispatch_gripper_command(app, command_payload: GripperCommandPayload) -> GripperDispatchResult:
    links = get_links(app)

    # local_udp / local_tcp: direct UDP to control server tool_listen (never relay).
    if links.active_outbound == "local":
        if _try_local_gripper_udp(app, command_payload):
            return {
                "success": True,
                "accepted": True,
                "status": 200,
                "error": None,
                "message": None,
            }
        return {
            "success": False,
            "accepted": False,
            "error": "gripper_udp_unavailable",
            "message": (
                "Local gripper uses UDP to control server tool_listen "
                f"(check gripper_service_port and that server tool service is running)"
            ),
            "status": 503,
        }

    if not links.outbound.is_connected:
        return {
            "success": False,
            "accepted": False,
            "error": "gripper_transport_unavailable",
            "message": f"{links.active_outbound} link is not connected",
            "status": 503,
        }

    if not links.outbound.is_ready(app):
        return {
            "success": False,
            "accepted": False,
            "error": "gripper_peer_unavailable",
            "message": f"{links.active_outbound} link has no connected peer",
            "status": 503,
        }

    if not links.outbound.send_gripper(app, command_payload):
        return {
            "success": False,
            "accepted": False,
            "error": "gripper_transport_unavailable",
            "message": "Failed to send gripper command",
            "status": 503,
        }

    return {
        "success": True,
        "accepted": True,
        "status": 200,
        "error": None,
        "message": None,
    }
