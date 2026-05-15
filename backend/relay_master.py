import asyncio
import sys
from datetime import datetime
from pathlib import Path

from .config import (
    CLOUD_BASE_URL,
    RELAY_RECONNECT_DELAY_S,
    RELAY_SESSION_ID,
    RELAY_TOKEN,
    RELAY_URL,
    TRANSPORT_MODE,
)
from .master_stream import (
    SLAVE_SUBSCRIBE_MESSAGE_TYPE,
    SLAVE_UNSUBSCRIBE_MESSAGE_TYPE,
    handle_slave_control_message,
    register_slave_peer,
    remove_slave_peer,
)
from .state import MASTER_RELAY_CLIENT_KEY, MASTER_RELAY_PUMP_TASK_KEY

RELAY_PEER_KEY = ("relay", 0)


def _ensure_cloud_importable():
    app_root = Path(__file__).resolve().parents[2]
    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))


def _log(message):
    print(f"[TeleProgram] {message}")


def use_relay_transport():
    return TRANSPORT_MODE == "relay"


async def _relay_pump(app, relay_client):
    try:
        async for payload in relay_client.iter_payloads():
            message_type = payload.get("type")
            if message_type == SLAVE_UNSUBSCRIBE_MESSAGE_TYPE:
                remove_slave_peer(app, RELAY_PEER_KEY, reason="unsubscribe")
                continue
            if message_type == SLAVE_SUBSCRIBE_MESSAGE_TYPE:
                handle_slave_control_message(app, RELAY_PEER_KEY, payload)
                continue
    except asyncio.CancelledError:
        raise
    finally:
        remove_slave_peer(app, RELAY_PEER_KEY, reason="relay_closed")


async def start_master_relay(app):
    if not use_relay_transport():
        return

    _ensure_cloud_importable()
    from cloud.relay_client import RelayClient

    relay_client = RelayClient(
        url=RELAY_URL,
        role="master",
        session_id=RELAY_SESSION_ID,
        token=RELAY_TOKEN,
        reconnect_delay_s=RELAY_RECONNECT_DELAY_S,
        label="TeleProgram",
    )
    await relay_client.connect()
    app[MASTER_RELAY_CLIENT_KEY] = relay_client
    app[MASTER_RELAY_PUMP_TASK_KEY] = asyncio.create_task(_relay_pump(app, relay_client))

    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] master relay connected to {RELAY_URL} "
        f"(cloud={CLOUD_BASE_URL}, session={RELAY_SESSION_ID})"
    )


async def close_master_relay(app):
    pump_task = app.get(MASTER_RELAY_PUMP_TASK_KEY)
    if pump_task is not None:
        pump_task.cancel()
        try:
            await pump_task
        except asyncio.CancelledError:
            pass
        app[MASTER_RELAY_PUMP_TASK_KEY] = None

    relay_client = app.get(MASTER_RELAY_CLIENT_KEY)
    if relay_client is not None:
        await relay_client.close()
        app[MASTER_RELAY_CLIENT_KEY] = None

    remove_slave_peer(app, RELAY_PEER_KEY, reason="shutdown")


def send_master_relay_payload(app, payload):
    relay_client = app.get(MASTER_RELAY_CLIENT_KEY)
    if relay_client is None or not relay_client.is_connected:
        return False

    loop = asyncio.get_event_loop()
    loop.create_task(relay_client.send_payload(payload))
    return True
