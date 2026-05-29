from __future__ import annotations

import asyncio
from uuid import uuid4

from ..links.cloud.protocol import (
    RELAY_ACTION_FULL_CHAIN_TIME_SYNC_REQUEST,
    RELAY_ACTION_FULL_CHAIN_TIME_SYNC_RESULT,
)
from ..state import (
    FULL_CHAIN_TIME_SYNC_CAPTURE_SNAPSHOT_KEY,
    FULL_CHAIN_TIME_SYNC_COORDINATOR_KEY,
    MASTER_CLOUD_TRANSPORT_KEY,
)
from ..utils import current_utc_iso_timestamp


def set_pending_capture_time_sync_snapshot(app, snapshot: dict | None) -> None:
    app[FULL_CHAIN_TIME_SYNC_CAPTURE_SNAPSHOT_KEY] = dict(snapshot) if snapshot else None


def consume_pending_capture_time_sync_snapshot(app) -> dict | None:
    snapshot = app.get(FULL_CHAIN_TIME_SYNC_CAPTURE_SNAPSHOT_KEY)
    app[FULL_CHAIN_TIME_SYNC_CAPTURE_SNAPSHOT_KEY] = None
    return dict(snapshot) if isinstance(snapshot, dict) else None


class FullChainTimeSyncCoordinator:
    def __init__(self, app, *, cloud_client=None, timeout_s: float = 10.0):
        self.app = app
        self._cloud_client_override = cloud_client
        self.timeout_s = timeout_s
        self._pending: dict[str, asyncio.Future] = {}
        self._listener_client_id: int | None = None

    async def run(self, *, browser_master: dict) -> dict:
        cloud_client = self._resolve_cloud_client()
        if cloud_client is None:
            return self._fail("master_cloud", "cloud relay transport is unavailable")
        if not getattr(cloud_client, "is_connected", False):
            return self._fail("master_cloud", "cloud relay transport is not connected")
        if not getattr(cloud_client, "peer_is_connected", False):
            return self._fail("master_cloud", "cloud relay peer is not connected")

        self._ensure_control_listener(cloud_client)

        request_id = f"fts-{uuid4().hex}"
        print(
            "[relay/time-sync] browser->master synced "
            f"request_id={request_id} "
            f"offset_ms={browser_master.get('offset_ms')} "
            f"rtt_ms={browser_master.get('rtt_ms')} "
            f"samples={browser_master.get('sample_count')}"
        )
        try:
            master_cloud = await cloud_client.resync_master_cloud(request_id=request_id)
            print(
                "[relay/time-sync] master->cloud synced "
                f"request_id={request_id} "
                f"offset_ms={master_cloud.get('offset_ms')} "
                f"rtt_ms={master_cloud.get('rtt_ms')} "
                f"samples={master_cloud.get('sample_count')}"
            )
        except Exception as error:
            print(
                "[relay/time-sync] master->cloud sync failed "
                f"request_id={request_id} error={error}"
            )
            return self._fail("master_cloud", str(error))

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[request_id] = future
        try:
            await cloud_client.send_control_message(
                RELAY_ACTION_FULL_CHAIN_TIME_SYNC_REQUEST,
                request_id=request_id,
                browser_master=browser_master,
                master_cloud=master_cloud,
                requested_at=current_utc_iso_timestamp(),
            )
            control_result = await asyncio.wait_for(future, timeout=self.timeout_s)
        except asyncio.TimeoutError:
            return self._fail("cloud_control", "control relay time sync timed out")
        except Exception as error:
            return self._fail("cloud_control", str(error))
        finally:
            self._pending.pop(request_id, None)

        if not control_result.get("ok"):
            return self._fail(
                str(control_result.get("failed_hop") or "cloud_control"),
                str(control_result.get("message") or "control relay time sync failed"),
            )

        completed_at = current_utc_iso_timestamp()
        snapshot = {
            "request_id": request_id,
            "completed_at": completed_at,
            "status": "success",
            "browser_master": dict(browser_master),
            "master_cloud": dict(master_cloud),
            "cloud_control": dict(control_result.get("cloud_control") or {}),
        }
        set_pending_capture_time_sync_snapshot(self.app, snapshot)
        return {
            "ok": True,
            "failed_hop": "none",
            "message": "",
            **snapshot,
        }

    def handle_control_result(self, envelope: dict) -> bool:
        if envelope.get("relay_action") != RELAY_ACTION_FULL_CHAIN_TIME_SYNC_RESULT:
            return False
        request_id = str(envelope.get("request_id") or "").strip()
        if not request_id:
            return False
        future = self._pending.get(request_id)
        if future is None or future.done():
            return False
        future.set_result(dict(envelope))
        return True

    def _resolve_cloud_client(self):
        if self._cloud_client_override is not None:
            return self._cloud_client_override
        return self.app.get(MASTER_CLOUD_TRANSPORT_KEY)

    def _ensure_control_listener(self, cloud_client) -> None:
        client_id = id(cloud_client)
        if self._listener_client_id == client_id:
            return
        if hasattr(cloud_client, "on_control_message"):
            cloud_client.on_control_message(self.handle_control_result)
        self._listener_client_id = client_id

    def _fail(self, failed_hop: str, message: str) -> dict:
        set_pending_capture_time_sync_snapshot(self.app, None)
        return {
            "ok": False,
            "failed_hop": failed_hop,
            "message": message,
        }


def get_full_chain_time_sync_coordinator(app) -> FullChainTimeSyncCoordinator:
    coordinator = app.get(FULL_CHAIN_TIME_SYNC_COORDINATOR_KEY)
    if coordinator is None:
        coordinator = FullChainTimeSyncCoordinator(app)
        app[FULL_CHAIN_TIME_SYNC_COORDINATOR_KEY] = coordinator
    return coordinator
