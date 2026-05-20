import asyncio
import json
from datetime import datetime

from ...config import MASTER_UDP_MAX_PACKET_BYTES, use_cloud_udp_transport
from ...state import MASTER_CLOUD_TRANSPORT_KEY
from ...state import (
    MASTER_LATEST_APRILTAG_PAYLOAD_KEY,
    MASTER_LATEST_DETECTION_STATE_KEY,
    MASTER_LATEST_INITIAL_CALIBRATION_KEY,
)
from ...utils import current_utc_iso_timestamp
from ..pose_protocol import (
    MASTER_STREAM_READY_MESSAGE_TYPE,
    decorate_master_payload,
    log_pose,
)


def send_master_snapshot(app, peer_key) -> None:
    del peer_key
    broadcast_pose(
        app,
        {
            "type": MASTER_STREAM_READY_MESSAGE_TYPE,
            "master_time": current_utc_iso_timestamp(),
            "has_detection_state": app[MASTER_LATEST_DETECTION_STATE_KEY] is not None,
            "has_initial_calibration": app[MASTER_LATEST_INITIAL_CALIBRATION_KEY] is not None,
            "has_apriltag_detections": app[MASTER_LATEST_APRILTAG_PAYLOAD_KEY] is not None,
        },
    )

    if app[MASTER_LATEST_DETECTION_STATE_KEY] is not None:
        broadcast_pose(
            app,
            app[MASTER_LATEST_DETECTION_STATE_KEY],
            add_master_send_time=True,
        )

    if app[MASTER_LATEST_INITIAL_CALIBRATION_KEY] is not None:
        broadcast_pose(
            app,
            app[MASTER_LATEST_INITIAL_CALIBRATION_KEY],
            add_master_send_time=True,
        )

    if app[MASTER_LATEST_APRILTAG_PAYLOAD_KEY] is not None:
        broadcast_pose(
            app,
            app[MASTER_LATEST_APRILTAG_PAYLOAD_KEY],
            add_master_send_time=True,
        )


def broadcast_pose(app, payload: dict, *, add_master_send_time: bool = False) -> bool:
    client = app.get(MASTER_CLOUD_TRANSPORT_KEY)
    if client is None or not client.is_connected:
        return False

    wire_transport = "udp" if use_cloud_udp_transport() else "wss"
    packet = decorate_master_payload(
        app,
        payload,
        link_name="cloud",
        transport=wire_transport,
        add_master_send_time=add_master_send_time,
    )

    if use_cloud_udp_transport():
        try:
            encoded_size = len(
                json.dumps(packet, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            )
            if encoded_size > MASTER_UDP_MAX_PACKET_BYTES:
                raise ValueError(
                    f"cloud udp payload too large ({encoded_size} bytes > "
                    f"{MASTER_UDP_MAX_PACKET_BYTES} bytes)"
                )
        except ValueError as error:
            log_pose(
                f"[{datetime.now().strftime('%H:%M:%S')}] [cloud] dropped payload: {error}"
            )
            return False

    loop = asyncio.get_running_loop()
    loop.create_task(client.send_payload(packet))
    return True
