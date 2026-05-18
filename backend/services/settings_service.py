"""Runtime settings: apply immediately and persist ``config/cloud.json`` in the background."""

from __future__ import annotations

import json
from typing import Any, Mapping

from aiohttp import web

from ..links import LINKS_KEY
from ..runtime_settings import get_runtime_settings
from ..wiring.reconfigure import reconfigure_outbound


def get_settings_snapshot(*, app) -> dict[str, Any]:
    settings = get_runtime_settings()
    links = app.get(LINKS_KEY)
    outbound_connected = False
    if links is not None:
        outbound_connected = bool(links.outbound.is_connected)

    snapshot = settings.to_snapshot()
    snapshot["outbound_connected"] = outbound_connected
    return snapshot


async def apply_settings_update(app, payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise web.HTTPBadRequest(
            text=json.dumps({"success": False, "error": "invalid_payload"}),
            content_type="application/json",
        )

    settings = get_runtime_settings()

    try:
        settings.apply_patch(dict(payload))
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

    settings.persist()

    try:
        await reconfigure_outbound(app)
    except RuntimeError as error:
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
