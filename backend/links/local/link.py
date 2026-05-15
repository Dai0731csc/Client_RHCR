"""Local link: UDP pose stream + gripper to on-LAN control server."""

from .gripper_udp import close_local_gripper_udp, send_gripper_command, start_local_gripper_udp
from .master_udp import close_local_master_udp, start_local_master_udp
from .pose import broadcast_pose


class LocalLink:
    name = "local"

    def __init__(self):
        self._started = False

    async def start(self, app) -> None:
        await start_local_master_udp(app)
        await start_local_gripper_udp(app)
        self._started = True

    async def close(self, app) -> None:
        await close_local_gripper_udp(app)
        await close_local_master_udp(app)
        self._started = False

    def broadcast_pose(self, app, payload: dict, *, add_server_send_time: bool = False) -> None:
        broadcast_pose(app, payload, add_server_send_time=add_server_send_time)

    def send_gripper(self, app, command_payload: dict) -> bool:
        return send_gripper_command(app, command_payload)

    @property
    def is_connected(self) -> bool:
        return self._started
