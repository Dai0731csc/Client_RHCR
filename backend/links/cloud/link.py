"""Cloud link: pose stream + gripper via cloud relay (TCP WebSocket or UDP)."""

from ...config import use_cloud_tcp_transport, use_cloud_udp_transport
from ...state import MASTER_CLOUD_TRANSPORT_KEY, MASTER_SLAVE_PEERS_KEY
from ..pose_protocol import CLOUD_PEER_KEY
from .pose import broadcast_pose
from .tcp import close_cloud_tcp, start_cloud_tcp
from .udp import close_cloud_udp, start_cloud_udp


class CloudLink:
    name = "cloud"

    def __init__(self):
        self._app = None
        self._started_mode: str | None = None

    async def start(self, app) -> None:
        self._app = app
        if use_cloud_tcp_transport():
            await start_cloud_tcp(app)
            self._started_mode = "cloud_tcp"
            return
        if use_cloud_udp_transport():
            await start_cloud_udp(app)
            self._started_mode = "cloud_udp"

    async def close(self, app) -> None:
        try:
            if self._started_mode == "cloud_tcp":
                await close_cloud_tcp(app)
            elif self._started_mode == "cloud_udp":
                await close_cloud_udp(app)
            else:
                await close_cloud_tcp(app)
                await close_cloud_udp(app)
        finally:
            self._started_mode = None
            self._app = None

    def broadcast_pose(self, app, payload: dict, *, add_master_send_time: bool = False) -> None:
        if self._started_mode is None:
            return
        broadcast_pose(
            app,
            payload,
            started_mode=self._started_mode,
            add_master_send_time=add_master_send_time,
        )

    def send_gripper(self, app, command_payload: dict) -> bool:
        if self._started_mode is None:
            return False
        return broadcast_pose(
            app,
            command_payload,
            started_mode=self._started_mode,
            add_master_send_time=False,
        )

    @property
    def is_connected(self) -> bool:
        if self._app is None:
            return False
        client = self._app.get(MASTER_CLOUD_TRANSPORT_KEY)
        return client is not None and client.is_connected

    def is_ready(self, app) -> bool:
        client = app.get(MASTER_CLOUD_TRANSPORT_KEY)
        if client is None or not client.is_connected:
            return False
        if self._started_mode == "cloud_tcp":
            return bool(getattr(client, "peer_is_connected", False))
        if self._started_mode == "cloud_udp":
            return CLOUD_PEER_KEY in (app.get(MASTER_SLAVE_PEERS_KEY) or {})
        return False
