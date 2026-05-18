from aiohttp import web

from ..links.local.relay import handle_local_relay_websocket, send_local_relay_snapshot


async def local_relay_websocket_handler(request):
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    await handle_local_relay_websocket(request, ws, send_snapshot=send_local_relay_snapshot)
    return ws
