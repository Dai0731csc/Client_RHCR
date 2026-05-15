"""Cloud link: pose stream + gripper via cloud relay (TCP WebSocket or UDP)."""

from ...config import use_cloud_udp_transport, use_relay_ws_transport
from ...state import MASTER_CLOUD_TRANSPORT_KEY
from .pose import broadcast_pose
from .tcp import close_cloud_tcp, start_cloud_tcp
from .udp import close_cloud_udp, start_cloud_udp


class CloudLink:
    name = "cloud"

    async def start(self, app) -> None:
        if use_relay_ws_transport():
            await start_cloud_tcp(app)
            return
        if use_cloud_udp_transport():
            await start_cloud_udp(app)

    async def close(self, app) -> None:
        if use_relay_ws_transport():
            await close_cloud_tcp(app)
            return
        if use_cloud_udp_transport():
            await close_cloud_udp(app)

    def broadcast_pose(self, app, payload: dict, *, add_server_send_time: bool = False) -> None:
        broadcast_pose(app, payload, add_server_send_time=add_server_send_time)

    def send_gripper(self, app, command_payload: dict) -> bool:
        return broadcast_pose(app, command_payload, add_server_send_time=False)

    @property
    def is_connected(self) -> bool:
        client = app.get(MASTER_CLOUD_TRANSPORT_KEY)
        return client is not None and client.is_connected
