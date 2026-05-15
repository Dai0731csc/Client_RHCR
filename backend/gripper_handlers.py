import asyncio
import json
import uuid
from datetime import datetime

from aiohttp import web

from .common import current_utc_iso_timestamp
from .config import GRIPPER_SERVICE_HOST, GRIPPER_SERVICE_PORT, TRANSPORT_MODE
from .relay_master import send_master_relay_payload, use_relay_transport
from .state import GRIPPER_COMMAND_TRANSPORT_KEY, MASTER_RELAY_CLIENT_KEY

GRIPPER_PROTOCOL = "master-slave.gripper.v1"
GRIPPER_COMMAND_MESSAGE_TYPE = "gripper_command"
GRIPPER_ALLOWED_ACTIONS = {"open", "close"}


def _log(message):
    print(f"[TeleProgram] {message}")


def _now_label():
    return datetime.now().strftime("%H:%M:%S")


def _sanitize_int(payload, field_name, default_value):
    try:
        return int(payload.get(field_name, default_value))
    except (TypeError, ValueError) as error:
        raise web.HTTPBadRequest(
            text=json.dumps(
                {
                    "success": False,
                    "error": f"invalid_{field_name}",
                    "message": f"{field_name} must be an integer",
                },
                ensure_ascii=False,
            ),
            content_type="application/json",
        ) from error


def build_gripper_command_payload(payload):
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
        "speed": _sanitize_int(payload, "speed", 30),
        "force": _sanitize_int(payload, "force", 1),
        "client_time": payload.get("client_time") or current_utc_iso_timestamp(),
    }


async def gripper_command_handler(request):
    try:
        payload = await request.json()
    except json.JSONDecodeError as error:
        raise web.HTTPBadRequest(
            text=json.dumps(
                {
                    "success": False,
                    "error": "invalid_json",
                    "message": "request body must be valid JSON",
                },
                ensure_ascii=False,
            ),
            content_type="application/json",
        ) from error

    command_payload = build_gripper_command_payload(payload)

    if use_relay_transport():
        relay_client = request.app.get(MASTER_RELAY_CLIENT_KEY)
        if relay_client is None or not relay_client.is_connected:
            return web.json_response(
                {
                    "success": False,
                    "accepted": False,
                    "error": "gripper_transport_unavailable",
                    "message": "Relay transport is not connected",
                },
                status=503,
            )
        if not send_master_relay_payload(request.app, command_payload):
            return web.json_response(
                {
                    "success": False,
                    "accepted": False,
                    "error": "gripper_transport_unavailable",
                    "message": "Failed to send gripper command via relay",
                },
                status=503,
            )
    else:
        transport = request.app.get(GRIPPER_COMMAND_TRANSPORT_KEY)
        if transport is None:
            return web.json_response(
                {
                    "success": False,
                    "accepted": False,
                    "error": "gripper_transport_unavailable",
                    "message": "Gripper command transport is not running",
                },
                status=503,
            )

        transport.sendto(
            json.dumps(command_payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            (GRIPPER_SERVICE_HOST, GRIPPER_SERVICE_PORT),
        )
    _log(
        f"[{_now_label()}] gripper command sent: "
        f"action={command_payload['action']} "
        f"speed={command_payload['speed']} "
        f"force={command_payload['force']} "
        f"request_id={command_payload['request_id']}"
    )
    return web.json_response(
        {
            "success": True,
            "accepted": True,
            "request_id": command_payload["request_id"],
            "action": command_payload["action"],
        }
    )


class GripperCommandTransportProtocol(asyncio.DatagramProtocol):
    def __init__(self, app):
        self.app = app

    def connection_made(self, transport):
        self.app[GRIPPER_COMMAND_TRANSPORT_KEY] = transport
        sockname = transport.get_extra_info("sockname")
        _log(
            f"[{_now_label()}] gripper command udp ready on "
            f"{sockname[0]}:{sockname[1]}"
        )

    def error_received(self, exc):
        _log(f"gripper command udp error: {exc}")

    def connection_lost(self, exc):
        self.app[GRIPPER_COMMAND_TRANSPORT_KEY] = None
        if exc is not None:
            _log(f"gripper command udp closed with error: {exc}")


async def start_gripper_command_transport(app):
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: GripperCommandTransportProtocol(app),
        local_addr=("0.0.0.0", 0),
    )
    app[GRIPPER_COMMAND_TRANSPORT_KEY] = transport


async def close_gripper_command_transport(app):
    transport = app.get(GRIPPER_COMMAND_TRANSPORT_KEY)
    if transport is not None:
        transport.close()
    app[GRIPPER_COMMAND_TRANSPORT_KEY] = None
