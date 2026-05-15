import json
import uuid
from typing import Any, Mapping

from aiohttp import web

from ..links import get_links
from ..models import GripperCommandPayload, GripperDispatchResult
from ..utils import current_utc_iso_timestamp

GRIPPER_PROTOCOL = "master-slave.gripper.v1"
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


def dispatch_gripper_command(app, command_payload: GripperCommandPayload) -> GripperDispatchResult:
    links = get_links(app)

    if not links.outbound.is_connected:
        return {
            "success": False,
            "accepted": False,
            "error": "gripper_transport_unavailable",
            "message": f"{links.active_outbound} link is not connected",
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
