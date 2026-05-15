import asyncio
import json
import logging
from typing import AsyncIterator, Optional

import aiohttp

from .protocol import (
    RELAY_ACTION_ERROR,
    RELAY_ACTION_PEER_CONNECTED,
    RELAY_ACTION_PEER_DISCONNECTED,
    RELAY_ACTION_REGISTER,
    RELAY_ACTION_REGISTERED,
    RELAY_ENVELOPE_CONTROL,
    RELAY_ENVELOPE_DATA,
    RELAY_ROLE_MASTER,
)

logger = logging.getLogger(__name__)


def _encode_data_envelope(payload: dict) -> str:
    return json.dumps(
        {"relay_envelope": RELAY_ENVELOPE_DATA, "payload": payload},
        separators=(",", ":"),
        ensure_ascii=False,
    )


class CloudWsClient:
    def __init__(
        self,
        *,
        url: str,
        role: str = RELAY_ROLE_MASTER,
        session_id: str,
        token: str = "",
        reconnect_delay_s: float = 2.0,
        label: str = "",
        metadata: Optional[dict] = None,
    ):
        self.url = url
        self.role = role
        self.session_id = session_id
        self.token = token
        self.reconnect_delay_s = reconnect_delay_s
        self.label = label or role
        self.metadata = metadata or {}

        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._reader_task: Optional[asyncio.Task] = None
        self._connected = asyncio.Event()
        self._peer_connected = asyncio.Event()
        self._closed = False
        self._peer_connected_callbacks: list = []

    def on_peer_connected(self, callback):
        self._peer_connected_callbacks.append(callback)

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set() and self._ws is not None and not self._ws.closed

    @property
    def peer_is_connected(self) -> bool:
        return self._peer_connected.is_set()

    async def connect(self):
        if self.is_connected:
            return

        self._closed = False
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

        self._ws = await self._session.ws_connect(self.url, heartbeat=20)
        await self._ws.send_str(
            json.dumps(
                {
                    "relay_envelope": RELAY_ENVELOPE_CONTROL,
                    "relay_action": RELAY_ACTION_REGISTER,
                    "role": self.role,
                    "session_id": self.session_id,
                    "token": self.token,
                    "metadata": self.metadata,
                },
                separators=(",", ":"),
                ensure_ascii=False,
            )
        )

        registered = False
        deadline = asyncio.get_running_loop().time() + 10.0
        while not registered:
            if asyncio.get_running_loop().time() > deadline:
                raise TimeoutError(f"relay register timed out for session={self.session_id}")

            msg = await self._ws.receive()
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue

            envelope = json.loads(msg.data)
            if envelope.get("relay_envelope") != RELAY_ENVELOPE_CONTROL:
                continue

            action = envelope.get("relay_action")
            if action == RELAY_ACTION_REGISTERED:
                registered = True
                if envelope.get("peer_connected"):
                    self._peer_connected.set()
                logger.info(
                    "[%s] cloud ws registered session=%s peer_connected=%s",
                    self.label,
                    self.session_id,
                    envelope.get("peer_connected"),
                )
            elif action == RELAY_ACTION_ERROR:
                raise RuntimeError(envelope.get("message") or "relay registration failed")

        self._connected.set()
        self._reader_task = asyncio.create_task(
            self._reader_loop(),
            name=f"cloud-ws-reader-{self.label}",
        )

    async def _reader_loop(self):
        assert self._ws is not None

        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    envelope = json.loads(msg.data)
                    if envelope.get("relay_envelope") == RELAY_ENVELOPE_CONTROL:
                        action = envelope.get("relay_action")
                        if action == RELAY_ACTION_PEER_CONNECTED:
                            self._peer_connected.set()
                            for callback in list(self._peer_connected_callbacks):
                                asyncio.create_task(callback())
                        elif action == RELAY_ACTION_PEER_DISCONNECTED:
                            self._peer_connected.clear()
                        continue

                    if envelope.get("relay_envelope") == RELAY_ENVELOPE_DATA:
                        payload = envelope.get("payload")
                        if isinstance(payload, dict):
                            await self._queue.put(payload)
                    continue

                if msg.type in {
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                }:
                    break
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning("[%s] cloud ws reader stopped: %s", self.label, error)
        finally:
            self._connected.clear()
            self._peer_connected.clear()
            await self._queue.put({"type": "_stream_closed"})
            if not self._closed:
                asyncio.create_task(self._reconnect(), name=f"cloud-ws-reconnect-{self.label}")

    async def _reconnect(self):
        await asyncio.sleep(self.reconnect_delay_s)
        if self._closed:
            return
        try:
            await self.close()
            await self.connect()
        except Exception as error:
            logger.warning("[%s] cloud ws reconnect failed: %s", self.label, error)
            asyncio.create_task(self._reconnect(), name=f"cloud-ws-reconnect-{self.label}")

    async def send_payload(self, payload: dict):
        if not self.is_connected:
            raise RuntimeError("cloud relay is not connected")
        await self._ws.send_str(_encode_data_envelope(payload))

    async def iter_payloads(self) -> AsyncIterator[dict]:
        while True:
            payload = await self._queue.get()
            if payload.get("type") == "_stream_closed":
                break
            yield payload

    async def close(self):
        self._closed = True
        self._connected.clear()
        self._peer_connected.clear()

        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None

        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None
