(function initCameraCalibration(ns) {
  const { dom, state, constants } = ns;

  function clearCameraCalibrationSession() {
    state.calibrationFrames = [];
    state.cameraCalibrationMode = false;
    state.cameraCalibrationUploadInProgress = false;
    state.cameraCalibrationActionInProgress = false;
    ns.setCameraCalibrationUI();
  }

  function resetCameraCalibrationFrames() {
    clearCameraCalibrationSession();
  }

  function resetTimeSyncState() {
    state.timeSyncInProgress = false;
    state.lastTimeSyncResult = null;
    ns.setCameraUI(Boolean(state.stream));
  }

  async function captureCanvasBlob(canvas) {
    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (!blob) {
          reject(new Error("Failed to encode calibration frame"));
          return;
        }
        resolve(blob);
      }, "image/jpeg", 0.9);
    });
  }

  function buildCameraCalibrationMetadata() {
    return {
      board_type: constants.CAMERA_CALIBRATION_BOARD_TYPE,
      board_rows: constants.CAMERA_CALIBRATION_BOARD_ROWS,
      board_cols: constants.CAMERA_CALIBRATION_BOARD_COLS,
      square_size_mm: constants.CAMERA_CALIBRATION_SQUARE_SIZE_MM,
      image_width: dom.video.videoWidth,
      image_height: dom.video.videoHeight,
      camera_settings: ns.getCurrentVideoSettings(),
      frames: state.calibrationFrames.map((frame) => ({
        filename: frame.file.name,
      })),
    };
  }

  async function captureCalibrationFrame() {
    if (!state.cameraCalibrationMode) {
      return;
    }

    if (!state.stream || !dom.video.videoWidth || !dom.video.videoHeight) {
      return;
    }

    try {
      const { canvas } = ns.detection.canvasFromVideoFrame();
      const blob = await captureCanvasBlob(canvas);
      const validation = await ns.transport.validateCalibrationFrame(blob, buildCameraCalibrationMetadata());
      if (!validation.valid) {
        console.info("Chessboard not found in calibration frame");
        return;
      }
      const index = state.calibrationFrames.length;
      const filename = `calibration_${String(index + 1).padStart(2, "0")}.jpg`;
      state.calibrationFrames.push({
        file: new File([blob], filename, { type: "image/jpeg" }),
      });
      ns.setCameraCalibrationUI();
    } catch (_error) {
      return;
    }
  }

  async function captureCalibrationFrameAction() {
    if (state.cameraCalibrationActionInProgress || state.cameraCalibrationUploadInProgress) {
      return;
    }

    if (!state.cameraCalibrationMode || !state.stream) {
      return;
    }

    state.cameraCalibrationActionInProgress = true;
    ns.setCameraCalibrationUI();

    try {
      await captureCalibrationFrame();
    } finally {
      state.cameraCalibrationActionInProgress = false;
      ns.setCameraCalibrationUI();
    }
  }

  function toggleCameraCalibrationMode() {
    if (state.cameraCalibrationActionInProgress || state.cameraCalibrationUploadInProgress || state.calibrationInProgress) {
      return;
    }

    if (!state.cameraCalibrationMode) {
      if (!state.stream) {
        return;
      }

      state.cameraCalibrationMode = true;
      state.calibrationFrames = [];
      ns.keepPreviewInView();
      ns.setCameraCalibrationUI();
      return;
    }

    clearCameraCalibrationSession();
  }

  async function uploadCalibrationFrames() {
    if (!state.cameraCalibrationMode || !state.calibrationFrames.length) {
      return;
    }

    state.cameraCalibrationUploadInProgress = true;
    ns.setCameraCalibrationUI();

    try {
      const metadata = buildCameraCalibrationMetadata();
      const rawResult = await ns.transport.uploadCameraCalibration(state.calibrationFrames, metadata);
      const result = ns.intrinsics.parseCalibrationResult(rawResult);

      ns.intrinsics.saveCalibrationResult(result);
      ns.intrinsics.configurePoseEstimation();
      clearCameraCalibrationSession();
    } catch (error) {
      console.warn("Camera calibration upload failed:", error);
    } finally {
      if (state.cameraCalibrationUploadInProgress) {
        state.cameraCalibrationUploadInProgress = false;
      }
      ns.setCameraCalibrationUI();
    }
  }

  function pickCalibrationDetection(detections) {
    return detections.find((detection) => {
      return (
        detection.id === constants.CALIBRATION_TAG_ID &&
        detection.pose &&
        detection.pose.t &&
        detection.pose.R
      );
    });
  }

  async function runTimeSync() {
    if (state.timeSyncInProgress || state.calibrationInProgress) {
      return;
    }

    if (!state.stream || !dom.video.videoWidth || !dom.video.videoHeight) {
      return;
    }

    ns.setTimeSyncUI(true);

    try {
      const syncResult = await ns.transport.syncClock();
      state.lastTimeSyncResult = {
        ...syncResult,
        completedAt: new Date().toISOString(),
      };
      void ns.transport.reportTimeSyncResult({
        status: "success",
        sample_count: syncResult.sampleCount,
        offset_ms: syncResult.offsetMs,
        rtt_ms: syncResult.rttMs,
        transport: syncResult.transportLabel || "unknown",
        completed_at: state.lastTimeSyncResult.completedAt,
      });
      console.info("Time sync completed:", syncResult);
    } catch (error) {
      state.lastTimeSyncResult = null;
      void ns.transport.reportTimeSyncResult({
        status: "failed",
        transport: state.realtimeDataChannel?.readyState === "open" ? "webrtc:apriltag" : "websocket:apriltag",
        message: error?.message || String(error),
        completed_at: new Date().toISOString(),
      }).catch(() => {});
      console.warn("Time sync failed:", error);
    } finally {
      ns.setTimeSyncUI(false);
      ns.setCameraUI(Boolean(state.stream));
    }
  }

  async function runInitialCalibration() {
    if (state.calibrationInProgress) {
      return;
    }

    if (!state.stream || !dom.video.videoWidth || !dom.video.videoHeight) {
      return;
    }

    if (!state.lastTimeSyncResult) {
      ns.setCameraUI(Boolean(state.stream));
      return;
    }

    ns.setCalibrationUI(true);

    const samples = [];
    const sampleTimestamps = [];
    let attempts = 0;

    try {
      await state.apriltagDetector.init();
      await ns.transport.prepareInitialCalibration();
      await ns.sleep(800);

      const startTime = Date.now();

      while (
        samples.length < constants.CALIBRATION_SAMPLE_COUNT &&
        attempts < constants.CALIBRATION_MAX_ATTEMPTS &&
        Date.now() - startTime < constants.CALIBRATION_MAX_DURATION_MS
      ) {
        attempts += 1;
        const detections = await ns.detection.runDetectionFrame();
        const detection = pickCalibrationDetection(detections);
        ns.previewOverlay?.render(detection ? [detection] : []);

        if (detection) {
          samples.push(detection);
          sampleTimestamps.push(new Date().toISOString());
          ns.setCalibrationUI(true);
        }

        await ns.sleep(constants.CALIBRATION_FRAME_DELAY_MS);
      }

      if (samples.length < constants.CALIBRATION_SAMPLE_COUNT) {
        throw new Error(
          `Calibration timed out: collected ${samples.length}/${constants.CALIBRATION_SAMPLE_COUNT} valid frames`
        );
      }

      const tagCameraSamples = samples.map((sample) => ns.math.invertPose(sample.pose));
      // const tagCameraSamples = samples.map((sample) => sample.pose);
      const meanPose = {
        t: ns.math.averageTranslations(tagCameraSamples.map((sample) => sample.t)),
        R: ns.math.averageRotations(tagCameraSamples.map((sample) => sample.R)),
      };
      await ns.transport.sendInitialCalibration(meanPose, {
        start: sampleTimestamps[0],
        end: sampleTimestamps[sampleTimestamps.length - 1],
      });
    } catch (error) {
      console.warn("Initial calibration failed:", error);
    } finally {
      ns.previewOverlay?.clear();
      ns.setCalibrationUI(false);
      ns.setCameraUI(Boolean(state.stream));
    }
  }

  ns.calibration = {
    resetCameraCalibrationFrames,
    resetTimeSyncState,
    captureCalibrationFrameAction,
    uploadCalibrationFrames,
    toggleCameraCalibrationMode,
    runTimeSync,
    runInitialCalibration,
  };
})(window.CameraPage = window.CameraPage || {});
