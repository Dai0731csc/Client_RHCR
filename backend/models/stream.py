from typing import Any, Literal, TypedDict


class TagPose(TypedDict):
    t: list[float]
    R: list[list[float]]


class FrameSize(TypedDict):
    width: int
    height: int


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
    frame_size: FrameSize | None
    master_receive_time: str | None
    master_send_time: str | None
    cloud_receive_time: str | None
    cloud_send_time: str | None
    control_socket_receive_time: str | None
    master_seq: int | None


class InitialCalibrationPayload(TypedDict, total=False):
    type: Literal["initial_calibration"]
    tag_id: int
    sample_count: int
    mean_pose: TagPose
    frame_size: FrameSize | None
    captured_at: str | None
    client_clock_offset_ms: float | None
    client_clock_rtt_ms: float | None
    master_receive_time: str | None
    master_send_time: str | None
    cloud_receive_time: str | None
    cloud_send_time: str | None
    control_socket_receive_time: str | None
    master_seq: int | None


class AprilTagDetectionsPayload(TypedDict, total=False):
    type: Literal["apriltag_detections"]
    detections: list[AprilTagDetection]
    nominal_frame_rate: float | None
    frame_size: FrameSize | None
    detectTag_start_time: str | None
    detectTag_end_time: str | None
    client_send_time: str | None
    client_clock_offset_ms: float | None
    client_clock_rtt_ms: float | None
    client_seq: int | None
    master_receive_time: str | None
    master_send_time: str | None
    cloud_receive_time: str | None
    cloud_send_time: str | None
    control_socket_receive_time: str | None
    master_seq: int | None


class StreamPayloadEnvelope(TypedDict, total=False):
    type: str
    payload: dict[str, Any]
