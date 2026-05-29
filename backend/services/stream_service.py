from datetime import datetime
from typing import Any, Mapping, cast

from scipy.spatial.transform import Rotation as R

from ..models import AprilTagDetectionsPayload, DetectionStatePayload, InitialCalibrationPayload
from ..state import (
    MASTER_LATEST_APRILTAG_PAYLOAD_KEY,
    MASTER_LATEST_DETECTION_STATE_KEY,
    MASTER_LATEST_INITIAL_CALIBRATION_KEY,
)
from ..links import get_links
from ..links.cloud.clock_skew import cloud_clock_skew_snapshot
from .time_sync_service import consume_pending_capture_time_sync_snapshot
from ..utils import with_master_receive_time


def _log(message):
    print(f"[TeleProgram] {message}")


def _broadcast(app, payload, *, add_master_send_time=False):
    get_links(app).outbound.broadcast_pose(
        app,
        payload,
        add_master_send_time=add_master_send_time,
    )


def get_detection_tag_id(detection: Mapping[str, Any] | None):
    if not isinstance(detection, dict):
        return None

    detection_tag_id = detection.get("tag_id")
    if detection_tag_id is not None:
        return detection_tag_id
    return detection.get("id")


def format_numeric_vector(values):
    if values is None:
        return "n/a"
    values = list(values)
    if len(values) == 0:
        return "n/a"
    return "[" + ", ".join(f"{float(value):.2f}" for value in values) + "]"


def ingest_initial_calibration_payload(
    app,
    payload: InitialCalibrationPayload,
    *,
    source="websocket",
) -> InitialCalibrationPayload:
    payload = cast(InitialCalibrationPayload, with_master_receive_time(payload))
    app[MASTER_LATEST_INITIAL_CALIBRATION_KEY] = payload
    _broadcast(app, payload, add_master_send_time=True)
    mean_pose = payload.get("mean_pose", {})
    mean_t = mean_pose.get("t")
    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] calibration payload "
        f"({source}): tag_id={payload.get('tag_id')} "
        f"sample_count={payload.get('sample_count')} mean_t={mean_t}"
    )
    return payload


async def ingest_apriltag_payload(app, payload: dict[str, Any], *, source="websocket"):
    payload = with_master_receive_time(payload)
    message_type = payload.get("type")

    if message_type == "detection_state":
        time_sync_full_chain = (
            consume_pending_capture_time_sync_snapshot(app)
            if bool(payload.get("active", False))
            else None
        )
        detection_state_payload = cast(
            DetectionStatePayload,
            {
                **payload,
                **cloud_clock_skew_snapshot(app),
                "time_sync_full_chain": time_sync_full_chain,
            },
        )
        app[MASTER_LATEST_DETECTION_STATE_KEY] = detection_state_payload
        _broadcast(app, detection_state_payload, add_master_send_time=True)
        _log(
            f"[{datetime.now().strftime('%H:%M:%S')}] detection state "
            f"({source}): active={bool(detection_state_payload.get('active', False))} "
            f"fps={detection_state_payload.get('nominal_frame_rate')} "
            f"frame_size={detection_state_payload.get('frame_size')}"
        )
        return detection_state_payload

    if message_type != "apriltag_detections":
        return payload

    latest_detection_state = app[MASTER_LATEST_DETECTION_STATE_KEY] or {}
    master_payload = cast(AprilTagDetectionsPayload, {
        **payload,
        "nominal_frame_rate": payload.get(
            "nominal_frame_rate",
            latest_detection_state.get("nominal_frame_rate"),
        ),
        "frame_size": payload.get("frame_size", latest_detection_state.get("frame_size")),
    })
    app[MASTER_LATEST_APRILTAG_PAYLOAD_KEY] = master_payload
    _broadcast(app, master_payload, add_master_send_time=True)

    detections = master_payload.get("detections") or []
    detection_summaries = []
    for detection in detections:
        detection_tag_id = get_detection_tag_id(detection)
        pose = detection.get("pose") or {}
        detection_summaries.append(
            f"tag_id={detection_tag_id} "
            f"t={format_numeric_vector(pose.get('t'))} "
            f"euler_xyz_deg={format_numeric_vector(R.from_matrix(pose.get('R')).as_euler('xyz', degrees=True)) if pose.get('R') else 'n/a'}"
        )
    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] apriltag packet received "
        f"({source}, count={len(detections)}, detections={detection_summaries})"
    )
    return master_payload
