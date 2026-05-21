import asyncio
import json
import logging
import errno
import ssl
from typing import AsyncIterator, Optional
from urllib.parse import urlsplit
from pathlib import Path

import aiohttp

from ...relay_clock_sync import RelayClockSyncClient
from .protocol import (
    RELAY_ACTION_CLOCK_SYNC_PUBLISH,
    RELAY_ACTION_ERROR,
    RELAY_ACTION_PEER_CONNECTED,
    RELAY_ACTION_PEER_DISCONNECTED,
    RELAY_ACTION_REGISTER,
    RELAY_ACTION_REGISTERED,
    RELAY_ENVELOPE_CONTROL,
    RELAY_ENVELOPE_DATA,
    RELAY_ROLE_MASTER,
    STREAM_CLOSED_INTERNAL_TYPE,
)

logger = logging.getLogger(__name__)


def _is_tls_mismatch_error(error: BaseException) -> bool:
    current = error
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (aiohttp.ClientConnectorSSLError, ssl.SSLError)):
            message = str(current).lower()
            if "record layer failure" in message or "wrong version number" in message:
                return True
        current = current.__cause__ or current.__context__
    return False


def _encode_data_envelope(payload: dict) -> str:
    return json.dumps(
        {"relay_envelope": RELAY_ENVELOPE_DATA, "payload": payload},
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _registration_disconnect_error(
    msg: aiohttp.WSMessage,
    ws: aiohttp.ClientWebSocketResponse,
) -> RuntimeError | BaseException:
    if msg.type == aiohttp.WSMsgType.ERROR:
        return ws.exception() or RuntimeError("relay websocket errored before registration completed")
    if msg.type in {
        aiohttp.WSMsgType.CLOSE,
        aiohttp.WSMsgType.CLOSED,
        aiohttp.WSMsgType.CLOSING,
    }:
        return RuntimeError("relay server disconnected before registration completed")
    return RuntimeError(f"unexpected websocket message before registration: {msg.type}")


def _find_cause(error: BaseException, predicate) -> BaseException | None:
    current = error
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if predicate(current):
            return current
        current = current.__cause__ or current.__context__
    return None


def _is_connection_refused_error(error: BaseException) -> bool:
    return _find_cause(
        error,
        lambda exc: isinstance(exc, OSError) and getattr(exc, "errno", None) == errno.ECONNREFUSED,
    ) is not None


def _build_client_ssl_value(*, url: str, tls_verify: bool, tls_ca_file: str) -> bool | ssl.SSLContext | None:
    if urlsplit(url).scheme != "wss":
        return None
    if not tls_verify:
        return False
    if not tls_ca_file:
        return None

    cafile = Path(tls_ca_file)
    if not cafile.is_file():
        raise FileNotFoundError(f"TLS CA file not found: {cafile}")
    if cafile.stat().st_size == 0:
        raise ValueError(f"TLS CA file is empty: {cafile}")
    return ssl.create_default_context(cafile=str(cafile))


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
        connect_headers: Optional[dict] = None,
        tls_verify: bool = True,
        tls_ca_file: str = "",
    ):
        self.url = url
        self.role = role
        self.session_id = session_id
        self.token = token
        self.reconnect_delay_s = reconnect_delay_s
        self.label = label or role
        self.metadata = metadata or {}
        self.connect_headers = connect_headers or {}
        self.tls_verify = tls_verify
        self.tls_ca_file = tls_ca_file

        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._reader_task: Optional[asyncio.Task] = None
        self._connected = asyncio.Event()
        self._peer_connected = asyncio.Event()
        self._closed = False
        self._peer_connected_callbacks: list = []
        self.skew_cloud_vs_master_ms: float | None = None
        self.clock_sync_rtt_cloud_ms: float | None = None

    def on_peer_connected(self, callback):
        self._peer_connected_callbacks.append(callback)

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set() and self._ws is not None and not self._ws.closed

    @property
    def peer_is_connected(self) -> bool:
        return self._peer_connected.is_set()

    def _refresh_connect_headers(self) -> None:
        try:
            from ...services.device_service import build_cloud_connect_headers

            self.connect_headers = build_cloud_connect_headers()
        except Exception:
            pass

    async def connect(self):
        if self.is_connected:
            return

        self.skew_cloud_vs_master_ms = None
        self.clock_sync_rtt_cloud_ms = None
        self._closed = False
        self._refresh_connect_headers()
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

        try:
            ws_connect_kwargs = {"heartbeat": 20}
            ssl_value = _build_client_ssl_value(
                url=self.url,
                tls_verify=self.tls_verify,
                tls_ca_file=self.tls_ca_file,
            )
            if ssl_value is not None:
                ws_connect_kwargs["ssl"] = ssl_value
            if self.connect_headers:
                ws_connect_kwargs["headers"] = self.connect_headers
            self._ws = await self._session.ws_connect(self.url, **ws_connect_kwargs)
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
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError(f"relay register timed out for session={self.session_id}")

                msg = await asyncio.wait_for(self._ws.receive(), timeout=remaining)
                if msg.type != aiohttp.WSMsgType.TEXT:
                    if msg.type != aiohttp.WSMsgType.BINARY:
                        raise _registration_disconnect_error(msg, self._ws)
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

            await self._run_clock_sync_at_connect()
        except Exception as error:
            if self._ws is not None and not self._ws.closed:
                await self._ws.close()
            self._ws = None

            if self._session is not None and not self._session.closed:
                await self._session.close()
            self._session = None

            if _is_tls_mismatch_error(error):
                raise RuntimeError(
                    "relay TLS handshake failed for "
                    f"{self.url}. The relay is likely serving plain ws/http while "
                    "client/config/cloud.json has cloud_use_tls=true. "
                    "Set cloud_use_tls to false or enable TLS on the relay."
                ) from error
            if isinstance(error, FileNotFoundError):
                raise RuntimeError(
                    f"relay TLS CA file is missing: {error}. "
                    "Set cloud_tls_ca_file in client/config/cloud.json "
                    "(or use tls_ca_file as a fallback) to a valid certificate path."
                ) from error
            if isinstance(error, ValueError) and "TLS CA file is empty" in str(error):
                raise RuntimeError(
                    f"relay TLS CA file is empty: {error}. "
                    "Replace it with the relay CA certificate, clear cloud_tls_ca_file "
                    "to use system CAs, or set cloud_tls_verify to false for temporary testing."
                ) from error
            if isinstance(error, aiohttp.ClientConnectorCertificateError):
                raise RuntimeError(
                    "relay TLS certificate verification failed for "
                    f"{self.url}. If you are using a self-signed certificate, "
                    "set cloud_tls_ca_file in client/config/cloud.json "
                    "(or tls_ca_file as a fallback) to the CA certificate, "
                    "or set cloud_tls_verify to false for temporary testing."
                ) from error
            if isinstance(error, aiohttp.ClientConnectorError) and _is_connection_refused_error(error):
                raise RuntimeError(
                    "relay TCP connect failed for "
                    f"{self.url}. The remote host refused the connection, which usually means "
                    "the cloud relay process is not listening on that host/port, the port is wrong, "
                    "or a firewall/NAT rule is blocking it."
                ) from error
            raise

        self._connected.set()
        self._reader_task = asyncio.create_task(
            self._reader_loop(),
            name=f"cloud-ws-reader-{self.label}",
        )

    async def _run_clock_sync_at_connect(self) -> None:
        if self._ws is None:
            return

        sync_client = RelayClockSyncClient()
        try:
            result = await sync_client.sync_over_ws(
                self._ws,
                role=self.role,
                session_id=self.session_id,
            )
        except Exception as error:
            logger.warning("[%s] relay clock sync failed: %s", self.label, error)
            return

        self.skew_cloud_vs_master_ms = result.offset_ms
        self.clock_sync_rtt_cloud_ms = result.rtt_ms
        await self._ws.send_str(
            json.dumps(
                {
                    "relay_envelope": RELAY_ENVELOPE_CONTROL,
                    "relay_action": RELAY_ACTION_CLOCK_SYNC_PUBLISH,
                    "role": self.role,
                    "session_id": self.session_id,
                    "skew_cloud_vs_master_ms": result.offset_ms,
                    "clock_sync_rtt_cloud_ms": result.rtt_ms,
                },
                separators=(",", ":"),
                ensure_ascii=False,
            )
        )
        logger.info(
            "[%s] relay clock sync cloud_offset_ms=%.2f rtt_ms=%.2f samples=%s",
            self.label,
            result.offset_ms,
            result.rtt_ms,
            result.sample_count,
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
            logger.warning("[%s] cloud ws reader stopped: %s", self.label, error, exc_info=True)
        finally:
            self._connected.clear()
            self._peer_connected.clear()
            await self._queue.put({"type": STREAM_CLOSED_INTERNAL_TYPE})
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
            expected_network_error = (
                isinstance(error, aiohttp.ClientConnectorError)
                or _is_connection_refused_error(error)
                or (
                    isinstance(error, RuntimeError)
                    and (
                        str(error).startswith("relay TCP connect failed for ")
                        or str(error).startswith("relay TLS handshake failed for ")
                        or str(error).startswith("relay TLS certificate verification failed for ")
                    )
                )
            )
            logger.warning(
                "[%s] cloud ws reconnect failed: %s",
                self.label,
                error,
                exc_info=not expected_network_error,
            )
            asyncio.create_task(self._reconnect(), name=f"cloud-ws-reconnect-{self.label}")

    async def send_payload(self, payload: dict):
        if not self.is_connected:
            raise RuntimeError("cloud relay is not connected")
        await self._ws.send_str(_encode_data_envelope(payload))

    async def iter_payloads(self) -> AsyncIterator[dict]:
        while True:
            payload = await self._queue.get()
            if payload.get("type") == STREAM_CLOSED_INTERNAL_TYPE and self._closed:
                break
            yield payload

    async def close(self):
        self._closed = True
        self._connected.clear()
        self._peer_connected.clear()
        self.skew_cloud_vs_master_ms = None
        self.clock_sync_rtt_cloud_ms = None

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
