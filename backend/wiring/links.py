from ..config import get_relay_url, use_cloud_tcp_transport
from ..links import LINKS_KEY, ClientLinks
from ..links.cloud.link import CloudLink
from ..links.frontend.link import FrontendLink
from ..links.local.link import LocalLink
from ..runtime_settings import get_runtime_settings


def build_client_links() -> ClientLinks:
    settings = get_runtime_settings()
    return ClientLinks(
        frontend=FrontendLink(),
        local=LocalLink(),
        cloud=CloudLink(),
        active_outbound=settings.active_outbound_name(),
    )


async def install_links(app):
    if use_cloud_tcp_transport() and not (get_relay_url() or "").strip():
        raise RuntimeError(
            "cloud_tcp requires a relay URL: set cloud_host and cloud_tcp_port in "
            "/settings or config/cloud.json."
        )

    links = app.get(LINKS_KEY)
    if links is None:
        links = build_client_links()
        app[LINKS_KEY] = links
    else:
        settings = get_runtime_settings()
        links.active_outbound = settings.active_outbound_name()

    await links.outbound.start(app)


async def shutdown_links(app):
    links = app.get(LINKS_KEY)
    if links is None:
        return

    await links.frontend.shutdown(app)
    await links.outbound.close(app)
    app[LINKS_KEY] = None
