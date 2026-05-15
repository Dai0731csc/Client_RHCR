from typing import Any, Literal, TypedDict


class CameraIntrinsics(TypedDict):
    fx: float
    fy: float
    cx: float
    cy: float


class FailedCalibrationImage(TypedDict):
    index: int
    reason: str


class CameraCalibrationRequestMeta(TypedDict, total=False):
    board_type: Literal["chessboard"]
    board_rows: int
    board_cols: int
    square_size_mm: float
    camera_settings: dict[str, Any]


class CameraCalibrationValidateRequestMeta(CameraCalibrationRequestMeta, total=False):
    pass


class CameraCalibrationResult(TypedDict, total=False):
    success: bool
    board_type: Literal["chessboard"]
    board_rows: int
    board_cols: int
    square_size_mm: float
    image_width: int
    image_height: int
    total_image_count: int
    valid_image_count: int
    rms: float
    reprojection_error: float | None
    intrinsics: CameraIntrinsics
    camera_matrix: list[list[float]]
    dist_coeffs: list[float] | None
    failed_images: list[FailedCalibrationImage]
    camera_settings: dict[str, Any]
    captured_at: str | None
