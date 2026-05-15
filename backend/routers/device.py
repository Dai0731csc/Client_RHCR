from aiohttp import web

from ..services.device_service import device_store


async def device_profile_handler(request):
    profile = device_store.update_from_request(request)
    return web.json_response(
        {
            "success": True,
            "device": profile,
        }
    )


async def device_profile_by_ip_handler(request):
    profile = device_store.get_device(ip=request.match_info.get("ip", ""))
    return web.json_response(
        {
            "success": True,
            "device": profile,
        }
    )
