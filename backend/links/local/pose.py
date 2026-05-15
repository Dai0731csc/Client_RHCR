import json
from datetime import datetime

from ...config import MASTER_UDP_MAX_PACKET_BYTES
from ...state import MASTER_SLAVE_PEERS_KEY, MASTER_UDP_TRANSPORT_KEY
from ..pose_protocol import decorate_master_payload, log_pose, peer_label


def encode_udp_payload(payload: dict) -> bytes:
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(encoded) > MASTER_UDP_MAX_PACKET_BYTES:
        raise ValueError(
            f"UDP payload too large ({len(encoded)} bytes > {MASTER_UDP_MAX_PACKET_BYTES} bytes)"
        )
    return encoded


def send_pose_packet(app, peer_key, payload: dict, *, add_server_send_time: bool = False) -> bool:
    transport = app.get(MASTER_UDP_TRANSPORT_KEY)
    if transport is None:
        return False

    packet = decorate_master_payload(
        app,
        payload,
        link_name="local",
        add_server_send_time=add_server_send_time,
    )
    try:
        transport.sendto(encode_udp_payload(packet), peer_key)
    except ValueError as error:
        log_pose(
            f"[{datetime.now().strftime('%H:%M:%S')}] dropped local udp payload for "
            f"{peer_label(peer_key)}: {error}"
        )
        return False
    return True


def broadcast_pose(app, payload: dict, *, add_server_send_time: bool = False) -> None:
    packet = decorate_master_payload(
        app,
        payload,
        link_name="local",
        add_server_send_time=add_server_send_time,
    )
    transport = app.get(MASTER_UDP_TRANSPORT_KEY)
    if transport is None:
        return

    encoded = encode_udp_payload(packet)
    for peer_key in list(app[MASTER_SLAVE_PEERS_KEY]):
        try:
            transport.sendto(encoded, peer_key)
        except ValueError as error:
            log_pose(
                f"[{datetime.now().strftime('%H:%M:%S')}] dropped local udp payload for "
                f"{peer_label(peer_key)}: {error}"
            )
