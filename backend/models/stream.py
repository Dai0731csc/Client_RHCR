from typing import Any, Literal, TypedDict


class TagPose(TypedDict):
    t: list[float]
    R: list[list[float]]


class AprilTagDetection(TypedDict, total=False):
    id: int | None
    tag_id: int
    decision_margin: float | None
    center: list[float] | None
    corners: list[list[float]] | None
    pose: TagPose | None


class DetectionStatePayload(TypedDict, total=False):
    type: Literal["detection_state"]
    active: bool
    nominal_frame_rate: float | None
    frame_size: list[int] | None
    server_receive_time: str | None
    server_send_time: str | None
    master_seq: int | None


class InitialCalibrationPayload(TypedDict, total=False):
    type: Literal["initial_calibration"]
    tag_id: int
    sample_count: int
    mean_pose: TagPose
    server_send_time: str | None
    master_seq: int | None


class AprilTagDetectionsPayload(TypedDict, total=False):
    type: Literal["apriltag_detections"]
    detections: list[AprilTagDetection]
    nominal_frame_rate: float | None
    frame_size: list[int] | None
    server_receive_time: str | None
    server_send_time: str | None
    master_seq: int | None


class StreamPayloadEnvelope(TypedDict, total=False):
    type: str
    payload: dict[str, Any]
