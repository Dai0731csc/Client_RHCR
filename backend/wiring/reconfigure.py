"""Hot-reload outbound transport without importing the routers stack at module load."""

from __future__ import annotations

from ..config import get_relay_url, use_cloud_tcp_transport
from ..links import LINKS_KEY
from ..runtime_settings import get_runtime_settings


async def reconfigure_outbound(app) -> None:
    """Apply runtime settings: tear down and restart the active outbound link."""
    from .links import build_client_links

    links = app.get(LINKS_KEY)
    if links is None:
        links = build_client_links()
        app[LINKS_KEY] = links

    await links.outbound.close(app)

    settings = get_runtime_settings()
    links.active_outbound = settings.active_outbound_name()

    if use_cloud_tcp_transport() and not (get_relay_url() or "").strip():
        raise RuntimeError(
            "cloud_tcp requires cloud_host; set Cloud Host in /settings and try again."
        )

    await links.outbound.start(app)
