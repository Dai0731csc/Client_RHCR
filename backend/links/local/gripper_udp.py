import asyncio
import json
from datetime import datetime

from ...config import get_gripper_service_host, get_gripper_service_port
from ...state import GRIPPER_COMMAND_PROTOCOL_KEY, GRIPPER_COMMAND_TRANSPORT_KEY


def _log(message: str) -> None:
    print(f"[TeleProgram] {message}")


class LocalGripperUdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, app):
        self.app = app
        self.closed = asyncio.get_running_loop().create_future()

    def connection_made(self, transport):
        self.app[GRIPPER_COMMAND_TRANSPORT_KEY] = transport
        self.app[GRIPPER_COMMAND_PROTOCOL_KEY] = self
        sockname = transport.get_extra_info("sockname")
        _log(
            f"[{datetime.now().strftime('%H:%M:%S')}] [local] gripper udp ready on "
            f"{sockname[0]}:{sockname[1]}"
        )

    def error_received(self, exc):
        _log(f"[local] gripper udp error: {exc}")

    def connection_lost(self, exc):
        self.app[GRIPPER_COMMAND_TRANSPORT_KEY] = None
        self.app[GRIPPER_COMMAND_PROTOCOL_KEY] = None
        if not self.closed.done():
            self.closed.set_result(None)
        if exc is not None:
            _log(f"[local] gripper udp closed with error: {exc}")


async def start_local_gripper_udp(app) -> None:
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: LocalGripperUdpProtocol(app),
        local_addr=("0.0.0.0", 0),
    )
    app[GRIPPER_COMMAND_TRANSPORT_KEY] = transport
    app[GRIPPER_COMMAND_PROTOCOL_KEY] = protocol


async def close_local_gripper_udp(app) -> None:
    transport = app.get(GRIPPER_COMMAND_TRANSPORT_KEY)
    protocol = app.get(GRIPPER_COMMAND_PROTOCOL_KEY)
    if transport is not None:
        transport.close()
        if protocol is not None and hasattr(protocol, "closed"):
            await protocol.closed
    app[GRIPPER_COMMAND_TRANSPORT_KEY] = None
    app[GRIPPER_COMMAND_PROTOCOL_KEY] = None


def send_gripper_command(app, command_payload: dict) -> bool:
    transport = app.get(GRIPPER_COMMAND_TRANSPORT_KEY)
    if transport is None:
        return False
    transport.sendto(
        json.dumps(command_payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        (get_gripper_service_host(), get_gripper_service_port()),
    )
    return True
