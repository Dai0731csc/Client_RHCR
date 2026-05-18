import asyncio
from datetime import datetime

from ...config import (
    get_relay_reconnect_delay_s,
    get_relay_session_id,
    get_relay_token,
    get_relay_url,
    get_runtime_tls_ca_file,
    get_runtime_tls_verify,
    get_transport_mode,
    use_cloud_tcp_transport,
)
from ...runtime_settings import get_runtime_settings
from ...state import MASTER_CLOUD_PUMP_TASK_KEY, MASTER_CLOUD_TRANSPORT_KEY
from ..pose_protocol import (
    CLOUD_PEER_KEY,
    SLAVE_SUBSCRIBE_MESSAGE_TYPE,
    SLAVE_UNSUBSCRIBE_MESSAGE_TYPE,
    handle_slave_control_message,
    remove_slave_peer,
)
from .protocol import STREAM_CLOSED_INTERNAL_TYPE
from .ws_client import CloudWsClient


def _log(message: str) -> None:
    print(f"[TeleProgram] {message}")


async def _tcp_inbound_pump(app, cloud_client: CloudWsClient) -> None:
    from .pose import send_master_snapshot

    try:
        async for payload in cloud_client.iter_payloads():
            message_type = payload.get("type")
            if message_type == STREAM_CLOSED_INTERNAL_TYPE:
                remove_slave_peer(app, CLOUD_PEER_KEY, reason="cloud_tcp_closed")
                continue
            if message_type == SLAVE_UNSUBSCRIBE_MESSAGE_TYPE:
                remove_slave_peer(app, CLOUD_PEER_KEY, reason="unsubscribe")
                continue
            if message_type == SLAVE_SUBSCRIBE_MESSAGE_TYPE:
                handle_slave_control_message(
                    app,
                    CLOUD_PEER_KEY,
                    payload,
                    send_snapshot=send_master_snapshot,
                )
                continue
    except asyncio.CancelledError:
        raise
    finally:
        remove_slave_peer(app, CLOUD_PEER_KEY, reason="cloud_tcp_pump_stopped")


async def start_cloud_tcp(app) -> None:
    if not use_cloud_tcp_transport():
        return

    relay_url = get_relay_url()
    settings = get_runtime_settings()
    cloud_base_url = ""
    if settings.cloud_host and settings.use_cloud_tcp_transport():
        http_scheme = "https" if settings.cloud_use_tls else "http"
        cloud_base_url = f"{http_scheme}://{settings.cloud_host}:{settings.cloud_tcp_port}"

    cloud_client = CloudWsClient(
        url=relay_url,
        role="master",
        session_id=get_relay_session_id(),
        token=get_relay_token(),
        reconnect_delay_s=get_relay_reconnect_delay_s(),
        label="TeleProgram",
        metadata={"transport_mode": get_transport_mode()},
        tls_verify=get_runtime_tls_verify(),
        tls_ca_file=get_runtime_tls_ca_file(),
    )
    await cloud_client.connect()
    app[MASTER_CLOUD_TRANSPORT_KEY] = cloud_client
    app[MASTER_CLOUD_PUMP_TASK_KEY] = asyncio.create_task(_tcp_inbound_pump(app, cloud_client))

    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] [cloud] tcp connected to {relay_url} "
        f"(base={cloud_base_url}, session={get_relay_session_id()})"
    )


async def close_cloud_tcp(app) -> None:
    pump_task = app.get(MASTER_CLOUD_PUMP_TASK_KEY)
    if pump_task is not None:
        pump_task.cancel()
        try:
            await pump_task
        except asyncio.CancelledError:
            pass
        app[MASTER_CLOUD_PUMP_TASK_KEY] = None

    cloud_client = app.get(MASTER_CLOUD_TRANSPORT_KEY)
    if cloud_client is not None:
        await cloud_client.close()
        app[MASTER_CLOUD_TRANSPORT_KEY] = None

    remove_slave_peer(app, CLOUD_PEER_KEY, reason="shutdown")
