import asyncio
import json
from datetime import datetime

from ...config import MASTER_UDP_HOST, MASTER_UDP_PORT
from ...state import (
    MASTER_SLAVE_PEERS_KEY,
    MASTER_UDP_PROTOCOL_KEY,
    MASTER_UDP_TRANSPORT_KEY,
)
from ..pose_protocol import handle_slave_control_message, log_pose, peer_label
from .pose import send_pose_packet


def send_master_snapshot(app, peer_key) -> None:
    from ..pose_protocol import MASTER_STREAM_READY_MESSAGE_TYPE
    from ...state import (
        MASTER_LATEST_APRILTAG_PAYLOAD_KEY,
        MASTER_LATEST_DETECTION_STATE_KEY,
        MASTER_LATEST_INITIAL_CALIBRATION_KEY,
    )
    from ...utils import current_utc_iso_timestamp

    send_pose_packet(
        app,
        peer_key,
        {
            "type": MASTER_STREAM_READY_MESSAGE_TYPE,
            "server_time": current_utc_iso_timestamp(),
            "has_detection_state": app[MASTER_LATEST_DETECTION_STATE_KEY] is not None,
            "has_initial_calibration": app[MASTER_LATEST_INITIAL_CALIBRATION_KEY] is not None,
            "has_apriltag_detections": app[MASTER_LATEST_APRILTAG_PAYLOAD_KEY] is not None,
        },
    )

    if app[MASTER_LATEST_DETECTION_STATE_KEY] is not None:
        send_pose_packet(
            app,
            peer_key,
            app[MASTER_LATEST_DETECTION_STATE_KEY],
            add_server_send_time=True,
        )

    if app[MASTER_LATEST_INITIAL_CALIBRATION_KEY] is not None:
        send_pose_packet(
            app,
            peer_key,
            app[MASTER_LATEST_INITIAL_CALIBRATION_KEY],
            add_server_send_time=True,
        )

    if app[MASTER_LATEST_APRILTAG_PAYLOAD_KEY] is not None:
        send_pose_packet(
            app,
            peer_key,
            app[MASTER_LATEST_APRILTAG_PAYLOAD_KEY],
            add_server_send_time=True,
        )


class LocalMasterUdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, app):
        self.app = app
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        self.app[MASTER_UDP_TRANSPORT_KEY] = transport
        sockname = transport.get_extra_info("sockname")
        log_pose(
            f"[{datetime.now().strftime('%H:%M:%S')}] [local] master udp listening on "
            f"{sockname[0]}:{sockname[1]}"
        )

    def datagram_received(self, data, addr):
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            log_pose(
                f"[{datetime.now().strftime('%H:%M:%S')}] [local] invalid udp packet from "
                f"{peer_label(addr)}"
            )
            return

        handle_slave_control_message(
            self.app,
            addr,
            payload,
            send_snapshot=send_master_snapshot,
        )

    def error_received(self, exc):
        log_pose(f"[local] master udp error: {exc}")

    def connection_lost(self, exc):
        self.app[MASTER_UDP_TRANSPORT_KEY] = None
        self.app[MASTER_UDP_PROTOCOL_KEY] = None
        self.app[MASTER_SLAVE_PEERS_KEY].clear()
        if exc is not None:
            log_pose(f"[local] master udp transport closed with error: {exc}")


async def start_local_master_udp(app) -> None:
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: LocalMasterUdpProtocol(app),
        local_addr=(MASTER_UDP_HOST, MASTER_UDP_PORT),
    )
    app[MASTER_UDP_TRANSPORT_KEY] = transport
    app[MASTER_UDP_PROTOCOL_KEY] = protocol


async def close_local_master_udp(app) -> None:
    transport = app.get(MASTER_UDP_TRANSPORT_KEY)
    if transport is not None:
        transport.close()

    app[MASTER_UDP_TRANSPORT_KEY] = None
    app[MASTER_UDP_PROTOCOL_KEY] = None
    app[MASTER_SLAVE_PEERS_KEY].clear()
