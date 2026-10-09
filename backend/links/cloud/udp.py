import asyncio
import json
import logging
from datetime import datetime

from ...config import (
    get_cloud_udp_host,
    get_cloud_udp_port,
    get_relay_session_id,
    get_relay_token,
    use_cloud_udp_transport,
)
from ...runtime_settings import get_runtime_settings
from ...relay_clock_sync import RelayClockSyncClient
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
from .protocol import RELAY_ACTION_FULL_CHAIN_TIME_SYNC_RESULT


def _log(message: str) -> None:
    print(f"[TeleProgram] {message}")


logger = logging.getLogger(__name__)

CLOCK_SYNC_PING_TYPE = "clock_sync_ping"
CLOCK_SYNC_ACK_TYPE = "clock_sync_ack"
CLOCK_SYNC_PUBLISH_TYPE = "clock_sync_publish"


class _CloudUdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, queue, sync_queue, on_transport_closed):
        self.queue = queue
        self.sync_queue = sync_queue
        self.on_transport_closed = on_transport_closed
        self.transport = None
        self._sync_active = False

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        del addr
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        if self._sync_active and payload.get("type") == CLOCK_SYNC_ACK_TYPE:
            self.sync_queue.put_nowait(payload)
            return
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
        self._sync_queue: asyncio.Queue = asyncio.Queue()
        self._protocol: _CloudUdpProtocol | None = None
        self._transport = None
        self._connected = asyncio.Event()
        self._peer_connected = asyncio.Event()
        self._closed = False
        self._control_message_callbacks: list = []
        self.skew_cloud_vs_master_ms: float | None = None
        self.clock_sync_rtt_cloud_ms: float | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set() and self._transport is not None

    @property
    def peer_is_connected(self) -> bool:
        return self._peer_connected.is_set()

    def on_control_message(self, callback):
        self._control_message_callbacks.append(callback)

    async def connect(self):
        if self.is_connected:
            return

        self.skew_cloud_vs_master_ms = None
        self.clock_sync_rtt_cloud_ms = None
        self._closed = False
        self._peer_connected.clear()
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _CloudUdpProtocol(
                self._queue,
                self._sync_queue,
                self._handle_transport_closed,
            ),
            remote_addr=(self.host, self.port),
        )
        self._transport = transport
        self._protocol = protocol
        self._connected.set()
        await self._run_clock_sync_at_connect()

    async def resync_master_cloud(self, *, request_id: str | None = None) -> dict:
        del request_id
        result = await self._sync_master_cloud()
        self.skew_cloud_vs_master_ms = result.offset_ms
        self.clock_sync_rtt_cloud_ms = result.rtt_ms
        await self.send_payload(
            {
                "type": CLOCK_SYNC_PUBLISH_TYPE,
                "skew_cloud_vs_master_ms": result.offset_ms,
                "clock_sync_rtt_cloud_ms": result.rtt_ms,
            }
        )
        logger.info(
            "[%s] relay udp clock sync cloud_offset_ms=%.2f rtt_ms=%.2f samples=%s",
            self.label,
            result.offset_ms,
            result.rtt_ms,
            result.sample_count,
        )
        return {
            "offset_ms": result.offset_ms,
            "rtt_ms": result.rtt_ms,
            "sample_count": result.sample_count,
        }

    async def _run_clock_sync_at_connect(self) -> None:
        if self._protocol is None:
            return

        try:
            result = await self._sync_master_cloud()
        except Exception as error:
            logger.warning("[%s] relay udp clock sync failed: %s", self.label, error)
            return

        self.skew_cloud_vs_master_ms = result.offset_ms
        self.clock_sync_rtt_cloud_ms = result.rtt_ms
        await self.send_payload(
            {
                "type": CLOCK_SYNC_PUBLISH_TYPE,
                "skew_cloud_vs_master_ms": result.offset_ms,
                "clock_sync_rtt_cloud_ms": result.rtt_ms,
            }
        )
        logger.info(
            "[%s] relay udp clock sync cloud_offset_ms=%.2f rtt_ms=%.2f samples=%s",
            self.label,
            result.offset_ms,
            result.rtt_ms,
            result.sample_count,
        )

    async def _sync_master_cloud(self):
        sync_client = RelayClockSyncClient()
        assert self._protocol is not None
        self._protocol._sync_active = True
        try:

            async def send_ping(*, seq: int, sender_send_time: str) -> None:
                await self.send_payload(
                    {
                        "type": CLOCK_SYNC_PING_TYPE,
                        "seq": seq,
                        "sender_send_time": sender_send_time,
                    }
                )

            async def wait_ack(*, seq: int, initiator_send_ms: float, initiator_send_mono: float):
                import time

                deadline = time.perf_counter() + sync_client.timeout_s
                while time.perf_counter() < deadline:
                    remaining = deadline - time.perf_counter()
                    if remaining <= 0:
                        return None
                    try:
                        envelope = await asyncio.wait_for(
                            self._sync_queue.get(),
                            timeout=remaining,
                        )
                    except asyncio.TimeoutError:
                        return None
                    return sync_client._sample_from_ack(
                        envelope,
                        seq=seq,
                        initiator_send_ms=initiator_send_ms,
                        initiator_send_mono=initiator_send_mono,
                    )

            return await sync_client.sync_over_udp(
                send_ping=send_ping,
                wait_ack=wait_ack,
                role=self.role,
                session_id=self.session_id,
            )
        finally:
            self._protocol._sync_active = False

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

    async def send_control_message(self, action: str, **fields):
        await self.send_payload({"type": action, **fields})

    async def iter_payloads(self):
        while True:
            payload = await self._queue.get()
            if payload.get("type") == "_stream_closed":
                break
            yield payload

    async def close(self):
        self._closed = True
        self._connected.clear()
        self._peer_connected.clear()
        self.skew_cloud_vs_master_ms = None
        self.clock_sync_rtt_cloud_ms = None
        if self._transport is not None:
            self._transport.close()
        self._transport = None
        self._protocol = None
        await self._queue.put({"type": "_stream_closed"})

    def mark_peer_connected(self) -> None:
        self._peer_connected.set()

    def mark_peer_disconnected(self) -> None:
        self._peer_connected.clear()

    def dispatch_control_message(self, payload: dict) -> bool:
        if payload.get("type") != RELAY_ACTION_FULL_CHAIN_TIME_SYNC_RESULT:
            return False
        for callback in list(self._control_message_callbacks):
            outcome = callback(dict(payload))
            if asyncio.iscoroutine(outcome):
                asyncio.create_task(outcome)
        return True


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
                cloud_client.mark_peer_disconnected()
                remove_slave_peer(app, CLOUD_PEER_KEY, reason="unsubscribe")
                continue
            if message_type == SLAVE_SUBSCRIBE_MESSAGE_TYPE:
                cloud_client.mark_peer_connected()
                handle_slave_control_message(
                    app,
                    CLOUD_PEER_KEY,
                    payload,
                    send_snapshot=_send_snapshot,
                )
                continue
            if cloud_client.dispatch_control_message(payload):
                continue
    except asyncio.CancelledError:
        raise
    finally:
        cloud_client.mark_peer_disconnected()
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
