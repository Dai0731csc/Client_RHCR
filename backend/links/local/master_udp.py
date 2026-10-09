import asyncio
import json
from datetime import datetime

from ...config import get_master_udp_host, get_master_udp_port
from ...state import (
    MASTER_LOCAL_UDP_CONTROL_KEY,
    MASTER_SLAVE_PEERS_KEY,
    MASTER_UDP_PROTOCOL_KEY,
    MASTER_UDP_TRANSPORT_KEY,
)
from ...utils import current_utc_iso_timestamp
from ..pose_protocol import handle_slave_control_message, log_pose, peer_label
from .pose import encode_udp_payload, send_pose_packet

CLOCK_SYNC_PING_TYPE = "clock_sync_ping"
CLOCK_SYNC_ACK_TYPE = "clock_sync_ack"
FULL_CHAIN_TIME_SYNC_REQUEST_TYPE = "full_chain_time_sync_request"
FULL_CHAIN_TIME_SYNC_RESULT_TYPE = "full_chain_time_sync_result"


class LocalMasterUdpControl:
    def __init__(self, app):
        self._app = app
        self._callbacks: list = []

    @property
    def is_connected(self) -> bool:
        return self.peer_is_connected

    @property
    def peer_is_connected(self) -> bool:
        return bool(self._app[MASTER_SLAVE_PEERS_KEY])

    def on_control_message(self, callback):
        self._callbacks.append(callback)

    async def send_control_message(self, action: str, **fields):
        peer_key = self._latest_peer_key()
        transport = self._app.get(MASTER_UDP_TRANSPORT_KEY)
        if peer_key is None or transport is None:
            raise RuntimeError("local udp peer is not connected")
        payload = {"type": action, **fields}
        transport.sendto(encode_udp_payload(payload), peer_key)

    def handle_payload(self, payload: dict, addr) -> bool:
        message_type = payload.get("type")
        if message_type == CLOCK_SYNC_PING_TYPE:
            self._send_clock_sync_ack(addr, payload)
            return True
        if message_type != FULL_CHAIN_TIME_SYNC_RESULT_TYPE:
            return False
        for callback in list(self._callbacks):
            outcome = callback(dict(payload))
            if asyncio.iscoroutine(outcome):
                asyncio.create_task(outcome)
        return True

    def _latest_peer_key(self):
        peers = list(self._app[MASTER_SLAVE_PEERS_KEY])
        if not peers:
            return None
        return peers[-1]

    def _send_clock_sync_ack(self, addr, ping: dict) -> None:
        transport = self._app.get(MASTER_UDP_TRANSPORT_KEY)
        if transport is None:
            return
        master_receive_time = current_utc_iso_timestamp()
        master_send_time = current_utc_iso_timestamp()
        transport.sendto(
            json.dumps(
                {
                    "type": CLOCK_SYNC_ACK_TYPE,
                    "seq": ping.get("seq"),
                    "cloud_receive_time": master_receive_time,
                    "cloud_send_time": master_send_time,
                    "received": ping,
                },
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8"),
            addr,
        )


def send_master_snapshot(app, peer_key) -> None:
    from ..pose_protocol import build_master_snapshot_payloads

    for payload, add_master_send_time in build_master_snapshot_payloads(app):
        send_pose_packet(
            app,
            peer_key,
            payload,
            add_master_send_time=add_master_send_time,
        )


class LocalMasterUdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, app):
        self.app = app
        self.transport = None
        self.closed = asyncio.get_running_loop().create_future()

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
        if not isinstance(payload, dict):
            return

        control_plane = self.app.get(MASTER_LOCAL_UDP_CONTROL_KEY)
        if control_plane is not None and control_plane.handle_payload(payload, addr):
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
        if not self.closed.done():
            self.closed.set_result(None)
        if exc is not None:
            log_pose(f"[local] master udp transport closed with error: {exc}")


async def start_local_master_udp(app) -> None:
    app[MASTER_LOCAL_UDP_CONTROL_KEY] = LocalMasterUdpControl(app)
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: LocalMasterUdpProtocol(app),
        local_addr=(get_master_udp_host(), get_master_udp_port()),
    )
    app[MASTER_UDP_TRANSPORT_KEY] = transport
    app[MASTER_UDP_PROTOCOL_KEY] = protocol


async def close_local_master_udp(app) -> None:
    transport = app.get(MASTER_UDP_TRANSPORT_KEY)
    protocol = app.get(MASTER_UDP_PROTOCOL_KEY)
    if transport is not None:
        transport.close()
        if protocol is not None and hasattr(protocol, "closed"):
            await protocol.closed

    app[MASTER_UDP_TRANSPORT_KEY] = None
    app[MASTER_UDP_PROTOCOL_KEY] = None
    app[MASTER_SLAVE_PEERS_KEY].clear()
    app[MASTER_LOCAL_UDP_CONTROL_KEY] = None
