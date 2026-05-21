import asyncio

from ..config import get_relay_url, use_cloud_tcp_transport
from ..services.device_service import ensure_host_region
from ..links import LINKS_KEY, ClientLinks
from ..links.cloud.link import CloudLink
from ..links.frontend.link import FrontendLink
from ..links.local.gripper_udp import close_local_gripper_udp, start_local_gripper_udp
from ..links.local.link import LocalLink
from ..runtime_settings import get_runtime_settings
from ..state import GRIPPER_COMMAND_TRANSPORT_KEY


def build_client_links() -> ClientLinks:
    settings = get_runtime_settings()
    return ClientLinks(
        frontend=FrontendLink(),
        local=LocalLink(),
        cloud=CloudLink(),
        active_outbound=settings.active_outbound_name(),
    )


async def install_links(app):
    links = app.get(LINKS_KEY)
    if links is None:
        links = build_client_links()
        app[LINKS_KEY] = links
    else:
        settings = get_runtime_settings()
        links.active_outbound = settings.active_outbound_name()

    try:
        if use_cloud_tcp_transport() and not (get_relay_url() or "").strip():
            raise RuntimeError(
                "cloud_tcp requires a relay URL: set cloud_host and cloud_tcp_port in "
                "/settings or config/cloud.json."
            )
        if links.active_outbound == "cloud":
            region = await asyncio.to_thread(ensure_host_region)
            if region and region != "unknown":
                print(f"[TeleProgram] host region resolved: {region}")
        await links.outbound.start(app)
    except Exception as exc:
        settings = get_runtime_settings()
        print(
            "[TeleProgram] outbound start failed; frontend remains available. "
            f"transport_mode={settings.transport_mode} error={exc}"
        )

    if get_runtime_settings().local_topology == "same_machine":
        try:
            await start_local_gripper_udp(app)
        except Exception as exc:
            print(
                "[TeleProgram] same_machine gripper udp start failed; "
                f"gripper commands may require cloud peer. error={exc}"
            )


async def shutdown_links(app):
    links = app.get(LINKS_KEY)
    if links is None:
        return

    await links.frontend.shutdown(app)
    await links.outbound.close(app)
    if app.get(GRIPPER_COMMAND_TRANSPORT_KEY) is not None:
        await close_local_gripper_udp(app)
    app[LINKS_KEY] = None
