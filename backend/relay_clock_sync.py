"""Relay clock sync (ping/ack); same convention as frontend/modules/time_sync.js."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def parse_iso_ms(value: Any) -> float | None:
    if value is None or not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.timestamp() * 1000.0


def _median(values: list[float]) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def compute_responder_offset_ms(
    *,
    initiator_send_ms: float,
    initiator_recv_ms: float,
    responder_receive_ms: float,
    responder_send_ms: float,
) -> tuple[float, float]:
    initiator_mid = (initiator_send_ms + initiator_recv_ms) / 2.0
    responder_mid = (responder_receive_ms + responder_send_ms) / 2.0
    offset_ms = responder_mid - initiator_mid
    rtt_ms = initiator_recv_ms - initiator_send_ms
    return offset_ms, rtt_ms


@dataclass(frozen=True)
class ClockSyncResult:
    offset_ms: float
    rtt_ms: float
    sample_count: int


class RelayClockSyncClient:
    def __init__(
        self,
        *,
        ping_action: str = "clock_sync_ping",
        ack_action: str = "clock_sync_ack",
        sample_count: int = 8,
        sleep_s: float = 0.06,
        timeout_s: float = 2.0,
    ):
        self.ping_action = ping_action
        self.ack_action = ack_action
        self.sample_count = sample_count
        self.sleep_s = sleep_s
        self.timeout_s = timeout_s

    async def _wait_for_ack(self, ws, *, seq: int, initiator_send_ms: float, initiator_send_mono: float):
        import time

        from aiohttp import WSMsgType

        deadline = time.perf_counter() + self.timeout_s
        while time.perf_counter() < deadline:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return None

            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=remaining)
            except asyncio.TimeoutError:
                return None

            if msg.type != WSMsgType.TEXT:
                continue

            try:
                envelope = json.loads(msg.data)
            except json.JSONDecodeError:
                continue

            if envelope.get("relay_envelope") != "control":
                continue

            action = envelope.get("relay_action")
            if action != self.ack_action:
                continue

            if envelope.get("seq") is not None and envelope.get("seq") != seq:
                continue

            initiator_recv_mono = time.perf_counter()
            initiator_recv_ms = initiator_send_ms + (
                initiator_recv_mono - initiator_send_mono
            ) * 1000.0

            cloud_recv_ms = parse_iso_ms(envelope.get("cloud_receive_time"))
            cloud_send_ms = parse_iso_ms(envelope.get("cloud_send_time"))
            if cloud_recv_ms is None or cloud_send_ms is None:
                continue

            offset_ms, _ = compute_responder_offset_ms(
                initiator_send_ms=initiator_send_ms,
                initiator_recv_ms=initiator_recv_ms,
                responder_receive_ms=cloud_recv_ms,
                responder_send_ms=cloud_send_ms,
            )
            rtt_ms = (initiator_recv_mono - initiator_send_mono) * 1000.0
            return (rtt_ms, offset_ms)

        return None

    async def sync_over_ws(
        self,
        ws,
        *,
        role: str,
        session_id: str,
    ) -> ClockSyncResult:
        import time

        samples: list[tuple[float, float, float]] = []

        for seq in range(self.sample_count):
            initiator_send_wall = datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z")
            initiator_send_mono = time.perf_counter()
            initiator_send_ms = parse_iso_ms(initiator_send_wall)
            if initiator_send_ms is None:
                continue

            await ws.send_str(
                json.dumps(
                    {
                        "relay_envelope": "control",
                        "relay_action": self.ping_action,
                        "seq": seq,
                        "role": role,
                        "session_id": session_id,
                        "sender_send_time": initiator_send_wall,
                    },
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
            )

            sample = await self._wait_for_ack(
                ws,
                seq=seq,
                initiator_send_ms=initiator_send_ms,
                initiator_send_mono=initiator_send_mono,
            )
            if sample is None:
                continue

            rtt_ms, offset_ms = sample
            samples.append((rtt_ms, offset_ms, seq))
            await asyncio.sleep(self.sleep_s)

        if not samples:
            raise RuntimeError("relay clock sync failed: no successful samples")

        best = sorted(samples, key=lambda item: item[0])[: min(5, len(samples))]
        return ClockSyncResult(
            offset_ms=_median([item[1] for item in best]),
            rtt_ms=_median([item[0] for item in best]),
            sample_count=len(best),
        )

    def _sample_from_ack(
        self,
        envelope: dict,
        *,
        seq: int,
        initiator_send_ms: float,
        initiator_send_mono: float,
    ) -> tuple[float, float] | None:
        import time

        if envelope.get("seq") is not None and envelope.get("seq") != seq:
            return None

        initiator_recv_mono = time.perf_counter()
        initiator_recv_ms = initiator_send_ms + (
            initiator_recv_mono - initiator_send_mono
        ) * 1000.0

        cloud_recv_ms = parse_iso_ms(envelope.get("cloud_receive_time"))
        cloud_send_ms = parse_iso_ms(envelope.get("cloud_send_time"))
        if cloud_recv_ms is None or cloud_send_ms is None:
            return None

        offset_ms, _ = compute_responder_offset_ms(
            initiator_send_ms=initiator_send_ms,
            initiator_recv_ms=initiator_recv_ms,
            responder_receive_ms=cloud_recv_ms,
            responder_send_ms=cloud_send_ms,
        )
        rtt_ms = (initiator_recv_mono - initiator_send_mono) * 1000.0
        return (rtt_ms, offset_ms)

    async def sync_over_udp(
        self,
        *,
        send_ping,
        wait_ack,
        role: str,
        session_id: str,
    ) -> ClockSyncResult:
        import time

        del role, session_id
        samples: list[tuple[float, float, float]] = []

        for seq in range(self.sample_count):
            initiator_send_wall = datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z")
            initiator_send_mono = time.perf_counter()
            initiator_send_ms = parse_iso_ms(initiator_send_wall)
            if initiator_send_ms is None:
                continue

            await send_ping(seq=seq, sender_send_time=initiator_send_wall)

            sample = await wait_ack(
                seq=seq,
                initiator_send_ms=initiator_send_ms,
                initiator_send_mono=initiator_send_mono,
            )
            if sample is None:
                continue

            rtt_ms, offset_ms = sample
            samples.append((rtt_ms, offset_ms, seq))
            await asyncio.sleep(self.sleep_s)

        if not samples:
            raise RuntimeError("relay clock sync failed: no successful samples")

        best = sorted(samples, key=lambda item: item[0])[: min(5, len(samples))]
        return ClockSyncResult(
            offset_ms=_median([item[1] for item in best]),
            rtt_ms=_median([item[0] for item in best]),
            sample_count=len(best),
        )
