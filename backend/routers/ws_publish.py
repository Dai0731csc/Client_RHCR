import json
from datetime import datetime

from aiohttp import web

from ..services.stream_service import ingest_apriltag_payload
from ..utils import create_ack_payload


def _log(message):
    print(f"[TeleProgram] {message}")


async def apriltag_publish_websocket_handler(request):
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)

    client = request.remote
    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] transport connected: "
        f"transport=websocket channel=apriltag client={client}"
    )

    await ws.send_json(
        {
            "type": "publish_ready",
            "server_time": datetime.now().isoformat(timespec="seconds"),
        }
    )

    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            try:
                payload = json.loads(msg.data)
            except json.JSONDecodeError:
                continue
            if payload.get("type") == "ping":
                await ws.send_json(create_ack_payload(payload))
                continue
            if payload.get("type") == "time_sync_result":
                _log(
                    f"[{datetime.now().strftime('%H:%M:%S')}] time sync result "
                    f"({payload.get('transport', 'websocket:apriltag')}): "
                    f"status={payload.get('status', 'unknown')} "
                    f"sample_count={payload.get('sample_count', 'n/a')} "
                    f"offset_ms={payload.get('offset_ms', 'n/a')} "
                    f"rtt_ms={payload.get('rtt_ms', 'n/a')} "
                    f"completed_at={payload.get('completed_at', 'n/a')}"
                )
                continue
            await ingest_apriltag_payload(request.app, payload, source="websocket")
        elif msg.type == web.WSMsgType.ERROR:
            _log(f"apriltag publish ws error: {ws.exception()}")

    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] transport disconnected: "
        f"transport=websocket channel=apriltag client={client}"
    )
    return ws
