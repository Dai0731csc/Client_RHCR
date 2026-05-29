from aiohttp import web

from ..services.time_sync_service import get_full_chain_time_sync_coordinator


async def full_chain_time_sync_handler(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        return web.json_response(
            {"success": False, "failed_hop": "browser_master", "message": "invalid JSON"},
            status=400,
        )

    browser_master = payload.get("browser_master")
    if not isinstance(browser_master, dict):
        return web.json_response(
            {
                "success": False,
                "failed_hop": "browser_master",
                "message": "browser_master payload is required",
            },
            status=400,
        )

    coordinator = get_full_chain_time_sync_coordinator(request.app)
    result = await coordinator.run(browser_master=browser_master)
    return web.json_response({"success": bool(result.get("ok")), **result})
