from ..config import RELAY_URL, use_cloud_profile, use_relay_ws_transport
from ..links import LINKS_KEY, ClientLinks
from ..links.cloud.link import CloudLink
from ..links.frontend.link import FrontendLink
from ..links.local.link import LocalLink


def build_client_links() -> ClientLinks:
    active = "cloud" if use_cloud_profile() else "local"
    return ClientLinks(
        frontend=FrontendLink(),
        local=LocalLink(),
        cloud=CloudLink(),
        active_outbound=active,
    )


async def install_links(app):
    if use_relay_ws_transport() and not (RELAY_URL or "").strip():
        raise RuntimeError(
            "经 WebSocket relay 出站（cloud_tcp / local_tcp）需要可用的 relay 地址："
            "请在 config/cloud.json 填写 cloud_host；local_tcp 可留空主机（默认 127.0.0.1），"
            "并设置 cloud_tcp_port。"
        )

    links = app.get(LINKS_KEY)
    if links is None:
        links = build_client_links()
        app[LINKS_KEY] = links

    await links.outbound.start(app)


async def shutdown_links(app):
    links = app.get(LINKS_KEY)
    if links is None:
        return

    await links.frontend.shutdown(app)
    await links.outbound.close(app)
    app[LINKS_KEY] = None
