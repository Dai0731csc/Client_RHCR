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
      skewClientVsMasterMs: Number.isFinite(snapshot.offsetMs) ? snapshot.offsetMs : null,
      clockSyncRttClientMs: Number.isFinite(snapshot.rttMs) ? snapshot.rttMs : null,
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
      skew_client_vs_master_ms: sendTimestamp.skewClientVsMasterMs,
      clock_sync_rtt_client_ms: sendTimestamp.clockSyncRttClientMs,
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
