import asyncio
import json
from datetime import datetime

from ...config import (
    get_cloud_udp_host,
    get_cloud_udp_port,
    get_relay_session_id,
    get_relay_token,
    use_cloud_udp_transport,
)
from ...runtime_settings import get_runtime_settings
from ...state import MASTER_CLOUD_PUMP_TASK_KEY, MASTER_CLOUD_TRANSPORT_KEY
from ...services.device_service import get_host_label
from ..pose_protocol import (
    CLOUD_PEER_KEY,
    MASTER_STREAM_READY_MESSAGE_TYPE,
    MASTER_STREAM_PROTOCOL,
    SLAVE_SUBSCRIBE_MESSAGE_TYPE,
    SLAVE_UNSUBSCRIBE_MESSAGE_TYPE,
    decorate_master_payload,
    handle_slave_control_message,
    remove_slave_peer,
)


def _log(message: str) -> None:
    print(f"[TeleProgram] {message}")


class _CloudUdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, queue, on_transport_closed):
        self.queue = queue
        self.on_transport_closed = on_transport_closed
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        del addr
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            self.queue.put_nowait(payload)

    def error_received(self, exc):
        _log(f"[{datetime.now().strftime('%H:%M:%S')}] [cloud] udp error: {exc}")

    def connection_lost(self, exc):
        self.on_transport_closed()
        if exc is not None:
            _log(f"[{datetime.now().strftime('%H:%M:%S')}] [cloud] udp closed: {exc}")


class CloudUdpClient:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        role: str = "master",
        session_id: str,
        token: str = "",
        label: str = "",
        client_label: str = "",
    ):
        self.host = host
        self.port = port
        self.role = role
        self.session_id = session_id
        self.token = token
        self.label = label or role
        self.client_label = client_label or self.label

        self._queue: asyncio.Queue = asyncio.Queue()
        self._transport = None
        self._connected = asyncio.Event()
        self._closed = False

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set() and self._transport is not None

    async def connect(self):
        if self.is_connected:
            return

        self._closed = False
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _CloudUdpProtocol(self._queue, self._handle_transport_closed),
            remote_addr=(self.host, self.port),
        )
        self._transport = transport
        self._connected.set()

    def _handle_transport_closed(self):
        self._connected.clear()
        self._transport = None
        self._queue.put_nowait({"type": "_stream_closed"})

    def _encode_payload(self, payload: dict) -> bytes:
        packet = dict(payload)
        packet.setdefault("role", self.role)
        packet.setdefault("session_id", self.session_id)
        packet.setdefault("client_label", self.client_label)
        if self.token:
            packet.setdefault("token", self.token)
        return json.dumps(packet, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    async def send_payload(self, payload: dict):
        if not self.is_connected:
            raise RuntimeError("cloud udp is not connected")
        self._transport.sendto(self._encode_payload(payload))

    async def iter_payloads(self):
        while True:
            payload = await self._queue.get()
            if payload.get("type") == "_stream_closed":
                break
            yield payload

    async def close(self):
        self._closed = True
        self._connected.clear()
        if self._transport is not None:
            self._transport.close()
        self._transport = None
        await self._queue.put({"type": "_stream_closed"})


async def _udp_inbound_pump(app, cloud_client: CloudUdpClient) -> None:
    from .pose import send_master_snapshot

    def _send_snapshot(snapshot_app, peer_key) -> None:
        send_master_snapshot(snapshot_app, peer_key, started_mode="cloud_udp")

    try:
        async for payload in cloud_client.iter_payloads():
            message_type = payload.get("type")
            if message_type == "error":
                _log(
                    f"[{datetime.now().strftime('%H:%M:%S')}] [cloud] udp error: "
                    f"{payload.get('message') or 'unknown'}"
                )
                continue
            if message_type == SLAVE_UNSUBSCRIBE_MESSAGE_TYPE:
                remove_slave_peer(app, CLOUD_PEER_KEY, reason="unsubscribe")
                continue
            if message_type == SLAVE_SUBSCRIBE_MESSAGE_TYPE:
                handle_slave_control_message(
                    app,
                    CLOUD_PEER_KEY,
                    payload,
                    send_snapshot=_send_snapshot,
                )
                continue
    except asyncio.CancelledError:
        raise
    finally:
        remove_slave_peer(app, CLOUD_PEER_KEY, reason="cloud_udp_closed")


async def start_cloud_udp(app) -> None:
    if not use_cloud_udp_transport():
        return

    udp_host = get_cloud_udp_host()
    udp_port = get_cloud_udp_port()
    cloud_client = CloudUdpClient(
        host=udp_host,
        port=udp_port,
        role="master",
        session_id=get_relay_session_id(),
        token=get_relay_token(),
        label="TeleProgram",
        client_label=get_host_label(),
    )
    await cloud_client.connect()
    app[MASTER_CLOUD_TRANSPORT_KEY] = cloud_client
    app[MASTER_CLOUD_PUMP_TASK_KEY] = asyncio.create_task(_udp_inbound_pump(app, cloud_client))
    await cloud_client.send_payload(
        decorate_master_payload(
            app,
            {
                "type": MASTER_STREAM_READY_MESSAGE_TYPE,
                "protocol": MASTER_STREAM_PROTOCOL,
            },
            link_name="cloud",
            transport="udp",
            add_master_send_time=False,
        )
    )

    settings = get_runtime_settings()
    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] [cloud] udp ready on "
        f"udp://{udp_host}:{udp_port} (cloud_host={settings.cloud_host})"
    )


async def close_cloud_udp(app) -> None:
    pump_task = app.get(MASTER_CLOUD_PUMP_TASK_KEY)
    if pump_task is not None:
        pump_task.cancel()
        try:
            await pump_task
        except asyncio.CancelledError:
            pass
        app[MASTER_CLOUD_PUMP_TASK_KEY] = None

    cloud_client = app.get(MASTER_CLOUD_TRANSPORT_KEY)
    if cloud_client is not None:
        await cloud_client.close()
        app[MASTER_CLOUD_TRANSPORT_KEY] = None

    remove_slave_peer(app, CLOUD_PEER_KEY, reason="shutdown")
