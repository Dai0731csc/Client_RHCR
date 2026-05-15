from datetime import datetime
from typing import cast

import numpy as np

from ..models import (
    CameraCalibrationRequestMeta,
    CameraCalibrationResult,
    CameraCalibrationValidateRequestMeta,
)

def try_import_cv2():
    try:
        import cv2
    except ModuleNotFoundError:
        return None
    return cv2


def build_chessboard_object_points(board_rows, board_cols, square_size_mm):
    object_points = np.zeros((board_rows * board_cols, 3), np.float32)
    object_points[:, :2] = np.mgrid[0:board_cols, 0:board_rows].T.reshape(-1, 2)
    object_points *= float(square_size_mm)
    return object_points


def compute_reprojection_error(
    cv2,
    object_points_list,
    image_points_list,
    rvecs,
    tvecs,
    camera_matrix,
    dist_coeffs,
):
    total_error = 0.0
    total_points = 0

    for object_points, image_points, rvec, tvec in zip(
        object_points_list, image_points_list, rvecs, tvecs
    ):
        projected_points, _ = cv2.projectPoints(
            object_points, rvec, tvec, camera_matrix, dist_coeffs
        )
        error = cv2.norm(image_points, projected_points, cv2.NORM_L2)
        total_error += error * error
        total_points += len(object_points)

    if total_points == 0:
        return None

    return float(np.sqrt(total_error / total_points))


def validate_chessboard_image(
    image_bytes,
    metadata: CameraCalibrationValidateRequestMeta,
):
    cv2 = try_import_cv2()
    if cv2 is None:
        raise RuntimeError("OpenCV (cv2) is not installed in this environment")

    board_rows = int(metadata.get("board_rows", 6))
    board_cols = int(metadata.get("board_cols", 9))
    pattern_size = (board_cols, board_rows)

    np_buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(np_buffer, cv2.IMREAD_GRAYSCALE)
    if image is None:
        return {
            "success": True,
            "valid": False,
            "reason": "decode_failed",
        }

    found, corners = cv2.findChessboardCorners(image, pattern_size)
    return {
        "success": True,
        "valid": bool(found),
        "reason": None if found else "corners_not_found",
        "detected_corner_count": int(len(corners)) if found and corners is not None else 0,
    }


def calibrate_chessboard_camera(
    image_bytes_list,
    metadata: CameraCalibrationRequestMeta,
) -> CameraCalibrationResult:
    cv2 = try_import_cv2()
    if cv2 is None:
        raise RuntimeError("OpenCV (cv2) is not installed in this environment")

    board_rows = int(metadata.get("board_rows", 6))
    board_cols = int(metadata.get("board_cols", 9))
    square_size_mm = float(metadata.get("square_size_mm", 20.0))
    pattern_size = (board_cols, board_rows)
    termination_criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        30,
        0.001,
    )

    object_template = build_chessboard_object_points(board_rows, board_cols, square_size_mm)
    object_points_list = []
    image_points_list = []
    image_size = None
    valid_image_count = 0
    failed_images = []

    for image_index, image_bytes in enumerate(image_bytes_list):
        np_buffer = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(np_buffer, cv2.IMREAD_GRAYSCALE)
        if image is None:
            failed_images.append({"index": image_index, "reason": "decode_failed"})
            continue

        image_size = (image.shape[1], image.shape[0])
        found, corners = cv2.findChessboardCorners(image, pattern_size)
        if not found:
            failed_images.append({"index": image_index, "reason": "corners_not_found"})
            continue

        refined_corners = cv2.cornerSubPix(
            image,
            corners,
            (11, 11),
            (-1, -1),
            termination_criteria,
        )
        object_points_list.append(object_template.copy())
        image_points_list.append(refined_corners)
        valid_image_count += 1

    if valid_image_count < 10:
        raise ValueError(
            f"not enough valid calibration images: {valid_image_count} valid, need at least 10"
        )

    rms, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        object_points_list,
        image_points_list,
        image_size,
        None,
        None,
    )
    reprojection_error = compute_reprojection_error(
        cv2,
        object_points_list,
        image_points_list,
        rvecs,
        tvecs,
        camera_matrix,
        dist_coeffs,
    )

    return cast(CameraCalibrationResult, {
        "success": True,
        "board_type": "chessboard",
        "board_rows": board_rows,
        "board_cols": board_cols,
        "square_size_mm": square_size_mm,
        "image_width": image_size[0],
        "image_height": image_size[1],
        "valid_image_count": valid_image_count,
        "total_image_count": len(image_bytes_list),
        "rms": float(rms),
        "reprojection_error": reprojection_error,
        "intrinsics": {
            "fx": float(camera_matrix[0][0]),
            "fy": float(camera_matrix[1][1]),
            "cx": float(camera_matrix[0][2]),
            "cy": float(camera_matrix[1][2]),
        },
        "camera_matrix": camera_matrix.astype(float).tolist(),
        "dist_coeffs": dist_coeffs.reshape(-1).astype(float).tolist(),
        "failed_images": failed_images,
        "camera_settings": metadata.get("camera_settings", {}),
        "captured_at": datetime.now().isoformat(timespec="seconds"),
    })


def camera_calibration_available():
    return try_import_cv2() is not None


def run_camera_calibration(
    board_type,
    metadata: CameraCalibrationRequestMeta,
    image_bytes_list,
) -> CameraCalibrationResult:
    if board_type != "chessboard":
        raise ValueError(f"Unsupported calibration board type: {board_type}")
    return calibrate_chessboard_camera(image_bytes_list, metadata)


def run_camera_calibration_validation(
    image_bytes,
    metadata: CameraCalibrationValidateRequestMeta,
):
    return validate_chessboard_image(image_bytes, metadata)
