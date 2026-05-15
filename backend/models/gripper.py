from typing import Literal, TypedDict


class GripperCommandPayload(TypedDict):
    type: Literal["gripper_command"]
    protocol: str
    request_id: str
    action: Literal["open", "close"]
    client_time: str


class GripperDispatchResult(TypedDict):
    success: bool
    accepted: bool
    status: int
    error: str | None
    message: str | None
