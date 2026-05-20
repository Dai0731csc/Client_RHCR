import asyncio
import json
from datetime import datetime

from aiohttp import web

from ...config import get_relay_session_id, get_relay_token, use_local_tcp_transport
from ...state import (
    MASTER_LATEST_APRILTAG_PAYLOAD_KEY,
    MASTER_LATEST_DETECTION_STATE_KEY,
    MASTER_LATEST_INITIAL_CALIBRATION_KEY,
    MASTER_LOCAL_RELAY_PEERS_KEY,
)
from ...utils import current_utc_iso_timestamp
from ..pose_protocol import (
    decorate_master_payload,
    handle_slave_control_message,
    MASTER_STREAM_READY_MESSAGE_TYPE,
    peer_label,
    remove_slave_peer,
)
from ..cloud.protocol import (
    RELAY_ACTION_ERROR,
    RELAY_ACTION_REGISTER,
    RELAY_ACTION_REGISTERED,
    RELAY_ENVELOPE_CONTROL,
    RELAY_ENVELOPE_DATA,
    RELAY_ROLE_SLAVE,
)


def _log(message: str) -> None:
    print(f"[TeleProgram] {message}")


def _peer_key_from_request(request):
    peername = None
    if request.transport is not None:
        peername = request.transport.get_extra_info("peername")
    if isinstance(peername, tuple) and len(peername) >= 2:
        return (str(peername[0]), int(peername[1]))
    remote = str(request.remote or "unknown")
    return (remote, 0)


def register_local_relay_peer(app, peer_key, ws) -> None:
    app[MASTER_LOCAL_RELAY_PEERS_KEY][peer_key] = ws


def unregister_local_relay_peer(app, peer_key, *, reason: str) -> None:
    app[MASTER_LOCAL_RELAY_PEERS_KEY].pop(peer_key, None)
    remove_slave_peer(app, peer_key, reason=reason)


async def start_local_relay(app) -> None:
    app[MASTER_LOCAL_RELAY_PEERS_KEY].clear()


async def close_local_relay(app) -> None:
    peers = list(app[MASTER_LOCAL_RELAY_PEERS_KEY].items())
    app[MASTER_LOCAL_RELAY_PEERS_KEY].clear()
    for peer_key, ws in peers:
        remove_slave_peer(app, peer_key, reason="shutdown")
        if not ws.closed:
            await ws.close()


async def _send_to_peer(ws, payload: dict) -> None:
    if ws.closed:
        return
    await ws.send_str(
        json.dumps(
            {"relay_envelope": RELAY_ENVELOPE_DATA, "payload": payload},
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )


async def _broadcast_local_relay(peers: list[tuple[tuple[str, int], object]], packet: dict) -> list[tuple[str, int]]:
    stale_peers: list[tuple[str, int]] = []
    for peer_key, ws in peers:
        try:
            await _send_to_peer(ws, packet)
        except Exception:
            stale_peers.append(peer_key)
    return stale_peers


def broadcast_local_relay_payload(app, payload: dict, *, add_master_send_time: bool = False) -> bool:
    peers = [
        (peer_key, ws)
        for peer_key, ws in app[MASTER_LOCAL_RELAY_PEERS_KEY].items()
        if not ws.closed
    ]
    if not peers:
        return False

    packet = decorate_master_payload(
        app,
        payload,
        link_name="local",
        transport="wss",
        add_master_send_time=add_master_send_time,
    )

    async def _run() -> None:
        stale_peers = await _broadcast_local_relay(peers, packet)
        for peer_key in stale_peers:
            unregister_local_relay_peer(app, peer_key, reason="send_failed")

    asyncio.get_running_loop().create_task(_run())
    return True


def send_local_relay_gripper_command(app, command_payload: dict) -> bool:
    return broadcast_local_relay_payload(app, command_payload, add_master_send_time=False)


def send_local_relay_snapshot(app, peer_key) -> None:
    ws = app[MASTER_LOCAL_RELAY_PEERS_KEY].get(peer_key)
    if ws is None or ws.closed:
        return

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

    async def _run() -> None:
        for payload, add_master_send_time in payloads:
            packet = decorate_master_payload(
                app,
                payload,
                link_name="local",
                transport="wss",
                add_master_send_time=add_master_send_time,
            )
            try:
                await _send_to_peer(ws, packet)
            except Exception:
                unregister_local_relay_peer(app, peer_key, reason="snapshot_failed")
                break

    asyncio.get_running_loop().create_task(_run())


async def handle_local_relay_websocket(request, ws, *, send_snapshot) -> None:
    app = request.app
    peer_key = _peer_key_from_request(request)
    registered = False

    async for msg in ws:
        if msg.type != web.WSMsgType.TEXT:
            if msg.type == web.WSMsgType.ERROR:
                _log(f"local relay ws error: {ws.exception()}")
            continue

        try:
            envelope = json.loads(msg.data)
        except json.JSONDecodeError:
            continue

        if envelope.get("relay_envelope") != RELAY_ENVELOPE_CONTROL:
            if not registered or envelope.get("relay_envelope") != RELAY_ENVELOPE_DATA:
                continue
            payload = envelope.get("payload")
            if isinstance(payload, dict):
                handle_slave_control_message(app, peer_key, payload, send_snapshot=send_snapshot)
            continue

        if envelope.get("relay_action") != RELAY_ACTION_REGISTER:
            continue

        if not use_local_tcp_transport():
            await ws.send_str(
                json.dumps(
                    {
                        "relay_envelope": RELAY_ENVELOPE_CONTROL,
                        "relay_action": RELAY_ACTION_ERROR,
                        "message": "local relay is only enabled when client transport_mode=local_tcp",
                    },
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
            )
            break

        if envelope.get("role") != RELAY_ROLE_SLAVE:
            await ws.send_str(
                json.dumps(
                    {
                        "relay_envelope": RELAY_ENVELOPE_CONTROL,
                        "relay_action": RELAY_ACTION_ERROR,
                        "message": "local relay only accepts slave role",
                    },
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
            )
            break

        session_id = str(envelope.get("session_id") or "").strip()
        token = str(envelope.get("token") or "").strip()
        if session_id != get_relay_session_id():
            await ws.send_str(
                json.dumps(
                    {
                        "relay_envelope": RELAY_ENVELOPE_CONTROL,
                        "relay_action": RELAY_ACTION_ERROR,
                        "message": "local relay session_id mismatch",
                    },
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
            )
            break
        if get_relay_token() and token != get_relay_token():
            await ws.send_str(
                json.dumps(
                    {
                        "relay_envelope": RELAY_ENVELOPE_CONTROL,
                        "relay_action": RELAY_ACTION_ERROR,
                        "message": "local relay token mismatch",
                    },
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
            )
            break

        register_local_relay_peer(app, peer_key, ws)
        registered = True
        _log(
            f"[{datetime.now().strftime('%H:%M:%S')}] [local] relay peer connected: "
            f"{peer_label(peer_key)}"
        )
        await ws.send_str(
            json.dumps(
                {
                    "relay_envelope": RELAY_ENVELOPE_CONTROL,
                    "relay_action": RELAY_ACTION_REGISTERED,
                    "peer_connected": True,
                },
                separators=(",", ":"),
                ensure_ascii=False,
            )
        )

    if registered:
        _log(
            f"[{datetime.now().strftime('%H:%M:%S')}] [local] relay peer disconnected: "
            f"{peer_label(peer_key)}"
        )
        unregister_local_relay_peer(app, peer_key, reason="relay_disconnected")
