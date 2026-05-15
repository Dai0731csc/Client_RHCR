from typing import Literal, TypedDict

from .calibration import CameraCalibrationResult


class DeviceProfile(TypedDict):
    version: Literal[1]
    ip: str
    region: str
    first_seen_at: str | None
    last_seen_at: str | None
    camera_calibration_updated_at: str | None
    camera_calibration: CameraCalibrationResult | None


class DeviceProfileResponse(TypedDict):
    success: bool
    device: DeviceProfile
