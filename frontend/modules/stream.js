(function initCameraDetection(ns) {
  const { dom, state } = ns;

  function canvasFromVideoFrame() {
    if (!state.frameCanvas) {
      state.frameCanvas = document.createElement("canvas");
      state.frameContext = state.frameCanvas.getContext("2d", { willReadFrequently: true });
    }

    if (
      state.frameCanvas.width !== dom.video.videoWidth ||
      state.frameCanvas.height !== dom.video.videoHeight
    ) {
      state.frameCanvas.width = dom.video.videoWidth;
      state.frameCanvas.height = dom.video.videoHeight;
    }

    state.frameContext.drawImage(dom.video, 0, 0, state.frameCanvas.width, state.frameCanvas.height);
    return { canvas: state.frameCanvas, context: state.frameContext };
  }

  function grayscaleFromImageData(imageData) {
    const pixels = imageData.data;
    const grayscalePixels = new Uint8Array(imageData.width * imageData.height);

    for (let pixelIndex = 0, grayIndex = 0; pixelIndex < pixels.length; pixelIndex += 4, grayIndex += 1) {
      grayscalePixels[grayIndex] = Math.round(
        (pixels[pixelIndex] + pixels[pixelIndex + 1] + pixels[pixelIndex + 2]) / 3
      );
    }

    return grayscalePixels;
  }

  async function runDetectionFrame() {
    const { canvas, context } = canvasFromVideoFrame();
    const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
    const grayscalePixels = grayscaleFromImageData(imageData);
    return state.apriltagDetector.detect(grayscalePixels, canvas.width, canvas.height);
  }

  function toTagCameraDetection(detection) {
    if (!detection.pose || !detection.pose.t || !detection.pose.R) {
      return detection;
    }

    return {
      ...detection,
      pose: ns.math.invertPose(detection.pose),
      // pose: detection.pose,
      pose_frame: "tag_camera",
    };
  }

  function toTagCameraDetections(detections) {
    return detections.map((detection) => toTagCameraDetection(detection));
  }

  ns.detection = {
    canvasFromVideoFrame,
    grayscaleFromImageData,
    runDetectionFrame,
    toTagCameraDetections,
  };
})(window.CameraPage = window.CameraPage || {});

(function initCameraStream(ns) {
  const { dom, state, constants } = ns;

  function getOverlayContext() {
    if (!dom.overlayCanvas) {
      return null;
    }

    if (!state.overlayContext) {
      state.overlayContext = dom.overlayCanvas.getContext("2d");
    }

    return state.overlayContext;
  }

  function syncOverlayCanvasSize() {
    const context = getOverlayContext();
    if (!context || !dom.previewStage) {
      return null;
    }

    const pixelRatio = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(dom.previewStage.clientWidth * pixelRatio));
    const height = Math.max(1, Math.round(dom.previewStage.clientHeight * pixelRatio));
    if (dom.overlayCanvas.width !== width || dom.overlayCanvas.height !== height) {
      dom.overlayCanvas.width = width;
      dom.overlayCanvas.height = height;
    }

    context.setTransform(1, 0, 0, 1, 0, 0);
    context.scale(pixelRatio, pixelRatio);
    return context;
  }

  function clearDetectionOverlay() {
    const context = syncOverlayCanvasSize();
    if (!context || !dom.previewStage) {
      return;
    }

    context.clearRect(0, 0, dom.previewStage.clientWidth, dom.previewStage.clientHeight);
  }

  function mapVideoPointToOverlay(point) {
    const stageWidth = dom.previewStage?.clientWidth || 0;
    const stageHeight = dom.previewStage?.clientHeight || 0;
    const videoWidth = dom.video.videoWidth || 0;
    const videoHeight = dom.video.videoHeight || 0;

    if (!stageWidth || !stageHeight || !videoWidth || !videoHeight) {
      return { x: 0, y: 0 };
    }

    const scale = Math.max(stageWidth / videoWidth, stageHeight / videoHeight);
    const renderedWidth = videoWidth * scale;
    const renderedHeight = videoHeight * scale;
    const offsetX = (stageWidth - renderedWidth) / 2;
    const offsetY = (stageHeight - renderedHeight) / 2;

    return {
      x: point.x * scale + offsetX,
      y: point.y * scale + offsetY,
    };
  }

  function formatDetectionLines(detection) {
    if (!detection.pose || !Array.isArray(detection.pose.t) || detection.pose.t.length < 3) {
      return [`ID ${detection.id}`];
    }

    const [tx, ty, tz] = detection.pose.t;
    if (![tx, ty, tz].every((value) => Number.isFinite(value))) {
      return [`ID ${detection.id}`];
    }

    const distance = Math.sqrt(tx * tx + ty * ty + tz * tz);
    return [`${distance.toFixed(3)} m`];
  }

  function drawDetectionLabel(context, lines, x, y) {
    context.font = "600 14px sans-serif";
    const paddingX = 8;
    const paddingY = 5;
    const lineHeight = 16;
    const textWidth = lines.reduce((maxWidth, line) => {
      return Math.max(maxWidth, context.measureText(line).width);
    }, 0);
    const textHeight = lineHeight * lines.length;
    const boxX = Math.max(0, x);
    const boxY = Math.max(0, y - textHeight - paddingY * 2 - 8);

    context.fillStyle = "rgba(0, 0, 0, 0.72)";
    context.fillRect(boxX, boxY, textWidth + paddingX * 2, textHeight + paddingY * 2);
    context.fillStyle = "#ffffff";
    lines.forEach((line, index) => {
      context.fillText(line, boxX + paddingX, boxY + paddingY + index * lineHeight);
    });
  }

  function renderDetectionOverlay(detections) {
    const context = syncOverlayCanvasSize();
    if (!context || !dom.previewStage) {
      return;
    }

    context.clearRect(0, 0, dom.previewStage.clientWidth, dom.previewStage.clientHeight);
    if (!Array.isArray(detections) || !detections.length) {
      return;
    }

    context.lineWidth = 2;
    context.strokeStyle = "#22c55e";
    context.fillStyle = "#22c55e";
    context.textBaseline = "top";

    detections.forEach((detection) => {
      if (!Array.isArray(detection.corners) || detection.corners.length !== 4) {
        return;
      }

      const overlayCorners = detection.corners.map((corner) => mapVideoPointToOverlay(corner));
      context.beginPath();
      context.moveTo(overlayCorners[0].x, overlayCorners[0].y);
      for (let index = 1; index < overlayCorners.length; index += 1) {
        context.lineTo(overlayCorners[index].x, overlayCorners[index].y);
      }
      context.closePath();
      context.stroke();

      overlayCorners.forEach((corner) => {
        context.beginPath();
        context.arc(corner.x, corner.y, 3, 0, Math.PI * 2);
        context.fill();
      });

      const labelCorner = overlayCorners.reduce((best, current) => {
        if (!best) {
          return current;
        }
        return current.y < best.y || (current.y === best.y && current.x < best.x) ? current : best;
      }, null);
      drawDetectionLabel(context, formatDetectionLines(detection), labelCorner.x, labelCorner.y);
    });
  }

  async function warmupCameraDependencies(stream) {
    try {
      await state.apriltagDetector.init();

      if (state.stream !== stream || dom.video.srcObject !== stream) {
        return;
      }

      ns.intrinsics.configurePoseEstimation();
      ns.intrinsics.configureTagSizes();
    } catch (error) {
      console.warn("Failed to warm up detector:", error);
    }

    try {
      await ns.transport.ensureRealtimeChannel();
    } catch (error) {
      console.warn("Failed to connect realtime channel:", error);
    }
  }

  async function notifyDetectionState(active) {
    try {
      await ns.transport.sendDetectionState(active);
    } catch (error) {
      console.warn("Failed to send detection_state:", error);
    }
  }

  function resetLatestDetectionState() {
    state.latestDetectionPacket = null;
    state.lastSentDetectionPacketVersion = 0;
  }

  function publishLatestDetectionPacket(detections, timings) {
    state.latestDetectionPacket = {
      version: state.nextDetectionPacketVersion,
      detections,
      timings,
    };
    state.nextDetectionPacketVersion += 1;
  }

  async function runDetectionLoop() {
    while (state.detectionLoopActive && state.stream) {
      const loopStartMs = Date.now();
      const detectTagStart = ns.transport.createTimestampInfo();
      const detections = await ns.detection.runDetectionFrame();
      renderDetectionOverlay(detections);
      const detectTagEnd = ns.transport.createTimestampInfo();
      publishLatestDetectionPacket(ns.detection.toTagCameraDetections(detections), {
        detectTagStartTime: detectTagStart.wallTimeIso,
        detectTagEndTime: detectTagEnd.wallTimeIso,
      });

      const elapsedLoopMs = Date.now() - loopStartMs;
      await ns.sleep(Math.max(constants.DETECTION_SEND_INTERVAL_MS - elapsedLoopMs, 0));
    }
  }

  async function runDetectionSendLoop() {
    while (state.detectionLoopActive && state.stream) {
      const packet = state.latestDetectionPacket;
      if (!packet || packet.version <= state.lastSentDetectionPacketVersion) {
        await ns.sleep(4);
        continue;
      }

      const payloadSent = await ns.transport.sendApriltagPayload(packet.detections, packet.timings);
      if (payloadSent) {
        state.lastSentDetectionPacketVersion = packet.version;
        continue;
      }

      await ns.sleep(constants.DETECTION_BACKPRESSURE_DELAY_MS);
    }
  }

  async function startContinuousDetection() {
    if (state.detectionLoopActive) {
      return;
    }

    if (!state.stream || !dom.video.videoWidth || !dom.video.videoHeight) {
      return;
    }

    if (!state.deviceHasCameraCalibration) {
      ns.setCameraUI(true);
      return;
    }

    state.detectionLoopActive = true;
    resetLatestDetectionState();
    ns.setCameraUI(true);

    try {
      await state.apriltagDetector.init();
      await notifyDetectionState(true);
      await Promise.all([runDetectionLoop(), runDetectionSendLoop()]);
    } catch (error) {
      console.warn("Continuous detection failed:", error);
    } finally {
      clearDetectionOverlay();
      resetLatestDetectionState();
      await notifyDetectionState(false);
      state.detectionLoopActive = false;
      ns.setCameraUI(Boolean(state.stream));
    }
  }

  function stopContinuousDetection() {
    if (!state.detectionLoopActive) {
      clearDetectionOverlay();
      resetLatestDetectionState();
      return;
    }

    state.detectionLoopActive = false;
    clearDetectionOverlay();
    resetLatestDetectionState();
    ns.setCameraUI(Boolean(state.stream));
  }

  function toggleDetection() {
    if (state.detectionLoopActive) {
      stopContinuousDetection();
      return;
    }

    startContinuousDetection();
  }

  async function openCamera() {
    if (!window.isSecureContext) {
      return;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return;
    }

    try {
      state.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { exact: "environment" } },
        audio: false,
      });
    } catch (_primaryError) {
      try {
        state.stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment" },
          audio: false,
        });
      } catch (_error) {
        return;
      }
    }

    dom.video.srcObject = state.stream;
    if (!dom.video.videoWidth || !dom.video.videoHeight) {
      await new Promise((resolve) => {
        if (dom.video.readyState >= 1) {
          resolve();
          return;
        }

        dom.video.addEventListener("loadedmetadata", resolve, { once: true });
      });
    }

    try {
      await dom.video.play();
    } catch (error) {
      if (error?.name !== "AbortError") {
        throw error;
      }

      if (dom.video.srcObject !== state.stream) {
        return;
      }
    }

    const openedStream = state.stream;
    ns.calibration.resetTimeSyncState();
    try {
      const deviceProfile = await ns.intrinsics.syncCalibrationFromBackend();
      ns.calibration.setDeviceCalibrationState(deviceProfile);
    } catch (error) {
      state.deviceProfile = null;
      state.deviceHasCameraCalibration = false;
      console.warn("Failed to load device calibration profile:", error);
    }
    if (state.deviceHasCameraCalibration) {
      ns.intrinsics.configurePoseEstimation();
    }
    ns.setCameraUI(true);
    ns.keepPreviewInView();
    void warmupCameraDependencies(openedStream);
  }

  function closeCamera() {
    stopContinuousDetection();

    if (state.stream) {
      state.stream.getTracks().forEach((track) => track.stop());
      state.stream = null;
    }

    dom.video.srcObject = null;
    clearDetectionOverlay();
    ns.calibration.resetCameraCalibrationFrames();
    ns.calibration.resetTimeSyncState();
    state.deviceProfile = null;
    state.deviceHasCameraCalibration = false;
    ns.setCameraUI(false);
    ns.transport.closeRealtimeConnection();
    ns.transport.closeApriltagSocket();
    ns.transport.closeCalibrationSocket();
    ns.transport.closeTimeSyncSocket();
  }

  function toggleCamera() {
    if (state.stream) {
      closeCamera();
      return;
    }

    openCamera();
  }

  function bindEvents() {
    dom.openCameraBtn.addEventListener("click", toggleCamera);
    dom.detectTagBtn.addEventListener("click", toggleDetection);
    dom.timeSyncBtn.addEventListener("click", ns.calibration.runTimeSync);
    dom.calibrateBtn.addEventListener("click", ns.calibration.runInitialCalibration);
    dom.cameraCalibrationBtn.addEventListener("click", ns.calibration.toggleCameraCalibrationMode);
    dom.previewCaptureCalibrationBtn?.addEventListener("click", ns.calibration.captureCalibrationFrameAction);
    dom.previewUploadCalibrationBtn?.addEventListener("click", ns.calibration.uploadCalibrationFrames);
    window.addEventListener("beforeunload", () => {
      closeCamera();
      ns.gripper?.dispose?.();
      state.apriltagDetector.destroy();
    });
  }

  function bootstrap() {
    ns.calibration.resetCameraCalibrationFrames();
    ns.calibration.resetTimeSyncState();
    ns.setCameraUI(false);
    bindEvents();
    ns.gripper?.initialize?.();
    state.apriltagDetector
      .init()
      .then(() => {})
      .catch((error) => {
        console.warn("Failed to initialize detector:", error);
      });
  }

  ns.app = {
    bootstrap,
  };
  ns.previewOverlay = {
    clear: clearDetectionOverlay,
    render: renderDetectionOverlay,
  };
})(window.CameraPage = window.CameraPage || {});
