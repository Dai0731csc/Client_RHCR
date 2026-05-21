import asyncio
import json
from datetime import datetime

from ...config import MASTER_UDP_MAX_PACKET_BYTES
from ...state import MASTER_CLOUD_TRANSPORT_KEY, MASTER_SLAVE_PEERS_KEY
from ..pose_protocol import (
    CLOUD_PEER_KEY,
    build_master_snapshot_payloads,
    decorate_master_payload,
    log_pose,
)


def _is_udp_mode(started_mode: str | None) -> bool:
    return started_mode == "cloud_udp"


def _wire_transport_for_mode(started_mode: str | None) -> str:
    return "udp" if _is_udp_mode(started_mode) else "wss"


def _log_send_result(task: asyncio.Task, *, started_mode: str | None) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception as error:
        transport = _wire_transport_for_mode(started_mode)
        log_pose(
            f"[{datetime.now().strftime('%H:%M:%S')}] [cloud] {transport} send failed: {error}"
        )


def send_master_snapshot(app, peer_key, *, started_mode: str | None) -> None:
    del peer_key
    for payload, add_master_send_time in build_master_snapshot_payloads(app):
        broadcast_pose(
            app,
            payload,
            started_mode=started_mode,
            add_master_send_time=add_master_send_time,
        )


def cloud_peer_ready(app, client, *, started_mode: str | None) -> bool:
    if client is None or not client.is_connected:
        return False
    if _is_udp_mode(started_mode):
        return CLOUD_PEER_KEY in (app.get(MASTER_SLAVE_PEERS_KEY) or {})
    if started_mode == "cloud_tcp":
        return bool(getattr(client, "peer_is_connected", False))
    return False


def broadcast_pose(
    app,
    payload: dict,
    *,
    started_mode: str | None,
    add_master_send_time: bool = False,
) -> bool:
    client = app.get(MASTER_CLOUD_TRANSPORT_KEY)
    if not cloud_peer_ready(app, client, started_mode=started_mode):
        return False

    wire_transport = _wire_transport_for_mode(started_mode)
    packet = decorate_master_payload(
        app,
        payload,
        link_name="cloud",
        transport=wire_transport,
        add_master_send_time=add_master_send_time,
    )
    if _is_udp_mode(started_mode):
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
    task = loop.create_task(client.send_payload(packet))
    task.add_done_callback(
        lambda completed_task: _log_send_result(completed_task, started_mode=started_mode)
    )
    return True
