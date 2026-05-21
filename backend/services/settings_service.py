"""Runtime settings: apply immediately and persist ``config/cloud.json`` in the background."""

from __future__ import annotations

import json
from typing import Any, Mapping

from aiohttp import web

from ..links import LINKS_KEY
from ..runtime_settings import ClientRuntimeSettings, get_runtime_settings, set_runtime_settings
from ..wiring.reconfigure import reconfigure_outbound


def get_settings_snapshot(*, app) -> dict[str, Any]:
    settings = get_runtime_settings()
    links = app.get(LINKS_KEY)
    outbound_connected = False
    outbound_ready = False
    if links is not None:
        outbound_connected = bool(links.outbound.is_connected)
        outbound_ready = bool(links.outbound.is_ready(app))

    snapshot = settings.to_snapshot()
    snapshot["outbound_connected"] = outbound_connected
    snapshot["outbound_ready"] = outbound_ready
    return snapshot


async def apply_settings_update(app, payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise web.HTTPBadRequest(
            text=json.dumps({"success": False, "error": "invalid_payload"}),
            content_type="application/json",
        )

    settings = get_runtime_settings()
    candidate = ClientRuntimeSettings(settings.data)

    try:
        candidate.apply_patch(dict(payload))
        candidate.to_snapshot()
    except ValueError as error:
        raise web.HTTPBadRequest(
            text=json.dumps(
                {
                    "success": False,
                    "error": "invalid_settings",
                    "message": str(error),
                },
                ensure_ascii=False,
            ),
            content_type="application/json",
        ) from error

    set_runtime_settings(candidate)
    try:
        await reconfigure_outbound(app)
        candidate.persist()
    except Exception as error:
        set_runtime_settings(settings)
        try:
            await reconfigure_outbound(app)
        except Exception as rollback_error:
            raise web.HTTPBadRequest(
                text=json.dumps(
                    {
                        "success": False,
                        "error": "reconfigure_failed",
                        "message": f"{error} (rollback failed: {rollback_error})",
                    },
                    ensure_ascii=False,
                ),
                content_type="application/json",
            ) from error
        raise web.HTTPBadRequest(
            text=json.dumps(
                {
                    "success": False,
                    "error": "reconfigure_failed",
                    "message": str(error),
                },
                ensure_ascii=False,
            ),
            content_type="application/json",
        ) from error

    snapshot = get_settings_snapshot(app=app)
    return {
        "success": True,
        "settings": snapshot,
        "message": f"Switched to {snapshot['transport_mode']} (outbound reconnected).",
    }
