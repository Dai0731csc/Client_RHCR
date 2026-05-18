import json

from aiohttp import web

from ..services.settings_service import apply_settings_update, get_settings_snapshot


async def settings_get_handler(request: web.Request) -> web.Response:
    return web.json_response(get_settings_snapshot(app=request.app))


async def settings_update_handler(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise web.HTTPBadRequest(
            text=json.dumps({"success": False, "error": "invalid_json"}),
            content_type="application/json",
        )

    result = await apply_settings_update(request.app, payload)
    return web.json_response(result)
