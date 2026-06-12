"""HTTP API for AprilTag distortion pose refinement (browser calls local client backend)."""

from __future__ import annotations

import json
from typing import Any

from aiohttp import web

from ..services.apriltag_distortion_pose import (
    ApriltagDistortionPoseEstimator,
    CameraIntrinsics,
    invert_pose,
)


def _json_error(message: str, *, status: int = 400) -> web.Response:
    return web.json_response({"success": False, "error": message}, status=status)


async def apriltag_refine_pose_handler(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _json_error("invalid JSON body")

    corners = body.get("corners")
    tag_size_m = body.get("tag_size_m")
    intrinsics = body.get("intrinsics")
    dist_coeffs = body.get("dist_coeffs")
    output_frame = str(body.get("output_frame") or "tag_camera").strip().lower()

    if not isinstance(corners, list) or len(corners) != 4:
        return _json_error("corners must be an array of 4 points")
    if tag_size_m is None:
        return _json_error("tag_size_m is required")
    if not isinstance(intrinsics, dict):
        return _json_error("intrinsics object is required")

    try:
        estimator = ApriltagDistortionPoseEstimator(
            intrinsics=CameraIntrinsics.from_mapping(intrinsics, dist_coeffs),
        )
        pose_camera = estimator.pose_camera_from_corners(corners, tag_size_m=float(tag_size_m))
    except (TypeError, ValueError) as exc:
        return _json_error(str(exc))
    except RuntimeError as exc:
        return web.json_response({"success": False, "error": str(exc)}, status=503)

    if pose_camera is None:
        return web.json_response(
            {"success": False, "error": "solvePnP failed"},
            status=422,
        )

    if output_frame == "camera":
        pose = pose_camera
        pose_frame = "camera_tag"
    elif output_frame == "tag_camera":
        pose = invert_pose(pose_camera)
        pose_frame = "tag_camera"
    else:
        return _json_error("output_frame must be 'tag_camera' or 'camera'")

    return web.json_response(
        {
            "success": True,
            "pose": pose,
            "pose_camera": pose_camera,
            "pose_frame": pose_frame,
            "pose_source": "distortion_corrected",
            "distortion_applied": estimator.intrinsics.has_distortion(),
        }
    )
