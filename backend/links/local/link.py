"""Local link: UDP pose stream + gripper to on-LAN control server."""

from ...runtime_settings import get_runtime_settings
from ...config import use_local_tcp_transport
from .gripper_udp import close_local_gripper_udp, send_gripper_command, start_local_gripper_udp
from .master_udp import close_local_master_udp, start_local_master_udp
from .pose import broadcast_pose as broadcast_local_udp_pose
from .relay import (
    broadcast_local_relay_payload,
    close_local_relay,
    send_local_relay_gripper_command,
    start_local_relay,
)


class LocalLink:
    name = "local"

    def __init__(self):
        self._started = False
        self._started_mode: str | None = None

    async def start(self, app) -> None:
        mode = get_runtime_settings().transport_mode
        if use_local_tcp_transport():
            await start_local_relay(app)
        else:
            await start_local_master_udp(app)
            await start_local_gripper_udp(app)
        self._started = True
        self._started_mode = mode

    async def close(self, app) -> None:
        mode = self._started_mode
        if mode == "local_tcp":
            await close_local_relay(app)
        elif mode == "local_udp":
            await close_local_gripper_udp(app)
            await close_local_master_udp(app)
        else:
            await close_local_relay(app)
            await close_local_gripper_udp(app)
            await close_local_master_udp(app)
        self._started = False
        self._started_mode = None

    def broadcast_pose(self, app, payload: dict, *, add_server_send_time: bool = False) -> None:
        if use_local_tcp_transport():
            broadcast_local_relay_payload(
                app,
                payload,
                add_server_send_time=add_server_send_time,
            )
            return
        broadcast_local_udp_pose(app, payload, add_server_send_time=add_server_send_time)

    def send_gripper(self, app, command_payload: dict) -> bool:
        if use_local_tcp_transport():
            return send_local_relay_gripper_command(app, command_payload)
        return send_gripper_command(app, command_payload)

    @property
    def is_connected(self) -> bool:
        return self._started
