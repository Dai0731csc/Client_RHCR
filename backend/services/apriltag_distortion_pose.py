"""AprilTag pose refinement with camera calibration distortion (OpenCV Brown–Conrady)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
from scipy.spatial.transform import Rotation as R


def try_import_cv2():
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise RuntimeError("OpenCV (cv2) is required for distortion pose refinement") from exc
    return cv2


@dataclass(frozen=True)
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    dist_coeffs: tuple[float, ...] = ()

    @classmethod
    def from_mapping(cls, intrinsics: dict[str, Any], dist_coeffs: Sequence[float] | None = None) -> CameraIntrinsics:
        return cls(
            fx=float(intrinsics["fx"]),
            fy=float(intrinsics["fy"]),
            cx=float(intrinsics["cx"]),
            cy=float(intrinsics["cy"]),
            dist_coeffs=tuple(float(v) for v in (dist_coeffs or ())),
        )

    @classmethod
    def from_device_calibration(cls, device: dict[str, Any]) -> CameraIntrinsics:
        cal = device.get("camera_calibration") or {}
        intr = cal.get("intrinsics") or {}
        dist = cal.get("dist_coeffs") or []
        return cls.from_mapping(intr, dist)

    def has_distortion(self) -> bool:
        return any(abs(coeff) > 1e-9 for coeff in self.dist_coeffs)

    def as_camera_matrix(self) -> np.ndarray:
        return np.array(
            [[self.fx, 0.0, self.cx], [0.0, self.fy, self.cy], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )

    def as_dist_coeffs(self) -> np.ndarray:
        if not self.dist_coeffs:
            return np.zeros((5, 1), dtype=np.float64)
        return np.asarray(self.dist_coeffs, dtype=np.float64).reshape(-1, 1)


def normalize_wasm_corners(corners: Sequence[Any]) -> np.ndarray:
    """WASM JSON corners [{x,y}, ...] → OpenCV shape (1, 4, 2)."""
    rows: list[list[float]] = []
    for corner in corners:
        if isinstance(corner, dict):
            rows.append([float(corner["x"]), float(corner["y"])])
        else:
            rows.append([float(corner[0]), float(corner[1])])
    if len(rows) != 4:
        raise ValueError(f"expected 4 tag corners, got {len(rows)}")
    return np.asarray(rows, dtype=np.float64).reshape(1, 4, 2)


def tag_object_points_m(tag_size_m: float) -> np.ndarray:
    """OpenCV aruco / AprilTag planar corner layout in tag frame (Z=0)."""
    half = float(tag_size_m) / 2.0
    return np.array(
        [
            [-half, half, 0.0],
            [half, half, 0.0],
            [half, -half, 0.0],
            [-half, -half, 0.0],
        ],
        dtype=np.float64,
    )


def invert_pose(pose: dict[str, Any]) -> dict[str, Any]:
    """Same SE(3) inverse as client/frontend/modules/pose.js invertPose."""
    rot = np.asarray(pose["R"], dtype=float).reshape(3, 3)
    trans = np.asarray(pose["t"], dtype=float).reshape(3)
    inv_r = rot.T
    inv_t = -(inv_r @ trans)
    return {"t": inv_t.tolist(), "R": inv_r.tolist()}


def pose_from_rvec_tvec(rvec: np.ndarray, tvec: np.ndarray) -> dict[str, Any]:
    rot = R.from_rotvec(np.asarray(rvec, dtype=float).reshape(3)).as_matrix()
    trans = np.asarray(tvec, dtype=float).reshape(3)
    return {"t": trans.tolist(), "R": rot.tolist()}


@dataclass
class ApriltagDistortionPoseEstimator:
    """
    Refine WASM corners → camera-frame pose using calibrated distortion.

    Default path: undistortPoints → solvePnP (zero dist), matching OpenCV best practice.
    """

    intrinsics: CameraIntrinsics
    undistort_first: bool = True

    def pose_camera_from_corners(
        self,
        corners: Sequence[Any],
        *,
        tag_size_m: float,
    ) -> dict[str, Any] | None:
        cv2 = try_import_cv2()
        camera_matrix = self.intrinsics.as_camera_matrix()
        dist = self.intrinsics.as_dist_coeffs()
        image_points = normalize_wasm_corners(corners)

        if self.undistort_first and self.intrinsics.has_distortion():
            image_points = cv2.undistortPoints(image_points, camera_matrix, dist, P=camera_matrix)
            dist = np.zeros((5, 1), dtype=np.float64)

        flags = getattr(cv2, "SOLVEPNP_ITERATIVE", 0)
        ok, rvec, tvec = cv2.solvePnP(
            tag_object_points_m(tag_size_m),
            image_points.reshape(4, 2).astype(np.float64),
            camera_matrix,
            dist,
            flags=flags,
        )
        if not ok:
            return None
        return pose_from_rvec_tvec(rvec, tvec)

    def pose_tag_camera_from_corners(
        self,
        corners: Sequence[Any],
        *,
        tag_size_m: float,
    ) -> dict[str, Any] | None:
        pose_camera = self.pose_camera_from_corners(corners, tag_size_m=tag_size_m)
        if pose_camera is None:
            return None
        return invert_pose(pose_camera)

    def refine_detection(
        self,
        detection: dict[str, Any],
        *,
        tag_size_m: float,
        apply_tag_camera_frame: bool = True,
    ) -> dict[str, Any]:
        """Return detection copy; replace pose when distortion correction succeeds."""
        corners = detection.get("corners")
        if corners is None:
            return detection

        pose_camera = self.pose_camera_from_corners(corners, tag_size_m=tag_size_m)
        if pose_camera is None:
            return detection

        refined = dict(detection)
        if apply_tag_camera_frame:
            refined["pose"] = invert_pose(pose_camera)
            refined["pose_frame"] = "tag_camera"
            refined["pose_source"] = "distortion_corrected"
        else:
            refined["pose"] = pose_camera
            refined["pose_frame"] = "camera_tag_wasm_equiv"
            refined["pose_source"] = "distortion_corrected_camera"
        return refined

    def refine_detections(
        self,
        detections: Sequence[dict[str, Any]],
        *,
        tag_size_m: float,
        apply_tag_camera_frame: bool = True,
    ) -> list[dict[str, Any]]:
        if not self.intrinsics.has_distortion():
            return [dict(item) for item in detections]
        return [
            self.refine_detection(
                item,
                tag_size_m=tag_size_m,
                apply_tag_camera_frame=apply_tag_camera_frame,
            )
            for item in detections
        ]


def build_estimator_from_device(
    device: dict[str, Any],
    *,
    undistort_first: bool = True,
) -> ApriltagDistortionPoseEstimator:
    return ApriltagDistortionPoseEstimator(
        intrinsics=CameraIntrinsics.from_device_calibration(device),
        undistort_first=undistort_first,
    )
