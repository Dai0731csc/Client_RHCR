import asyncio
import json
from datetime import datetime

from .common import current_utc_iso_timestamp, with_server_send_time
from .config import (
    MASTER_UDP_HOST,
    MASTER_UDP_MAX_PACKET_BYTES,
    MASTER_UDP_PORT,
)
from .state import (
    MASTER_LATEST_APRILTAG_PAYLOAD_KEY,
    MASTER_LATEST_DETECTION_STATE_KEY,
    MASTER_LATEST_INITIAL_CALIBRATION_KEY,
    MASTER_SLAVE_PEERS_KEY,
    MASTER_UDP_PROTOCOL_KEY,
    MASTER_UDP_SEQUENCE_KEY,
    MASTER_UDP_TRANSPORT_KEY,
)

MASTER_STREAM_PROTOCOL = "robotic-haircutting.raw-pose-stream.v1"
SLAVE_SUBSCRIBE_MESSAGE_TYPE = "slave_subscribe"
SLAVE_UNSUBSCRIBE_MESSAGE_TYPE = "slave_unsubscribe"
MASTER_STREAM_READY_MESSAGE_TYPE = "master_stream_ready"
MASTER_STREAM_DATA_TYPES = {
    "detection_state",
    "initial_calibration",
    "apriltag_detections",
}


def _log(message):
    print(f"[TeleProgram] {message}")


def _peer_label(addr):
    return f"{addr[0]}:{addr[1]}"


def _next_master_sequence(app):
    app[MASTER_UDP_SEQUENCE_KEY] += 1
    return app[MASTER_UDP_SEQUENCE_KEY]


def _encode_payload(payload):
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(encoded) > MASTER_UDP_MAX_PACKET_BYTES:
        raise ValueError(
            f"UDP payload too large ({len(encoded)} bytes > {MASTER_UDP_MAX_PACKET_BYTES} bytes)"
        )
    return encoded


def _master_transport_name():
    from .relay_master import use_relay_transport

    return "wss" if use_relay_transport() else "udp"


def _decorate_master_payload(app, payload, *, add_server_send_time=False):
    packet = with_server_send_time(payload) if add_server_send_time else dict(payload)
    packet["protocol"] = MASTER_STREAM_PROTOCOL
    packet["transport"] = _master_transport_name()
    if packet.get("type") in MASTER_STREAM_DATA_TYPES:
        packet["master_seq"] = _next_master_sequence(app)
    return packet


def _send_master_payload(app, peer_key, payload, *, add_server_send_time=False):
    packet = _decorate_master_payload(app, payload, add_server_send_time=add_server_send_time)

    from .relay_master import RELAY_PEER_KEY, send_master_relay_payload, use_relay_transport

    if use_relay_transport():
        if peer_key != RELAY_PEER_KEY:
            return False
        try:
            encoded_size = len(
                json.dumps(packet, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            )
            if encoded_size > MASTER_UDP_MAX_PACKET_BYTES:
                raise ValueError(
                    f"relay payload too large ({encoded_size} bytes > "
                    f"{MASTER_UDP_MAX_PACKET_BYTES} bytes)"
                )
        except ValueError as error:
            _log(
                f"[{datetime.now().strftime('%H:%M:%S')}] dropped master relay payload for "
                f"{_peer_label(peer_key)}: {error}"
            )
            return False
        return send_master_relay_payload(app, packet)

    transport = app.get(MASTER_UDP_TRANSPORT_KEY)
    if transport is None:
        return False

    try:
        transport.sendto(_encode_payload(packet), peer_key)
    except ValueError as error:
        _log(
            f"[{datetime.now().strftime('%H:%M:%S')}] dropped master udp payload for "
            f"{_peer_label(peer_key)}: {error}"
        )
        return False

    return True


def register_slave_peer(app, peer_key, payload):
    peers = app[MASTER_SLAVE_PEERS_KEY]
    is_new_peer = peer_key not in peers
    peers[peer_key] = {
        "client_time": payload.get("client_time"),
        "client_label": payload.get("client_label"),
        "tracked_tag_id": payload.get("tracked_tag_id"),
        "wants_snapshot": payload.get("wants_snapshot", True),
    }
    return is_new_peer


def remove_slave_peer(app, peer_key, *, reason="client_request"):
    peer = app[MASTER_SLAVE_PEERS_KEY].pop(peer_key, None)
    if peer is None:
        return

    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] master removed slave peer "
        f"({_peer_label(peer_key)}, reason={reason})"
    )


def handle_slave_control_message(app, peer_key, payload):
    message_type = payload.get("type")

    if message_type == SLAVE_SUBSCRIBE_MESSAGE_TYPE:
        is_new_peer = register_slave_peer(app, peer_key, payload)
        if is_new_peer:
            _log(
                f"[{datetime.now().strftime('%H:%M:%S')}] master registered slave peer: "
                f"{_peer_label(peer_key)}"
            )
        if payload.get("wants_snapshot", True):
            send_master_snapshot(app, peer_key)
        return

    if message_type == SLAVE_UNSUBSCRIBE_MESSAGE_TYPE:
        remove_slave_peer(app, peer_key, reason="unsubscribe")


def send_master_snapshot(app, peer_key):
    _send_master_payload(
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
        _send_master_payload(
            app,
            peer_key,
            app[MASTER_LATEST_DETECTION_STATE_KEY],
            add_server_send_time=True,
        )

    if app[MASTER_LATEST_INITIAL_CALIBRATION_KEY] is not None:
        _send_master_payload(
            app,
            peer_key,
            app[MASTER_LATEST_INITIAL_CALIBRATION_KEY],
            add_server_send_time=True,
        )

    if app[MASTER_LATEST_APRILTAG_PAYLOAD_KEY] is not None:
        _send_master_payload(
            app,
            peer_key,
            app[MASTER_LATEST_APRILTAG_PAYLOAD_KEY],
            add_server_send_time=True,
        )


def broadcast_master_payload(app, payload, *, add_server_send_time=False):
    for peer_key in list(app[MASTER_SLAVE_PEERS_KEY]):
        _send_master_payload(app, peer_key, payload, add_server_send_time=add_server_send_time)


class MasterUdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, app):
        self.app = app
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        self.app[MASTER_UDP_TRANSPORT_KEY] = transport
        sockname = transport.get_extra_info("sockname")
        _log(
            f"[{datetime.now().strftime('%H:%M:%S')}] master udp listening on "
            f"{sockname[0]}:{sockname[1]}"
        )

    def datagram_received(self, data, addr):
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _log(
                f"[{datetime.now().strftime('%H:%M:%S')}] invalid master udp packet from "
                f"{_peer_label(addr)}"
            )
            return

        handle_slave_control_message(self.app, addr, payload)

    def error_received(self, exc):
        _log(f"master udp error: {exc}")

    def connection_lost(self, exc):
        self.app[MASTER_UDP_TRANSPORT_KEY] = None
        self.app[MASTER_UDP_PROTOCOL_KEY] = None
        self.app[MASTER_SLAVE_PEERS_KEY].clear()
        if exc is not None:
            _log(f"master udp transport closed with error: {exc}")


async def start_master_transport(app):
    from .relay_master import start_master_relay, use_relay_transport

    if use_relay_transport():
        await start_master_relay(app)
        return

    await start_master_udp_server(app)


async def close_master_transport(app):
    from .relay_master import close_master_relay, use_relay_transport

    if use_relay_transport():
        await close_master_relay(app)
        return

    await close_master_udp_server(app)


async def start_master_udp_server(app):
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: MasterUdpProtocol(app),
        local_addr=(MASTER_UDP_HOST, MASTER_UDP_PORT),
    )
    app[MASTER_UDP_TRANSPORT_KEY] = transport
    app[MASTER_UDP_PROTOCOL_KEY] = protocol


async def close_master_udp_server(app):
    transport = app.get(MASTER_UDP_TRANSPORT_KEY)
    if transport is not None:
        transport.close()

    app[MASTER_UDP_TRANSPORT_KEY] = None
    app[MASTER_UDP_PROTOCOL_KEY] = None
    app[MASTER_SLAVE_PEERS_KEY].clear()
