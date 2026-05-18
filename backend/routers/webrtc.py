import asyncio
import json
from datetime import datetime

from aiohttp import web

from ..config import build_webrtc_client_config, create_rtc_configuration
from ..services.stream_service import ingest_apriltag_payload
from ..state import WEBRTC_PEER_CONNECTIONS_KEY
from ..utils import create_ack_payload


def _log(message):
    print(f"[TeleProgram] {message}")


def import_aiortc():
    try:
        from aiortc import RTCPeerConnection, RTCSessionDescription
        from aiortc.rtcconfiguration import RTCConfiguration, RTCIceServer
    except ImportError as error:
        raise RuntimeError(
            "aiortc is required for WebRTC mode. Install it with `pip install aiortc`."
        ) from error

    return RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer


def describe_webrtc_error(error):
    if isinstance(error, asyncio.TimeoutError):
        return "WebRTC ICE gathering timed out"
    return str(error) or error.__class__.__name__


async def wait_for_ice_gathering_complete(peer_connection, timeout_s=5.0):
    if peer_connection.iceGatheringState == "complete":
        return

    done = asyncio.Event()

    @peer_connection.on("icegatheringstatechange")
    def _on_ice_gathering_state_change():
        if peer_connection.iceGatheringState == "complete":
            done.set()

    await asyncio.wait_for(done.wait(), timeout=timeout_s)


async def close_peer_connection(app, peer_connection):
    app[WEBRTC_PEER_CONNECTIONS_KEY].discard(peer_connection)
    if peer_connection.connectionState != "closed":
        await peer_connection.close()


def create_peer_connection(app, client_label):
    RTCPeerConnection, _, RTCConfiguration, RTCIceServer = import_aiortc()
    peer_connection = RTCPeerConnection(
        configuration=create_rtc_configuration(RTCConfiguration, RTCIceServer)
    )
    app[WEBRTC_PEER_CONNECTIONS_KEY].add(peer_connection)

    @peer_connection.on("connectionstatechange")
    async def _on_connection_state_change():
        _log(
            f"[{datetime.now().strftime('%H:%M:%S')}] webrtc state ({client_label}): "
            f"{peer_connection.connectionState}"
        )
        if peer_connection.connectionState == "connected":
            _log(
                f"[{datetime.now().strftime('%H:%M:%S')}] transport connected: "
                f"transport=webrtc channel=apriltag client={client_label}"
            )
        if peer_connection.connectionState in {"failed", "closed"}:
            await close_peer_connection(app, peer_connection)

    @peer_connection.on("datachannel")
    def _on_datachannel(channel):
        _log(
            f"[{datetime.now().strftime('%H:%M:%S')}] webrtc datachannel open request "
            f"({client_label}): {channel.label}"
        )

        @channel.on("message")
        def _on_message(message):
            if not isinstance(message, str):
                return

            async def _handle_message():
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    return

                message_type = payload.get("type")

                if message_type == "ping":
                    if channel.readyState == "open":
                        channel.send(json.dumps(create_ack_payload(payload)))
                    return

                if message_type == "time_sync_result":
                    _log(
                        f"[{datetime.now().strftime('%H:%M:%S')}] time sync result "
                        f"({payload.get('transport', f'webrtc:{channel.label}')}): "
                        f"status={payload.get('status', 'unknown')} "
                        f"sample_count={payload.get('sample_count', 'n/a')} "
                        f"offset_ms={payload.get('offset_ms', 'n/a')} "
                        f"rtt_ms={payload.get('rtt_ms', 'n/a')} "
                        f"completed_at={payload.get('completed_at', 'n/a')}"
                    )
                    return

                await ingest_apriltag_payload(
                    app,
                    payload,
                    source=f"webrtc:{channel.label}",
                )

            asyncio.create_task(_handle_message())

        @channel.on("close")
        def _on_close():
            _log(
                f"[{datetime.now().strftime('%H:%M:%S')}] webrtc datachannel closed "
                f"({client_label}): {channel.label}"
            )

    return peer_connection


async def webrtc_config_handler(_request):
    return web.json_response(build_webrtc_client_config())


async def webrtc_signaling_websocket_handler(request):
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)

    client = request.remote or "unknown"
    peer_connection = None
    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] signaling connected: "
        f"transport=webrtc-signaling client={client}"
    )
    await ws.send_json({"type": "webrtc_signaling_ready"})

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                except json.JSONDecodeError:
                    await ws.send_json({"type": "webrtc_error", "message": "invalid JSON"})
                    continue

                if payload.get("type") != "webrtc_offer":
                    continue

                try:
                    _, RTCSessionDescription, _, _ = import_aiortc()
                except RuntimeError as error:
                    await ws.send_json({"type": "webrtc_error", "message": str(error)})
                    continue

                try:
                    if peer_connection is not None:
                        await close_peer_connection(request.app, peer_connection)

                    peer_connection = create_peer_connection(request.app, client)
                    offer = RTCSessionDescription(sdp=payload.get("sdp"), type="offer")
                    await peer_connection.setRemoteDescription(offer)
                    answer = await peer_connection.createAnswer()
                    await peer_connection.setLocalDescription(answer)
                    await wait_for_ice_gathering_complete(peer_connection)

                    await ws.send_json(
                        {
                            "type": "webrtc_answer",
                            "sdp": peer_connection.localDescription.sdp,
                        }
                    )
                except Exception as error:
                    message = describe_webrtc_error(error)
                    _log(
                        f"[{datetime.now().strftime('%H:%M:%S')}] webrtc signaling failed "
                        f"({client}): {message}"
                    )
                    if peer_connection is not None:
                        await close_peer_connection(request.app, peer_connection)
                        peer_connection = None
                    await ws.send_json({"type": "webrtc_error", "message": message})
                continue

            if msg.type == web.WSMsgType.ERROR:
                _log(f"webrtc signaling ws error: {ws.exception()}")
    finally:
        if peer_connection is not None:
            await close_peer_connection(request.app, peer_connection)
        _log(
            f"[{datetime.now().strftime('%H:%M:%S')}] signaling disconnected: "
            f"transport=webrtc-signaling client={client}"
        )

    return ws


async def close_webrtc_peers(app):
    for peer_connection in list(app[WEBRTC_PEER_CONNECTIONS_KEY]):
        await close_peer_connection(app, peer_connection)
