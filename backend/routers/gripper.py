import json
from datetime import datetime

from aiohttp import web

from ..services.device_service import get_client_ip
from ..services.gripper_service import build_gripper_command_payload, dispatch_gripper_command


def _log(message):
    print(f"[TeleProgram] {message}")


def _now_label():
    return datetime.now().strftime("%H:%M:%S")


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
    client_ip = get_client_ip(request.headers, request.remote)
    _log(
        f"[{_now_label()}] gripper command received from {client_ip or 'unknown'}: "
        f"action={command_payload['action']}"
    )
    dispatch_result = dispatch_gripper_command(request.app, command_payload)
    if not dispatch_result["success"]:
        _log(
            f"[{_now_label()}] gripper command rejected: "
            f"error={dispatch_result['error']} message={dispatch_result['message']}"
        )
        return web.json_response(
            {
                "success": False,
                "accepted": False,
                "error": dispatch_result["error"],
                "message": dispatch_result["message"],
            },
            status=dispatch_result["status"],
        )

    _log(
        f"[{_now_label()}] gripper command sent: "
        f"action={command_payload['action']} "
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
