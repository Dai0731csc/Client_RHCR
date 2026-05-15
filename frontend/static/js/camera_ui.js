(function initCameraUI(ns) {
  const { dom, state, constants } = ns;

  function iconSvg(name) {
    const icons = {
      camera:
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 8h3l2-2h6l2 2h3v10H4z"></path><circle cx="12" cy="13" r="3.5"></circle></svg>',
      cameraOff:
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 8h3l2-2h6l2 2h3v10H4z"></path><circle cx="12" cy="13" r="3.5"></circle><path d="M5 5l14 14"></path></svg>',
      play:
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 7v10l8-5z"></path></svg>',
      stop:
        '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="1.5"></rect></svg>',
      target:
        '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="5"></circle><path d="M12 3v3"></path><path d="M12 18v3"></path><path d="M3 12h3"></path><path d="M18 12h3"></path></svg>',
      capture:
        '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="7"></circle><circle cx="12" cy="12" r="3"></circle></svg>',
      upload:
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V7"></path><path d="m8.5 10.5 3.5-3.5 3.5 3.5"></path><path d="M6 18h12"></path></svg>',
      calibrate:
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 8V4h4"></path><path d="M16 4h4v4"></path><path d="M20 16v4h-4"></path><path d="M8 20H4v-4"></path><circle cx="12" cy="12" r="2.5"></circle></svg>',
      sync:
        '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8"></circle><path d="M12 8v4l2.5 2.5"></path></svg>',
      gripperOpen:
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4v16"></path><path d="M17 4v16"></path><path d="M7 8h3"></path><path d="M14 8h3"></path><path d="M10 12h4"></path><path d="M7 16h3"></path><path d="M14 16h3"></path></svg>',
      gripperClose:
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4v16"></path><path d="M15 4v16"></path><path d="M9 8h2"></path><path d="M13 8h2"></path><path d="M11 12h2"></path><path d="M9 16h2"></path><path d="M13 16h2"></path></svg>',
    };
    return icons[name] || icons.camera;
  }

  function setButtonVisual(button, iconName, label, busy = false) {
    if (!button) {
      return;
    }

    button.innerHTML = `<span class="button-icon" aria-hidden="true">${iconSvg(iconName)}</span><span class="sr-only">${label}</span>`;
    button.setAttribute("aria-label", label);
    button.title = label;
    button.classList.toggle("is-busy", busy);
  }

  function updateCalibrationProgress() {
    const count = state.calibrationFrames.length;
    const target = constants.CAMERA_CALIBRATION_TARGET_COUNT;
    const ratio = target ? Math.min(1, count / target) : 0;
    const isVisible = state.cameraCalibrationMode || count > 0;
    const text = isVisible ? `${count} / ${target}` : "";
    if (dom.previewCalibrationCounter) {
      dom.previewCalibrationCounter.textContent = text;
    }
    if (dom.previewCalibrationProgressBar) {
      dom.previewCalibrationProgressBar.style.width = isVisible ? `${Math.round(ratio * 100)}%` : "0";
    }
    if (dom.previewStage) {
      dom.previewStage.classList.toggle("is-calibrating", isVisible);
    }
  }

  function keepPreviewInView() {
    if (!dom.previewPanel || !window.matchMedia("(max-width: 1080px)").matches) {
      return;
    }

    dom.previewPanel.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  function setCameraCalibrationUI() {
    const hasStream = Boolean(state.stream);
    const readyToUpload = state.calibrationFrames.length >= constants.CAMERA_CALIBRATION_TARGET_COUNT;
    const canToggleMode =
      (hasStream || state.cameraCalibrationMode) &&
      !state.calibrationInProgress &&
      !state.timeSyncInProgress &&
      !state.cameraCalibrationUploadInProgress &&
      !state.cameraCalibrationActionInProgress;
    const canCapture =
      hasStream &&
      state.cameraCalibrationMode &&
      !state.calibrationInProgress &&
      !state.timeSyncInProgress &&
      !state.cameraCalibrationUploadInProgress &&
      !state.cameraCalibrationActionInProgress;
    const canUpload =
      hasStream &&
      state.cameraCalibrationMode &&
      readyToUpload &&
      !state.calibrationInProgress &&
      !state.timeSyncInProgress &&
      !state.cameraCalibrationUploadInProgress &&
      !state.cameraCalibrationActionInProgress;

    dom.cameraCalibrationBtn.disabled = !canToggleMode;
    if (state.cameraCalibrationUploadInProgress) {
      setButtonVisual(dom.cameraCalibrationBtn, "stop", "Exit camera calibration", true);
    } else if (!state.cameraCalibrationMode) {
      setButtonVisual(dom.cameraCalibrationBtn, "calibrate", "Enter camera calibration");
    } else {
      setButtonVisual(dom.cameraCalibrationBtn, "stop", "Exit camera calibration");
    }

    if (dom.previewCaptureCalibrationBtn) {
      dom.previewCaptureCalibrationBtn.hidden = !state.cameraCalibrationMode;
      dom.previewCaptureCalibrationBtn.disabled = !canCapture;
      setButtonVisual(
        dom.previewCaptureCalibrationBtn,
        "capture",
        `Capture chessboard frame (${state.calibrationFrames.length}/${constants.CAMERA_CALIBRATION_TARGET_COUNT})`,
        state.cameraCalibrationActionInProgress
      );
    }

    if (dom.previewUploadCalibrationBtn) {
      dom.previewUploadCalibrationBtn.hidden = !(state.cameraCalibrationMode && readyToUpload);
      dom.previewUploadCalibrationBtn.disabled = !canUpload;
      setButtonVisual(dom.previewUploadCalibrationBtn, "upload", "Upload chessboard frames and compute intrinsics", state.cameraCalibrationUploadInProgress);
    }

    updateCalibrationProgress();
  }

  function setGripperUI() {
    if (!dom.gripperToggleBtn) {
      return;
    }

    dom.gripperToggleBtn.disabled = state.gripperBusy;
    setButtonVisual(
      dom.gripperToggleBtn,
      state.gripperState === "open" ? "gripperClose" : "gripperOpen",
      state.gripperBusy
        ? state.gripperState === "open"
          ? "Closing gripper..."
          : "Opening gripper..."
        : state.gripperState === "open"
          ? "Close gripper"
          : "Open gripper",
      state.gripperBusy
    );
  }

  function setCameraUI(opened) {
    const busy = state.calibrationInProgress || state.timeSyncInProgress;
    const hasTimeSync = Boolean(state.lastTimeSyncResult);

    dom.openCameraBtn.disabled = busy;
    setButtonVisual(dom.openCameraBtn, opened ? "cameraOff" : "camera", opened ? "Close camera" : "Open rear camera");
    dom.detectTagBtn.disabled = !opened || busy;
    dom.timeSyncBtn.disabled = !opened || busy;
    dom.calibrateBtn.disabled = !opened || busy || !hasTimeSync;
    setButtonVisual(
      dom.detectTagBtn,
      state.detectionLoopActive ? "stop" : "play",
      state.detectionLoopActive ? "Stop continuous detection" : "Start continuous detection"
    );
    setButtonVisual(
      dom.timeSyncBtn,
      "sync",
      state.timeSyncInProgress ? "Time sync in progress..." : hasTimeSync ? "Re-run time sync" : "Time sync",
      state.timeSyncInProgress
    );
    setButtonVisual(
      dom.calibrateBtn,
      "target",
      state.calibrationInProgress ? "Initial calibration in progress..." : hasTimeSync ? "Initial calibration" : "Initial calibration (run time sync first)",
      state.calibrationInProgress
    );

    setCameraCalibrationUI();
    setGripperUI();
  }

  function setCalibrationUI(isRunning) {
    state.calibrationInProgress = isRunning;
    setCameraUI(Boolean(state.stream));
  }

  function setTimeSyncUI(isRunning) {
    state.timeSyncInProgress = isRunning;
    setCameraUI(Boolean(state.stream));
  }

  ns.keepPreviewInView = keepPreviewInView;
  ns.setCameraCalibrationUI = setCameraCalibrationUI;
  ns.setGripperUI = setGripperUI;
  ns.setCameraUI = setCameraUI;
  ns.setCalibrationUI = setCalibrationUI;
  ns.setTimeSyncUI = setTimeSyncUI;
})(window.CameraPage = window.CameraPage || {});
