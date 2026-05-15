import json
from datetime import datetime

from aiohttp import web
from scipy.spatial.transform import Rotation as R

from .common import (
    create_ack_payload,
    with_server_receive_time,
)
from .master_stream import broadcast_master_payload
from .state import (
    MASTER_LATEST_APRILTAG_PAYLOAD_KEY,
    MASTER_LATEST_DETECTION_STATE_KEY,
)


def _log(message):
    print(f"[TeleProgram] {message}")


def get_detection_tag_id(detection):
    if not isinstance(detection, dict):
        return None

    detection_id = detection.get("id")
    if detection_id is not None:
        return detection_id

    return detection.get("tag_id")


def format_numeric_vector(values):
    if values is None:
        return "n/a"
    values = list(values)
    if len(values) == 0:
        return "n/a"
    return "[" + ", ".join(f"{float(value):.2f}" for value in values) + "]"


async def ingest_apriltag_payload(app, payload, *, source="websocket"):
    payload = with_server_receive_time(payload)
    message_type = payload.get("type")

    if message_type == "detection_state":
        app[MASTER_LATEST_DETECTION_STATE_KEY] = payload
        broadcast_master_payload(
            app,
            payload,
            add_server_send_time=True,
        )
        _log(
            f"[{datetime.now().strftime('%H:%M:%S')}] detection state "
            f"({source}): active={bool(payload.get('active', False))} "
            f"fps={payload.get('nominal_frame_rate')} "
            f"frame_size={payload.get('frame_size')}"
        )
        return payload

    if message_type != "apriltag_detections":
        return payload

    latest_detection_state = app[MASTER_LATEST_DETECTION_STATE_KEY] or {}
    master_payload = {
        **payload,
        "nominal_frame_rate": payload.get("nominal_frame_rate", latest_detection_state.get("nominal_frame_rate")),
        "frame_size": payload.get("frame_size", latest_detection_state.get("frame_size")),
    }
    app[MASTER_LATEST_APRILTAG_PAYLOAD_KEY] = master_payload
    broadcast_master_payload(
        app,
        master_payload,
        add_server_send_time=True,
    )

    detections = master_payload.get("detections") or []
    detection_summaries = []
    for detection in detections:
        detection_tag_id = get_detection_tag_id(detection)
        pose = detection.get("pose") or {}
        detection_summaries.append(
            f"tag_id={detection_tag_id} "
            f"t={format_numeric_vector(pose.get('t'))} "
            f"euler_xyz_deg={format_numeric_vector(R.from_matrix(pose.get('R')).as_euler('xyz', degrees=True)) if pose.get('R') else 'n/a'}"
        )
    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] apriltag packet received "
        f"({source}, count={len(detections)}, detections={detection_summaries})"
    )
    return master_payload


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
