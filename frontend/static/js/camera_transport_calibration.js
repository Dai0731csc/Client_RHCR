(function initCameraTransportCalibration(ns) {
  const { state, constants } = ns;
  const transport = ns.transport || (ns.transport = {});

  async function validateCalibrationFrame(blob, metadata) {
    const formData = new FormData();
    formData.append("metadata", JSON.stringify(metadata));
    formData.append("image", blob, "validation.jpg");

    const response = await fetch(constants.CAMERA_CALIBRATION_VALIDATE_API_PATH, {
      method: "POST",
      body: formData,
    });
    const result = await response.json();

    if (!response.ok || !result.success) {
      throw new Error(result.message || result.error || `Validation request failed with ${response.status}`);
    }

    return result;
  }

  async function uploadCameraCalibration(frames, metadata) {
    const formData = new FormData();
    formData.append("metadata", JSON.stringify(metadata));
    frames.forEach((frame) => {
      formData.append("images", frame.file, frame.file.name);
    });

    const response = await fetch(constants.CAMERA_CALIBRATION_API_PATH, {
      method: "POST",
      body: formData,
    });
    const result = await response.json();

    if (!response.ok || !result.success) {
      throw new Error(result.message || result.error || `Calibration request failed with ${response.status}`);
    }

    return result;
  }

  async function prepareInitialCalibration() {
    await transport.ensureCalibrationSocket();
  }

  async function sendInitialCalibration(meanPose, sourceTimeRange) {
    const payload = transport.createCalibrationPayload(meanPose, sourceTimeRange);
    await transport.sendCalibrationPayload(payload);
  }

  transport.validateCalibrationFrame = validateCalibrationFrame;
  transport.uploadCameraCalibration = uploadCameraCalibration;
  transport.prepareInitialCalibration = prepareInitialCalibration;
  transport.sendInitialCalibration = sendInitialCalibration;
})(window.CameraPage = window.CameraPage || {});
