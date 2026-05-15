import asyncio
from datetime import datetime

from ...config import (
    CLOUD_BASE_URL,
    RELAY_RECONNECT_DELAY_S,
    RELAY_SESSION_ID,
    RELAY_TOKEN,
    RELAY_URL,
    use_relay_ws_transport,
)
from ...state import MASTER_CLOUD_PUMP_TASK_KEY, MASTER_CLOUD_TRANSPORT_KEY
from ..pose_protocol import (
    CLOUD_PEER_KEY,
    SLAVE_SUBSCRIBE_MESSAGE_TYPE,
    SLAVE_UNSUBSCRIBE_MESSAGE_TYPE,
    handle_slave_control_message,
    remove_slave_peer,
)
from .ws_client import CloudWsClient


def _log(message: str) -> None:
    print(f"[TeleProgram] {message}")


async def _tcp_inbound_pump(app, cloud_client: CloudWsClient) -> None:
    from .pose import send_master_snapshot

    try:
        async for payload in cloud_client.iter_payloads():
            message_type = payload.get("type")
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
        remove_slave_peer(app, CLOUD_PEER_KEY, reason="cloud_tcp_closed")


async def start_cloud_tcp(app) -> None:
    if not use_relay_ws_transport():
        return

    cloud_client = CloudWsClient(
        url=RELAY_URL,
        role="master",
        session_id=RELAY_SESSION_ID,
        token=RELAY_TOKEN,
        reconnect_delay_s=RELAY_RECONNECT_DELAY_S,
        label="TeleProgram",
    )
    await cloud_client.connect()
    app[MASTER_CLOUD_TRANSPORT_KEY] = cloud_client
    app[MASTER_CLOUD_PUMP_TASK_KEY] = asyncio.create_task(_tcp_inbound_pump(app, cloud_client))

    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] [cloud] tcp connected to {RELAY_URL} "
        f"(base={CLOUD_BASE_URL}, session={RELAY_SESSION_ID})"
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
