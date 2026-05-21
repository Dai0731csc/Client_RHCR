"""Cloud relay clock skew snapshot for attaching to stream payloads."""

from __future__ import annotations

from typing import Any

SKEW_CLOUD_VS_MASTER_MS = "skew_cloud_vs_master_ms"
CLOCK_SYNC_RTT_CLOUD_MS = "clock_sync_rtt_cloud_ms"


def cloud_clock_skew_snapshot(app: Any) -> dict[str, float]:
    """Skew measured on TeleProgram (master) vs cloud at connect."""
    from ...state import MASTER_CLOUD_TRANSPORT_KEY

    client = app.get(MASTER_CLOUD_TRANSPORT_KEY)
    if client is None:
        return {}
    out: dict[str, float] = {}
    skew = getattr(client, "skew_cloud_vs_master_ms", None)
    if skew is not None:
        out[SKEW_CLOUD_VS_MASTER_MS] = float(skew)
    rtt = getattr(client, "clock_sync_rtt_cloud_ms", None)
    if rtt is not None:
        out[CLOCK_SYNC_RTT_CLOUD_MS] = float(rtt)
    return out
