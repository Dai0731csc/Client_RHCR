from aiohttp import web

from ..services.device_service import device_store


def normalize_base_path(base_path):
    base_path = (base_path or "").strip()
    if not base_path or base_path == "/":
        return ""
    return "/" + base_path.strip("/")


def app_path(base_path, suffix):
    normalized = normalize_base_path(base_path)
    if not suffix.startswith("/"):
        suffix = f"/{suffix}"
    return f"{normalized}{suffix}" if normalized else suffix


def build_template_context(*, base_path="", hub_path="/"):
    normalized_base_path = normalize_base_path(base_path)
    return {
        "base_path": normalized_base_path,
        "hub_path": hub_path or "/",
        "static_url_prefix": app_path(normalized_base_path, "/static"),
    }


async def camera_page(request):
    device_store.update_from_request(request)
    env = request.app["jinja"]
    template = env.get_template("camera.html")
    html = template.render(**request.app["template_context"])
    return web.Response(text=html, content_type="text/html")
