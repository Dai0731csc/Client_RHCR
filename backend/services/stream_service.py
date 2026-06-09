from datetime import datetime
from typing import Any, Mapping, cast
import json
import os
from pathlib import Path

import cv2
import numpy as np

from ..models import AprilTagDetectionsPayload, DetectionStatePayload, InitialCalibrationPayload
from ..state import (
    MASTER_LATEST_APRILTAG_PAYLOAD_KEY,
    MASTER_LATEST_DETECTION_STATE_KEY,
    MASTER_LATEST_INITIAL_CALIBRATION_KEY,
)
from ..links import get_links
from ..utils import with_server_receive_time


# 放在 stream_service.py 顶部，JOINT_POSE_FILTER_ALPHA 附近

JOINT_POSE_FILTER_ALPHA = 0.2
JOINT_POSE_MAX_STEP_NORM = 0.15
LAST_JOINT_POSE_KEY = "last_joint_pose"

# ============================================================
# 在这里设置你的相机 IP，对应文件：
# backend/data/devices/{CAMERA_CALIBRATION_DEVICE_IP}.json
# 例如：
# backend/data/devices/192.168.2.165.json
# ============================================================
CAMERA_CALIBRATION_DEVICE_IP = "192.168.2.165"



def _log(message):
    print(f"[TeleProgram] {message}")


def _broadcast(app, payload):
    get_links(app).outbound.broadcast_pose(app, payload)



def get_detection_tag_id(detection: Mapping[str, Any] | None):
    if not isinstance(detection, dict):
        return None

    detection_tag_id = detection.get("tag_id")
    if detection_tag_id is None:
        detection_tag_id = detection.get("id")

    if detection_tag_id is None:
        return None

    try:
        return int(detection_tag_id)
    except Exception:
        return detection_tag_id


def format_numeric_vector(values):
    if values is None:
        return "n/a"
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    if values.size == 0 or not np.all(np.isfinite(values)):
        return "n/a"
    return "[" + ", ".join(f"{float(value):.4f}" for value in values) + "]"


def format_matrix(matrix):
    if matrix is None:
        return "n/a"
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.size == 0 or not np.all(np.isfinite(matrix)):
        return "n/a"
    rows = []
    for row in matrix:
        rows.append("[" + ", ".join(f"{float(v):.4f}" for v in row) + "]")
    return "[" + ", ".join(rows) + "]"


def _normalize_corner_point(point):
    if isinstance(point, dict):
        if "x" in point and "y" in point:
            return [float(point["x"]), float(point["y"])]
        if "u" in point and "v" in point:
            return [float(point["u"]), float(point["v"])]
        if "0" in point and "1" in point:
            return [float(point["0"]), float(point["1"])]
    return [float(point[0]), float(point[1])]


def _normalize_corners(corners):
    return np.array([_normalize_corner_point(p) for p in corners], dtype=np.float64).reshape(4, 2)


def _is_finite_array(x):
    arr = np.asarray(x, dtype=np.float64)
    return np.all(np.isfinite(arr))


# 替换原来的 _get_camera_calibration_device_ip(app)

def _get_camera_calibration_device_ip(app):
    device_ip = (
        app.get("camera_calibration_device_ip")
        or app.get("device_ip")
        or app.get("camera_ip")
        or app.get("device_id")
        or app.get("camera_device_id")
        or app.get("host")
        or app.get("camera_host")
        or CAMERA_CALIBRATION_DEVICE_IP
    )

    if device_ip is None:
        return None

    device_ip = str(device_ip).strip()
    return device_ip or None



# 替换原来的 _load_camera_calibration_from_device_json(app)

def _load_camera_calibration_from_device_json(app):
    device_ip = _get_camera_calibration_device_ip(app)

    if not device_ip:
        _log("skip loading calibration json: missing camera IP")
        return None, None

    filename = f"{device_ip}.json"
    here = Path(__file__).resolve()

    candidates = [
        here.parents[1] / "data" / "devices" / filename,
        here.parents[2] / "backend" / "data" / "devices" / filename,
        Path.cwd() / "backend" / "data" / "devices" / filename,
        Path.cwd() / "data" / "devices" / filename,
        Path.cwd() / "devices" / filename,
        Path.cwd() / filename,
    ]

    seen = set()
    unique_candidates = []
    for path in candidates:
        path = path.resolve()
        if path not in seen:
            seen.add(path)
            unique_candidates.append(path)

    for path in unique_candidates:
        try:
            if not path.exists():
                continue

            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            calib = data.get("camera_calibration") or data

            camera_matrix = (
                calib.get("camera_matrix")
                or calib.get("K")
                or calib.get("intrinsic_matrix")
            )

            intrinsics = calib.get("intrinsics") or {}
            if camera_matrix is None and intrinsics:
                fx = intrinsics.get("fx")
                fy = intrinsics.get("fy")
                cx = intrinsics.get("cx")
                cy = intrinsics.get("cy")

                if fx is not None and fy is not None and cx is not None and cy is not None:
                    camera_matrix = [
                        [fx, 0.0, cx],
                        [0.0, fy, cy],
                        [0.0, 0.0, 1.0],
                    ]

            dist_coeffs = (
                calib.get("dist_coeffs")
                or calib.get("distortion_coefficients")
                or calib.get("distortion")
                or np.zeros(5)
            )

            if camera_matrix is None:
                continue

            camera_matrix = np.asarray(camera_matrix, dtype=np.float64)
            if camera_matrix.size == 9:
                camera_matrix = camera_matrix.reshape(3, 3)

            dist_coeffs = np.asarray(dist_coeffs, dtype=np.float64).reshape(-1)

            if camera_matrix.shape != (3, 3):
                continue

            if not _is_finite_array(camera_matrix) or not _is_finite_array(dist_coeffs):
                continue

            fx = float(camera_matrix[0, 0])
            fy = float(camera_matrix[1, 1])
            cx = float(camera_matrix[0, 2])
            cy = float(camera_matrix[1, 2])

            if fx < 50 or fy < 50 or cx <= 0 or cy <= 0:
                continue

            _log(f"loaded camera calibration from {path}")
            return camera_matrix, dist_coeffs

        except Exception as exc:
            _log(f"failed loading calibration {path}: {exc}")

    _log(f"camera calibration json not found or invalid for ip={device_ip}")
    return None, None



def _get_valid_camera_params(app):
    calib = app.get(MASTER_LATEST_INITIAL_CALIBRATION_KEY) or {}

    camera_matrix = (
        calib.get("camera_matrix")
        or calib.get("K")
        or calib.get("intrinsic_matrix")
    )

    intrinsics = calib.get("intrinsics") or {}
    if camera_matrix is None and intrinsics:
        fx = intrinsics.get("fx")
        fy = intrinsics.get("fy")
        cx = intrinsics.get("cx")
        cy = intrinsics.get("cy")

        if fx is not None and fy is not None and cx is not None and cy is not None:
            camera_matrix = [
                [fx, 0.0, cx],
                [0.0, fy, cy],
                [0.0, 0.0, 1.0],
            ]

    dist_coeffs = (
        calib.get("dist_coeffs")
        or calib.get("distortion_coefficients")
        or calib.get("distortion")
        or np.zeros(5)
    )

    if camera_matrix is not None:
        camera_matrix = np.asarray(camera_matrix, dtype=np.float64)

        if camera_matrix.size == 9:
            camera_matrix = camera_matrix.reshape(3, 3)

        dist_coeffs = np.asarray(dist_coeffs, dtype=np.float64).reshape(-1)

        if (
            camera_matrix.shape == (3, 3)
            and _is_finite_array(camera_matrix)
            and _is_finite_array(dist_coeffs)
        ):
            fx = float(camera_matrix[0, 0])
            fy = float(camera_matrix[1, 1])
            cx = float(camera_matrix[0, 2])
            cy = float(camera_matrix[1, 2])

            if fx >= 50 and fy >= 50 and cx > 0 and cy > 0:
                return camera_matrix, dist_coeffs

    camera_matrix, dist_coeffs = _load_camera_calibration_from_device_json(app)
    if camera_matrix is not None and dist_coeffs is not None:
        return camera_matrix, dist_coeffs

    _log("skip PnP: missing valid camera calibration")
    return None, None


def _valid_image_points_px(image_points_2d):
    image_points_2d = np.asarray(image_points_2d, dtype=np.float64)

    if image_points_2d.shape != (4, 2):
        return False

    if not np.all(np.isfinite(image_points_2d)):
        return False

    if np.nanmax(np.abs(image_points_2d)) <= 2.0:
        return False

    return True


def rt_to_pose(R_mat, t_vec):
    return {
        "R": np.asarray(R_mat, dtype=np.float64).tolist(),
        "t": np.asarray(t_vec, dtype=np.float64).reshape(-1).tolist(),
    }


def invert_pose(R_mat, t_vec):
    R_mat = np.asarray(R_mat, dtype=np.float64).reshape(3, 3)
    t_vec = np.asarray(t_vec, dtype=np.float64).reshape(3)
    R_inv = R_mat.T
    t_inv = -R_inv @ t_vec
    return R_inv, t_inv


def _pose_from_rvec_tvec(rvec, tvec):
    if not _is_finite_array(rvec) or not _is_finite_array(tvec):
        return None
    R_bc, _ = cv2.Rodrigues(rvec)
    if not _is_finite_array(R_bc):
        return None
    R_cb, t_cb = invert_pose(R_bc, tvec.flatten())
    if not _is_finite_array(R_cb) or not _is_finite_array(t_cb):
        return None
    return R_cb, t_cb


def _try_solve_pnp(object_points, image_points, camera_matrix, dist_coeffs, flag):
    try:
        success, rvec, tvec = cv2.solvePnP(
            object_points,
            image_points,
            camera_matrix,
            dist_coeffs,
            flags=flag,
        )
        if not success:
            return None
        return _pose_from_rvec_tvec(rvec, tvec)
    except Exception:
        return None


def solve_tag_pose_from_body_points(body_points_3d, image_points_2d, camera_matrix, dist_coeffs):
    if not _is_finite_array(body_points_3d):
        return None
    if not _is_finite_array(image_points_2d):
        return None
    if not _is_finite_array(camera_matrix):
        return None
    if not _is_finite_array(dist_coeffs):
        return None

    for flag in (
        cv2.SOLVEPNP_IPPE,
        cv2.SOLVEPNP_ITERATIVE,
        cv2.SOLVEPNP_EPNP,
    ):
        result = _try_solve_pnp(
            body_points_3d,
            image_points_2d,
            camera_matrix,
            dist_coeffs,
            flag,
        )
        if result is not None:
            return result

    return None


def solve_array_pose_tang(body_points_3d, image_points_2d, camera_matrix, dist_coeffs):
    if not _is_finite_array(body_points_3d):
        return None
    if not _is_finite_array(image_points_2d):
        return None
    if not _is_finite_array(camera_matrix):
        return None
    if not _is_finite_array(dist_coeffs):
        return None
    if len(body_points_3d) < 8:
        return None

    try:
        success, rvec, tvec = cv2.solvePnP(
            body_points_3d,
            image_points_2d,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_EPNP,
        )
        if not success:
            return None
        if not _is_finite_array(rvec) or not _is_finite_array(tvec):
            return None

        try:
            rvec, tvec = cv2.solvePnPRefineLM(
                body_points_3d,
                image_points_2d,
                camera_matrix,
                dist_coeffs,
                rvec,
                tvec,
                criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6),
            )
        except Exception:
            pass

        return _pose_from_rvec_tvec(rvec, tvec)
    except Exception:
        return None


def build_body_points_from_tag(tag_id, tag_corners_ti, tag_ti2body):
    R_Ti_B, t_Ti_B = tag_ti2body[tag_id]
    return (R_Ti_B.T @ (tag_corners_ti - t_Ti_B).T).T


def _is_pose_valid(pose):
    if not isinstance(pose, dict):
        return False
    return _is_finite_array(pose.get("R")) and _is_finite_array(pose.get("t"))


def _smooth_rotation(R_prev, R_new, alpha):
    R_rel = R_new @ R_prev.T
    rvec, _ = cv2.Rodrigues(R_rel)
    rvec = alpha * rvec
    R_inc, _ = cv2.Rodrigues(rvec)
    return R_inc @ R_prev


def _stabilize_joint_pose(app, pose):
    """
    只在当前帧有有效 pose 时才平滑。
    当前帧没有有效 pose 时，返回 None，而不是返回上一帧。
    否则单 Tag 或丢 Tag 时会看起来 t/R 卡住不动。
    """
    if pose is None or not _is_pose_valid(pose):
        return None

    t_new = np.asarray(pose["t"], dtype=np.float64).reshape(3)
    R_new = np.asarray(pose["R"], dtype=np.float64).reshape(3, 3)

    last_pose = app.get(LAST_JOINT_POSE_KEY)
    if not _is_pose_valid(last_pose):
        stabilized = rt_to_pose(R_new, t_new)
        app[LAST_JOINT_POSE_KEY] = stabilized
        return stabilized

    t_prev = np.asarray(last_pose["t"], dtype=np.float64).reshape(3)
    R_prev = np.asarray(last_pose["R"], dtype=np.float64).reshape(3, 3)

    step = t_new - t_prev
    step_norm = float(np.linalg.norm(step))

    if step_norm > JOINT_POSE_MAX_STEP_NORM:
        t_new = t_prev + step / step_norm * JOINT_POSE_MAX_STEP_NORM

    t_smooth = (1.0 - JOINT_POSE_FILTER_ALPHA) * t_prev + JOINT_POSE_FILTER_ALPHA * t_new
    R_smooth = _smooth_rotation(R_prev, R_new, JOINT_POSE_FILTER_ALPHA)

    stabilized = rt_to_pose(R_smooth, t_smooth)
    app[LAST_JOINT_POSE_KEY] = stabilized
    return stabilized



def ingest_initial_calibration_payload(
    app,
    payload: InitialCalibrationPayload,
    *,
    source="websocket",
) -> InitialCalibrationPayload:
    payload = cast(InitialCalibrationPayload, with_server_receive_time(payload))
    app[MASTER_LATEST_INITIAL_CALIBRATION_KEY] = payload
    _broadcast(app, payload)
    mean_pose = payload.get("mean_pose", {})
    mean_t = mean_pose.get("t")
    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] calibration payload "
        f"({source}): tag_id={payload.get('tag_id')} "
        f"sample_count={payload.get('sample_count')} mean_t={mean_t}"
    )
    return payload


async def ingest_apriltag_payload(app, payload: dict[str, Any], *, source="websocket"):
    payload = with_server_receive_time(payload)
    message_type = payload.get("type")

    if message_type == "detection_state":
        detection_state_payload = cast(DetectionStatePayload, payload)
        app[MASTER_LATEST_DETECTION_STATE_KEY] = detection_state_payload
        _broadcast(app, detection_state_payload)
        _log(
            f"[{datetime.now().strftime('%H:%M:%S')}] detection state "
            f"({source}): active={bool(detection_state_payload.get('active', False))} "
            f"fps={detection_state_payload.get('nominal_frame_rate')} "
            f"frame_size={detection_state_payload.get('frame_size')}"
        )
        return detection_state_payload

    if message_type != "apriltag_detections":
        return payload

    latest_detection_state = app.get(MASTER_LATEST_DETECTION_STATE_KEY) or {}

    master_payload = cast(
        AprilTagDetectionsPayload,
        {
            **payload,
            "nominal_frame_rate": payload.get(
                "nominal_frame_rate",
                latest_detection_state.get("nominal_frame_rate"),
            ),
            "frame_size": payload.get(
                "frame_size",
                latest_detection_state.get("frame_size"),
            ),
        },
    )

    detections = master_payload.get("detections") or []

    camera_matrix, dist_coeffs = _get_valid_camera_params(app)
    if camera_matrix is None or dist_coeffs is None:
        master_payload = cast(
            AprilTagDetectionsPayload,
            {
                **master_payload,
                "detections": [
                    {
                        **detection,
                        "pose": {},
                    }
                    for detection in detections
                ],
                "joint_pose": None,
                "used_tag_ids": [],
            },
        )

        app[MASTER_LATEST_APRILTAG_PAYLOAD_KEY] = master_payload
        _broadcast(app, master_payload)
        _log("skip fused pose: no valid camera calibration")
        return master_payload

    updated_detections = []

    W = 0.15
    H = 0.25
    L = 0.15
    half_W = W / 2.0
    half_H = H / 2.0
    half_L = L / 2.0

    tag_ti2body = {
        0: (
            np.array([[0, 0, -1], [1, 0, 0], [0, -1, 0]], dtype=np.float64),
            np.array([half_L, 0.0017, 0.001], dtype=np.float64),
        ),
        1: (
            np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=np.float64),
            np.array([-0.001, -half_W, 0], dtype=np.float64),
        ),
        2: (
            np.array([[0, 1, 0], [1, 0, 0], [0, 0, -1]], dtype=np.float64),
            np.array([-0.001, -0.0003, half_H], dtype=np.float64),
        ),
        3: (
            np.array([[-1, 0, 0], [0, 0, -1], [0, -1, 0]], dtype=np.float64),
            np.array([0.001, half_W, 0], dtype=np.float64),
        ),
        4: (
            np.array([[0, 0, 1], [-1, 0, 0], [0, -1, 0]], dtype=np.float64),
            np.array([-half_L, 0.0001, -0.0005], dtype=np.float64),
        ),
    }

    TAG_SIZE = 0.078
    half_tag = TAG_SIZE / 2.0
    tag_corners_ti = np.array(
        [
            [-half_tag, -half_tag, 0.0],
            [half_tag, -half_tag, 0.0],
            [half_tag, half_tag, 0.0],
            [-half_tag, half_tag, 0.0],
        ],
        dtype=np.float64,
    )

    all_body_3d = []
    all_image_2d = []
    used_tag_ids = []

    for detection in detections:
        detection_tag_id = get_detection_tag_id(detection)
        pose = {}

        if detection_tag_id in tag_ti2body and "corners" in detection:
            try:
                image_points_2d = _normalize_corners(detection["corners"])

                if not _valid_image_points_px(image_points_2d):
                    _log(f"skip tag {detection_tag_id}: corners are not pixel coordinates")
                    updated_detections.append(
                        {
                            **detection,
                            "pose": {},
                        }
                    )
                    continue

                body_points_3d = build_body_points_from_tag(
                    detection_tag_id,
                    tag_corners_ti,
                    tag_ti2body,
                )

                tag_solution = solve_tag_pose_from_body_points(
                    body_points_3d,
                    image_points_2d,
                    camera_matrix,
                    dist_coeffs,
                )

                if tag_solution is not None:
                    R_cb_tag, t_cb_tag = tag_solution
                    pose = rt_to_pose(R_cb_tag, t_cb_tag)
                    all_body_3d.append(body_points_3d)
                    all_image_2d.append(image_points_2d)
                    used_tag_ids.append(detection_tag_id)
            except Exception as exc:
                _log(f"skip tag {detection_tag_id}: {exc}")
                pose = {}

        updated_detections.append(
            {
                **detection,
                "pose": pose,
            }
        )

        joint_pose = None

    if len(all_body_3d) >= 1:
        joint_body_3d = np.vstack(all_body_3d).astype(np.float64)
        joint_image_2d = np.vstack(all_image_2d).astype(np.float64)

        joint_solution = None

        if len(all_body_3d) >= 2:
            joint_solution = solve_array_pose_tang(
                joint_body_3d,
                joint_image_2d,
                camera_matrix,
                dist_coeffs,
            )

        if joint_solution is None:
            joint_solution = solve_tag_pose_from_body_points(
                joint_body_3d,
                joint_image_2d,
                camera_matrix,
                dist_coeffs,
            )

        if joint_solution is not None:
            R_cb, t_cb = joint_solution
            joint_pose = rt_to_pose(R_cb, t_cb)

    joint_pose = _stabilize_joint_pose(app, joint_pose)


    master_payload = cast(
        AprilTagDetectionsPayload,
        {
            **master_payload,
            "detections": updated_detections,
            "joint_pose": joint_pose,
            "used_tag_ids": used_tag_ids,
        },
    )

    if _is_pose_valid(joint_pose):
        app["camera_in_body_rot"] = joint_pose["R"]
        app["camera_in_body_trans"] = joint_pose["t"]

    app[MASTER_LATEST_APRILTAG_PAYLOAD_KEY] = master_payload
    _broadcast(app, master_payload)

    _log(
        f"[{datetime.now().strftime('%H:%M:%S')}] fused pose "
        f"({source}, used_tags={used_tag_ids}, "
        f"t={format_numeric_vector((joint_pose or {}).get('t'))}, "
        f"R={format_matrix((joint_pose or {}).get('R'))})"
    )

    return master_payload
