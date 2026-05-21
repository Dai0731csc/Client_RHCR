"""Shared raw-pose stream protocol (local + cloud outbound links)."""

from datetime import datetime

from ..state import (
    MASTER_LATEST_APRILTAG_PAYLOAD_KEY,
    MASTER_LATEST_DETECTION_STATE_KEY,
    MASTER_LATEST_INITIAL_CALIBRATION_KEY,
    MASTER_SLAVE_PEERS_KEY,
    MASTER_UDP_SEQUENCE_KEY,
)
from ..utils import current_utc_iso_timestamp
from ..utils import with_master_send_time

MASTER_STREAM_PROTOCOL = "rhcr-oulu.raw-pose-stream"
SLAVE_SUBSCRIBE_MESSAGE_TYPE = "slave_subscribe"
SLAVE_UNSUBSCRIBE_MESSAGE_TYPE = "slave_unsubscribe"
MASTER_STREAM_READY_MESSAGE_TYPE = "master_stream_ready"
MASTER_STREAM_DATA_TYPES = {
    "detection_state",
    "initial_calibration",
    "apriltag_detections",
}

CLOUD_PEER_KEY = ("cloud", 0)

_TRANSPORT_BY_LINK = {
    "local": "udp",
    "cloud": "wss",
}


def log_pose(message: str) -> None:
    print(f"[TeleProgram] {message}")


def peer_label(addr) -> str:
    return f"{addr[0]}:{addr[1]}"


def _next_master_sequence(app) -> int:
    app[MASTER_UDP_SEQUENCE_KEY] += 1
    return app[MASTER_UDP_SEQUENCE_KEY]


def decorate_master_payload(
    app,
    payload: dict,
    *,
    link_name: str,
    transport: str | None = None,
    add_master_send_time: bool = False,
) -> dict:
    packet = with_master_send_time(payload) if add_master_send_time else dict(payload)
    packet["protocol"] = MASTER_STREAM_PROTOCOL
    packet["transport"] = transport or _TRANSPORT_BY_LINK.get(link_name, link_name)
    if packet.get("type") in MASTER_STREAM_DATA_TYPES:
        packet["master_seq"] = _next_master_sequence(app)
    return packet


def build_master_snapshot_payloads(app) -> list[tuple[dict, bool]]:
    payloads: list[tuple[dict, bool]] = [
        (
            {
                "type": MASTER_STREAM_READY_MESSAGE_TYPE,
                "master_time": current_utc_iso_timestamp(),
                "has_detection_state": app[MASTER_LATEST_DETECTION_STATE_KEY] is not None,
                "has_initial_calibration": app[MASTER_LATEST_INITIAL_CALIBRATION_KEY] is not None,
                "has_apriltag_detections": app[MASTER_LATEST_APRILTAG_PAYLOAD_KEY] is not None,
            },
            False,
        )
    ]
    if app[MASTER_LATEST_DETECTION_STATE_KEY] is not None:
        payloads.append((app[MASTER_LATEST_DETECTION_STATE_KEY], True))
    if app[MASTER_LATEST_INITIAL_CALIBRATION_KEY] is not None:
        payloads.append((app[MASTER_LATEST_INITIAL_CALIBRATION_KEY], True))
    if app[MASTER_LATEST_APRILTAG_PAYLOAD_KEY] is not None:
        payloads.append((app[MASTER_LATEST_APRILTAG_PAYLOAD_KEY], True))
    return payloads


def register_slave_peer(app, peer_key, payload: dict) -> bool:
    peers = app[MASTER_SLAVE_PEERS_KEY]
    is_new_peer = peer_key not in peers
    peers[peer_key] = {
        "client_time": payload.get("client_time"),
        "client_label": payload.get("client_label"),
        "tracked_tag_id": payload.get("tracked_tag_id"),
        "wants_snapshot": payload.get("wants_snapshot", True),
    }
    return is_new_peer


def remove_slave_peer(app, peer_key, *, reason: str = "client_request") -> None:
    peer = app[MASTER_SLAVE_PEERS_KEY].pop(peer_key, None)
    if peer is None:
        return
    log_pose(
        f"[{datetime.now().strftime('%H:%M:%S')}] master removed slave peer "
        f"({peer_label(peer_key)}, reason={reason})"
    )


def handle_slave_control_message(app, peer_key, payload: dict, *, send_snapshot) -> None:
    message_type = payload.get("type")

    if message_type == SLAVE_SUBSCRIBE_MESSAGE_TYPE:
        is_new_peer = register_slave_peer(app, peer_key, payload)
        if is_new_peer:
            log_pose(
                f"[{datetime.now().strftime('%H:%M:%S')}] master registered slave peer: "
                f"{peer_label(peer_key)}"
            )
        if payload.get("wants_snapshot", True):
            send_snapshot(app, peer_key)
        return

    if message_type == SLAVE_UNSUBSCRIBE_MESSAGE_TYPE:
        remove_slave_peer(app, peer_key, reason="unsubscribe")
