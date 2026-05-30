from __future__ import annotations

import asyncio
from uuid import uuid4

from ..links.cloud.protocol import (
    RELAY_ACTION_FULL_CHAIN_TIME_SYNC_REQUEST,
    RELAY_ACTION_FULL_CHAIN_TIME_SYNC_RESULT,
)
from ..runtime_settings import get_runtime_settings
from ..state import (
    FULL_CHAIN_TIME_SYNC_CAPTURE_SNAPSHOT_KEY,
    FULL_CHAIN_TIME_SYNC_COORDINATOR_KEY,
    MASTER_CLOUD_TRANSPORT_KEY,
    MASTER_LOCAL_RELAY_CONTROL_KEY,
    MASTER_LOCAL_UDP_CONTROL_KEY,
)
from ..utils import current_utc_iso_timestamp


def set_pending_capture_time_sync_snapshot(app, snapshot: dict | None) -> None:
    app[FULL_CHAIN_TIME_SYNC_CAPTURE_SNAPSHOT_KEY] = dict(snapshot) if snapshot else None


def consume_pending_capture_time_sync_snapshot(app) -> dict | None:
    snapshot = app.get(FULL_CHAIN_TIME_SYNC_CAPTURE_SNAPSHOT_KEY)
    app[FULL_CHAIN_TIME_SYNC_CAPTURE_SNAPSHOT_KEY] = None
    return dict(snapshot) if isinstance(snapshot, dict) else None


class FullChainTimeSyncCoordinator:
    def __init__(self, app, *, cloud_client=None, local_transport=None, timeout_s: float = 10.0):
        self.app = app
        self._cloud_client_override = cloud_client
        self._local_transport_override = local_transport
        self.timeout_s = timeout_s
        self._pending: dict[str, asyncio.Future] = {}
        self._listener_client_ids: set[int] = set()

    async def run(self, *, browser_master: dict) -> dict:
        request_id = f"fts-{uuid4().hex}"
        print(
            "[relay/time-sync] browser->master synced "
            f"request_id={request_id} "
            f"offset_ms={browser_master.get('offset_ms')} "
            f"rtt_ms={browser_master.get('rtt_ms')} "
            f"samples={browser_master.get('sample_count')}"
        )
        snapshot = {
            "request_id": request_id,
            "browser_master": dict(browser_master),
            "master_cloud": None,
            "cloud_control": None,
            "master_control": None,
            "completed_at": None,
            "status": "partial_success",
            "skipped_hops": [],
            "failed_hops": [],
        }
        mode = self._transport_mode()
        if mode in {"cloud_tcp", "cloud_udp"}:
            await self._run_cloud_chain(
                request_id=request_id,
                browser_master=browser_master,
                snapshot=snapshot,
            )
        elif mode in {"local_tcp", "local_udp"}:
            await self._run_local_chain(
                request_id=request_id,
                browser_master=browser_master,
                snapshot=snapshot,
            )
        else:
            snapshot["skipped_hops"].append("downstream_transport")

        snapshot["completed_at"] = current_utc_iso_timestamp()
        snapshot["status"] = "success" if not snapshot["skipped_hops"] and not snapshot["failed_hops"] else "partial_success"
        set_pending_capture_time_sync_snapshot(self.app, snapshot)
        return {
            "ok": True,
            "failed_hop": snapshot["failed_hops"][0]["hop"] if snapshot["failed_hops"] else "none",
            "message": snapshot["failed_hops"][0]["message"] if snapshot["failed_hops"] else "",
            **snapshot,
        }

    def handle_control_result(self, envelope: dict) -> bool:
        action = envelope.get("relay_action") or envelope.get("type")
        if action != RELAY_ACTION_FULL_CHAIN_TIME_SYNC_RESULT:
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

    def _resolve_local_transport(self):
        if self._local_transport_override is not None:
            return self._local_transport_override
        mode = self._transport_mode()
        if mode == "local_tcp":
            return self.app.get(MASTER_LOCAL_RELAY_CONTROL_KEY)
        if mode == "local_udp":
            return self.app.get(MASTER_LOCAL_UDP_CONTROL_KEY)
        return None

    def _ensure_control_listener(self, transport) -> None:
        client_id = id(transport)
        if client_id in self._listener_client_ids:
            return
        if hasattr(transport, "on_control_message"):
            transport.on_control_message(self.handle_control_result)
            self._listener_client_ids.add(client_id)

    def _transport_mode(self) -> str:
        return str(get_runtime_settings().transport_mode or "").strip()

    async def _run_cloud_chain(self, *, request_id: str, browser_master: dict, snapshot: dict) -> None:
        cloud_client = self._resolve_cloud_client()
        if cloud_client is None or not getattr(cloud_client, "is_connected", False):
            snapshot["skipped_hops"].extend(["master_cloud", "cloud_control"])
            return
        mode = self._transport_mode()
        if mode != "cloud_udp" and not getattr(cloud_client, "peer_is_connected", False):
            snapshot["skipped_hops"].extend(["master_cloud", "cloud_control"])
            return

        self._ensure_control_listener(cloud_client)
        master_cloud = None
        try:
            master_cloud = await cloud_client.resync_master_cloud(request_id=request_id)
            snapshot["master_cloud"] = dict(master_cloud)
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
            snapshot["failed_hops"].append({"hop": "master_cloud", "message": str(error)})
            snapshot["skipped_hops"].append("cloud_control")
            return

        control_result = await self._request_control_result(
            cloud_client,
            request_id=request_id,
            failed_hop="cloud_control",
            browser_master=browser_master,
            master_cloud=master_cloud,
            requested_at=current_utc_iso_timestamp(),
        )
        if not control_result.get("ok"):
            snapshot["failed_hops"].append(
                {
                    "hop": str(control_result.get("failed_hop") or "cloud_control"),
                    "message": str(control_result.get("message") or "control relay time sync failed"),
                }
            )
            return
        snapshot["cloud_control"] = dict(control_result.get("cloud_control") or {})

    async def _run_local_chain(self, *, request_id: str, browser_master: dict, snapshot: dict) -> None:
        local_transport = self._resolve_local_transport()
        if local_transport is None or not getattr(local_transport, "is_connected", False):
            snapshot["skipped_hops"].append("master_control")
            return
        if not getattr(local_transport, "peer_is_connected", False):
            snapshot["skipped_hops"].append("master_control")
            return

        self._ensure_control_listener(local_transport)
        control_result = await self._request_control_result(
            local_transport,
            request_id=request_id,
            failed_hop="master_control",
            browser_master=browser_master,
            requested_at=current_utc_iso_timestamp(),
        )
        if not control_result.get("ok"):
            snapshot["failed_hops"].append(
                {
                    "hop": str(control_result.get("failed_hop") or "master_control"),
                    "message": str(control_result.get("message") or "local relay time sync failed"),
                }
            )
            return
        master_control = control_result.get("master_control")
        if not isinstance(master_control, dict):
            master_control = control_result.get("cloud_control")
        snapshot["master_control"] = dict(master_control or {})

    async def _request_control_result(self, transport, *, request_id: str, failed_hop: str, **fields) -> dict:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[request_id] = future
        try:
            await transport.send_control_message(
                RELAY_ACTION_FULL_CHAIN_TIME_SYNC_REQUEST,
                request_id=request_id,
                **fields,
            )
            return await asyncio.wait_for(future, timeout=self.timeout_s)
        except asyncio.TimeoutError:
            return {
                "ok": False,
                "failed_hop": failed_hop,
                "message": "control relay time sync timed out",
            }
        except Exception as error:
            return {
                "ok": False,
                "failed_hop": failed_hop,
                "message": str(error),
            }
        finally:
            self._pending.pop(request_id, None)


def get_full_chain_time_sync_coordinator(app) -> FullChainTimeSyncCoordinator:
    coordinator = app.get(FULL_CHAIN_TIME_SYNC_COORDINATOR_KEY)
    if coordinator is None:
        coordinator = FullChainTimeSyncCoordinator(app)
        app[FULL_CHAIN_TIME_SYNC_COORDINATOR_KEY] = coordinator
    return coordinator
