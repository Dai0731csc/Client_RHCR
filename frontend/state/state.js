(function initCameraState(ns) {
  const basePath = (window.CameraPageConfig && window.CameraPageConfig.basePath) || "";
  const withBasePath = window.SharedBasePath.createWithBasePath(basePath);

  const dom = {
    video: document.getElementById("video"),
    overlayCanvas: document.getElementById("overlayCanvas"),
    previewPanel: document.getElementById("previewPanel"),
    previewStage: document.getElementById("previewStage"),
    openCameraBtn: document.getElementById("openCameraBtn"),
    detectTagBtn: document.getElementById("detectTagBtn"),
    timeSyncBtn: document.getElementById("timeSyncBtn"),
    calibrateBtn: document.getElementById("calibrateBtn"),
    cameraCalibrationBtn: document.getElementById("cameraCalibrationBtn"),
    gripperToggleBtn: document.getElementById("gripperToggleBtn"),
    previewCalibrationCounter: document.getElementById("previewCalibrationCounter"),
    previewCalibrationProgressBar: document.getElementById("previewCalibrationProgressBar"),
    previewCaptureCalibrationBtn: document.getElementById("previewCaptureCalibrationBtn"),
    previewUploadCalibrationBtn: document.getElementById("previewUploadCalibrationBtn"),
  };

  const state = {
    stream: null,
    detectionLoopActive: false,
    apriltagSocket: null,
    apriltagSocketReady: null,
    realtimeSignalingSocket: null,
    realtimeSignalingSocketReady: null,
    realtimePeerConnection: null,
    realtimeDataChannel: null,
    realtimeChannelReady: null,
    pendingRealtimeAnswer: null,
    webrtcConfig: null,
    calibrationSocket: null,
    calibrationSocketReady: null,
    timeSyncInProgress: false,
    lastTimeSyncResult: null,
    webrtcFailureCount: 0,
    webrtcRetryAtMs: 0,
    lastWebRTCFailureMessage: "",
    calibrationInProgress: false,
    cameraCalibrationMode: false,
    cameraCalibrationUploadInProgress: false,
    cameraCalibrationActionInProgress: false,
    calibrationFrames: [],
    frameCanvas: null,
    frameContext: null,
    overlayContext: null,
    currentIntrinsicsRecord: null,
    deviceProfile: null,
    deviceHasCameraCalibration: false,
    latestDetectionPacket: null,
    nextDetectionPacketVersion: 1,
    lastSentDetectionPacketVersion: 0,
    gripperState: "closed",
    gripperBusy: false,
    gripperLastError: "",
    apriltagDetector: new ApriltagDetector(),
    timeSyncClient: window.SharedTimeSync.createTimeSyncClient(),
  };

  const constants = {
    DEFAULT_TAG_SIZE_METERS: 0.075,
    MAX_CONFIGURED_TAG_ID: 255,
    MAX_REALTIME_BUFFERED_BYTES: 16384,
    MAX_WS_BUFFERED_BYTES: 16384,
    CALIBRATION_TAG_ID: 0,
    CALIBRATION_SAMPLE_COUNT: 20,
    CALIBRATION_MAX_ATTEMPTS: 60,
    CALIBRATION_MAX_DURATION_MS: 10000,
    CALIBRATION_FRAME_DELAY_MS: 120,
    DETECTION_BACKPRESSURE_DELAY_MS: 10,
    /** Camera max ~30 fps; detection + server control_hz follow this. */
    CAMERA_TARGET_FRAME_RATE: 30,
    CAMERA_INTRINSICS_STORAGE_KEY: "camera_intrinsics_by_mode_v1",
    CAMERA_CALIBRATION_TARGET_COUNT: 15,
    CAMERA_CALIBRATION_BOARD_TYPE: "chessboard",
    CAMERA_CALIBRATION_BOARD_ROWS: 6,
    CAMERA_CALIBRATION_BOARD_COLS: 9,
    CAMERA_CALIBRATION_SQUARE_SIZE_MM: 20.0,
    TIME_SYNC_SAMPLE_COUNT: 20,
    TIME_SYNC_SLEEP_MS: 100,
    CAMERA_CALIBRATION_API_PATH: withBasePath("/api/camera-calibration"),
    CAMERA_CALIBRATION_VALIDATE_API_PATH: withBasePath("/api/camera-calibration/validate"),
    DEVICE_PROFILE_API_PATH: withBasePath("/api/device-profile"),
    WEBRTC_SIGNALING_API_PATH: withBasePath("/api/webrtc/config"),
    GRIPPER_COMMAND_API_PATH: withBasePath("/api/gripper/command"),
    WEBRTC_RETRY_INITIAL_DELAY_MS: 3000,
    WEBRTC_RETRY_MAX_DELAY_MS: 60000,
    FULL_CHAIN_TIME_SYNC_API_PATH: withBasePath("/api/time-sync/full-chain"),
  };

  function getCurrentVideoSettings() {
    return state.stream?.getVideoTracks?.()[0]?.getSettings?.() || {};
  }

  function sleep(ms) {
    return new Promise((resolve) => {
      window.setTimeout(resolve, ms);
    });
  }

  ns.dom = dom;
  ns.state = state;
  ns.constants = constants;
  ns.basePath = basePath;
  ns.withBasePath = withBasePath;
  ns.getCurrentVideoSettings = getCurrentVideoSettings;
  ns.sleep = sleep;
})(window.CameraPage = window.CameraPage || {});
