from aiohttp import web

from .links import LINKS_KEY
from .runtime_settings import init_runtime_settings
from .state import init_app_state
from .wiring.links import build_client_links, install_links, shutdown_links


def create_app(*, base_path=""):
    app = web.Application()
    init_app_state(app)
    init_runtime_settings()

    links = build_client_links()
    app[LINKS_KEY] = links
    links.frontend.register_routes(app, base_path=base_path)

    app.on_startup.append(install_links)
    app.on_shutdown.append(shutdown_links)
    return app
