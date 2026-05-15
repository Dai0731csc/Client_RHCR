(function initCameraTransportPayloads(ns) {
  const { dom, state, constants } = ns;
  const transport = ns.transport || (ns.transport = {});
  /** Monotonic counter per apriltag_detections publish (browser → TeleProgram). */
  let clientEmitSeq = 0;

  function toIsoString(wallMs) {
    return new Date(wallMs).toISOString();
  }

  function createTimestampInfo(wallMs = Date.now()) {
    const snapshot = state.timeSyncClient.getSnapshot();
    return {
      wallMs,
      wallTimeIso: toIsoString(wallMs),
      clockOffsetMs: Number.isFinite(snapshot.offsetMs) ? snapshot.offsetMs : null,
      clockRttMs: Number.isFinite(snapshot.rttMs) ? snapshot.rttMs : null,
    };
  }

  function createApriltagPayload(detections, timings = {}) {
    const sendTimestamp = createTimestampInfo();
    clientEmitSeq += 1;
    return {
      type: "apriltag_detections",
      detectTag_start_time: timings.detectTagStartTime || null,
      detectTag_end_time: timings.detectTagEndTime || null,
      client_send_time: sendTimestamp.wallTimeIso,
      client_clock_offset_ms: sendTimestamp.clockOffsetMs,
      client_clock_rtt_ms: sendTimestamp.clockRttMs,
      client_seq: clientEmitSeq,
      detections,
    };
  }

  function createCalibrationPayload(meanPose, sourceTimeRange) {
    const capturedAt = createTimestampInfo();
    return {
      type: "initial_calibration",
      tag_id: constants.CALIBRATION_TAG_ID,
      sample_count: constants.CALIBRATION_SAMPLE_COUNT,
      captured_at: capturedAt.wallTimeIso,
      client_clock_offset_ms: capturedAt.clockOffsetMs,
      client_clock_rtt_ms: capturedAt.clockRttMs,
      frame_size: {
        width: dom.video.videoWidth,
        height: dom.video.videoHeight,
      },
      source_sample_time_range: sourceTimeRange,
      mean_pose: meanPose,
    };
  }

  function createDetectionStatePayload(active) {
    const sendTimestamp = createTimestampInfo();
    return {
      type: "detection_state",
      active,
      client_send_time: sendTimestamp.wallTimeIso,
      client_clock_offset_ms: sendTimestamp.clockOffsetMs,
      client_clock_rtt_ms: sendTimestamp.clockRttMs,
      nominal_frame_rate: active ? ns.getCurrentVideoSettings()?.frameRate ?? null : null,
      frame_size: active ? {
        width: dom.video.videoWidth,
        height: dom.video.videoHeight,
      } : null,
    };
  }

  transport.createTimestampInfo = createTimestampInfo;
  transport.createApriltagPayload = createApriltagPayload;
  transport.createCalibrationPayload = createCalibrationPayload;
  transport.createDetectionStatePayload = createDetectionStatePayload;
})(window.CameraPage = window.CameraPage || {});
