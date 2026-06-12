"""Human-readable TeleProgram logs for tag_camera poses (invertPose)."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.spatial.transform import Rotation as SciRot

TAG_CAMERA_FRAME_LEGEND = (
    "[tag_camera] 平移·右手: +X画面右 +Y画面下 +Z靠近标签 | "
    "旋转·ω_手: 对「拧手机」的右手定则(拇指=+轴,四指=正转角); "
    "与库内 R 的 rotvec 反号(因 R 是相机在 tag 系朝向)"
)

_SMALL = 1e-4


def _arrow(value: float, positive: str, negative: str, neutral: str = "·") -> str:
    if value > _SMALL:
        return positive
    if value < -_SMALL:
        return negative
    return neutral


def format_tag_camera_translation(t: Any) -> str:
    if t is None:
        return "t=n/a"
    tx, ty, tz = (float(v) for v in t[:3])
    return (
        f"x={tx:+.3f}{_arrow(tx, '→', '←')} "
        f"y={ty:+.3f}{_arrow(ty, '↓', '↑')} "
        f"z={tz:+.3f}{_arrow(tz, '近', '远')}"
    )


def _rotvec_tag_deg(R_matrix: Any) -> np.ndarray | None:
    if R_matrix is None:
        return None
    return np.degrees(SciRot.from_matrix(np.asarray(R_matrix, dtype=float)).as_rotvec())


def rotvec_hand_deg_from_R(R_matrix: Any) -> np.ndarray | None:
    """Intuitive camera-hand rotation (RH): negates tag_camera orientation rotvec."""
    rv = _rotvec_tag_deg(R_matrix)
    if rv is None:
        return None
    return -rv


def _format_hand_rotvec(rv: np.ndarray | None, *, prefix: str) -> str:
    if rv is None:
        return f"{prefix}=n/a"
    magnitude = float(np.linalg.norm(rv))
    if magnitude < 0.05:
        return f"{prefix}≈0°"
    axis_index = int(np.argmax(np.abs(rv)))
    axis_name = ("X", "Y", "Z")[axis_index]
    signed_angle = float(rv[axis_index])
    sign = "+" if signed_angle >= 0 else "-"
    return (
        f"{prefix}°=[{rv[0]:+.1f},{rv[1]:+.1f},{rv[2]:+.1f}] "
        f"主绕{sign}{axis_name}{abs(signed_angle):.1f}°"
    )


def format_tag_camera_rotvec_hand(R_matrix: Any) -> str:
    return _format_hand_rotvec(rotvec_hand_deg_from_R(R_matrix), prefix="ω_手")


def format_tag_camera_detection_summary(
    *,
    tag_id: Any,
    pose: Mapping[str, Any],
) -> str:
    t_part = format_tag_camera_translation(pose.get("t"))
    rot_part = format_tag_camera_rotvec_hand(pose.get("R"))
    return f"tag#{tag_id} | {t_part} | {rot_part}"
