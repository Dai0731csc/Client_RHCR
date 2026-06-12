/**
 * AprilTag pose refinement with camera calibration distortion.
 *
 * WASM still performs detection (corners). When distCoeffs are present, this module
 * calls the local client backend (OpenCV) to replace pose before tag_camera invert.
 */
(function initApriltagDistortionPose(ns) {
  const { state, constants, withBasePath } = ns;

  const REFINE_POSE_API_PATH = withBasePath("/api/apriltag/refine-pose");

  function hasDistortionCorrection(intrinsicsRecord) {
    const dist = intrinsicsRecord?.distCoeffs;
    return (
      Array.isArray(dist) &&
      dist.length >= 4 &&
      dist.some((value) => Math.abs(Number(value)) > 1e-9)
    );
  }

  function intrinsicsPayload(intrinsicsRecord) {
    if (!intrinsicsRecord) {
      return null;
    }
    return {
      fx: Number(intrinsicsRecord.fx),
      fy: Number(intrinsicsRecord.fy),
      cx: Number(intrinsicsRecord.cx),
      cy: Number(intrinsicsRecord.cy),
      dist_coeffs: Array.isArray(intrinsicsRecord.distCoeffs)
        ? intrinsicsRecord.distCoeffs.map((value) => Number(value))
        : [],
    };
  }

  async function refineDetectionPose(detection, options = {}) {
    const intrinsicsRecord = options.intrinsicsRecord ?? state.currentIntrinsicsRecord;
    const tagSizeM = Number(options.tagSizeM ?? constants.DEFAULT_TAG_SIZE_METERS);
    const outputFrame = options.outputFrame ?? "tag_camera";

    if (!detection?.corners || !hasDistortionCorrection(intrinsicsRecord)) {
      return detection;
    }

    const payload = intrinsicsPayload(intrinsicsRecord);
    if (!payload) {
      return detection;
    }

    try {
      const response = await fetch(REFINE_POSE_API_PATH, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          corners: detection.corners,
          tag_size_m: tagSizeM,
          intrinsics: {
            fx: payload.fx,
            fy: payload.fy,
            cx: payload.cx,
            cy: payload.cy,
          },
          dist_coeffs: payload.dist_coeffs,
          output_frame: outputFrame,
        }),
      });

      const result = await response.json();
      if (!response.ok || !result?.success || !result.pose) {
        console.warn("Distortion pose refine failed:", result?.error || response.status);
        return detection;
      }

      return {
        ...detection,
        pose: result.pose,
        pose_frame: result.pose_frame || outputFrame,
        pose_source: result.pose_source || "distortion_corrected",
      };
    } catch (error) {
      console.warn("Distortion pose refine request failed:", error);
      return detection;
    }
  }

  async function refineDetectionPoses(detections, options = {}) {
    if (!Array.isArray(detections) || !detections.length) {
      return detections;
    }
    const intrinsicsRecord = options.intrinsicsRecord ?? state.currentIntrinsicsRecord;
    if (!hasDistortionCorrection(intrinsicsRecord)) {
      return detections;
    }
    return Promise.all(detections.map((detection) => refineDetectionPose(detection, options)));
  }

  ns.apriltagDistortion = {
    hasDistortionCorrection,
    refineDetectionPose,
    refineDetectionPoses,
  };
})(window.CameraPage = window.CameraPage || {});
