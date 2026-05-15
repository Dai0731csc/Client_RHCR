(function initCameraMath(ns) {
  const glMatrixNamespace = window.glMatrix || {};
  const mat3Api = window.mat3 || glMatrixNamespace.mat3 || null;
  const vec3Api = window.vec3 || glMatrixNamespace.vec3 || null;
  const quatApi = window.quat || glMatrixNamespace.quat || null;
  if (!mat3Api || !vec3Api || !quatApi) {
    throw new Error("gl-matrix is required for camera_pose.js");
  }

  function normalizeQuaternion(quaternion) {
    const normalized = quatApi.create();
    quatApi.normalize(normalized, quaternionWxyzToGlQuat(quaternion));
    return glQuatToQuaternionWxyz(normalized);
  }

  function rotationMatrixToMat3(rotationMatrix) {
    return mat3Api.fromValues(
      rotationMatrix[0][0],
      rotationMatrix[1][0],
      rotationMatrix[2][0],
      rotationMatrix[0][1],
      rotationMatrix[1][1],
      rotationMatrix[2][1],
      rotationMatrix[0][2],
      rotationMatrix[1][2],
      rotationMatrix[2][2]
    );
  }

  function mat3ToRotationMatrix(matrix) {
    return [
      [matrix[0], matrix[3], matrix[6]],
      [matrix[1], matrix[4], matrix[7]],
      [matrix[2], matrix[5], matrix[8]],
    ];
  }

  function quaternionWxyzToGlQuat(quaternion) {
    return quatApi.fromValues(quaternion[1], quaternion[2], quaternion[3], quaternion[0]);
  }

  function glQuatToQuaternionWxyz(quaternion) {
    return [quaternion[3], quaternion[0], quaternion[1], quaternion[2]];
  }

  function rotationMatrixToQuaternion(rotationMatrix) {
    const quaternion = quatApi.create();
    quatApi.fromMat3(quaternion, rotationMatrixToMat3(rotationMatrix));
    quatApi.normalize(quaternion, quaternion);
    return glQuatToQuaternionWxyz(quaternion);
  }

  function quaternionToRotationMatrix(quaternion) {
    const rotationMatrix = mat3Api.create();
    const normalizedQuaternion = quatApi.create();
    quatApi.normalize(normalizedQuaternion, quaternionWxyzToGlQuat(quaternion));
    mat3Api.fromQuat(rotationMatrix, normalizedQuaternion);
    return mat3ToRotationMatrix(rotationMatrix);
  }

  function transposeMatrix(matrix) {
    const transposed = mat3Api.create();
    mat3Api.transpose(transposed, rotationMatrixToMat3(matrix));
    return mat3ToRotationMatrix(transposed);
  }

  function multiplyMatrixVector(matrix, vector) {
    const transformedVector = vec3Api.create();
    vec3Api.transformMat3(transformedVector, vector, rotationMatrixToMat3(matrix));
    return Array.from(transformedVector);
  }

  function invertPose(pose) {
    const invertedRotation = transposeMatrix(pose.R);
    const invertedTranslation = multiplyMatrixVector(
      invertedRotation,
      pose.t.map((value) => -value)
    );

    return {
      t: invertedTranslation,
      R: invertedRotation,
    };
  }

  function averageTranslations(translations) {
    const sums = vec3Api.create();
    translations.forEach((translation) => {
      vec3Api.add(sums, sums, translation);
    });
    vec3Api.scale(sums, sums, 1 / translations.length);
    return Array.from(sums);
  }

  function averageRotations(rotationMatrices) {
    const quaternions = rotationMatrices.map((rotationMatrix) =>
      quaternionWxyzToGlQuat(rotationMatrixToQuaternion(rotationMatrix))
    );
    const reference = quaternions[0];
    const accumulator = quatApi.create();

    quaternions.forEach((quaternion) => {
      const aligned = quatApi.clone(quaternion);
      if (quatApi.dot(reference, aligned) < 0) {
        quatApi.scale(aligned, aligned, -1);
      }
      quatApi.add(accumulator, accumulator, aligned);
    });

    quatApi.scale(accumulator, accumulator, 1 / quaternions.length);
    quatApi.normalize(accumulator, accumulator);
    return quaternionToRotationMatrix(glQuatToQuaternionWxyz(accumulator));
  }

  ns.math = {
    invertPose,
    averageTranslations,
    averageRotations,
  };
})(window.CameraPage = window.CameraPage || {});

(function initCameraIntrinsics(ns) {
  const { dom, state, constants } = ns;
  const z = window.Zod;

  if (!z) {
    throw new Error("zod is required for camera_pose.js");
  }

  const finiteNumber = z.number().finite();
  const cameraSettingsSchema = z.record(z.unknown());
  const intrinsicsValuesSchema = z.object({
    fx: finiteNumber,
    fy: finiteNumber,
    cx: finiteNumber,
    cy: finiteNumber,
  });
  const intrinsicsRecordSchema = intrinsicsValuesSchema.extend({
    distCoeffs: z.array(finiteNumber).nullable().optional(),
    reprojectionError: finiteNumber.nullable().optional(),
    imageWidth: finiteNumber.nullable().optional(),
    imageHeight: finiteNumber.nullable().optional(),
    source: z.string().optional(),
    capturedAt: z.string().nullable().optional(),
    cameraSettings: cameraSettingsSchema.optional(),
  });
  const intrinsicsRecordMapSchema = z.record(intrinsicsRecordSchema);
  const calibrationResultSchema = z.object({
    success: z.literal(true),
    intrinsics: intrinsicsValuesSchema,
    dist_coeffs: z.array(finiteNumber).nullable().optional(),
    reprojection_error: finiteNumber,
    image_width: finiteNumber,
    image_height: finiteNumber,
    captured_at: z.string().optional(),
    camera_settings: cameraSettingsSchema.optional(),
    valid_image_count: finiteNumber.optional(),
    total_image_count: finiteNumber.optional(),
  }).passthrough();

  function formatZodError(error) {
    const issue = error?.issues?.[0];
    if (!issue) {
      return "invalid structured data";
    }

    const path = issue.path?.length ? issue.path.join(".") : "root";
    return `${path}: ${issue.message}`;
  }

  function createDefaultIntrinsics(frameWidth, frameHeight) {
    return {
      fx: frameWidth,
      fy: frameWidth,
      cx: frameWidth / 2,
      cy: frameHeight / 2,
    };
  }

  function createCameraModeKey(frameWidth, frameHeight, settings = {}) {
    const facingMode = settings.facingMode || "unknown";
    const deviceId = settings.deviceId || "unknown";
    return `${frameWidth}x${frameHeight}:${facingMode}:${deviceId}`;
  }

  function buildIntrinsicsRecord(intrinsics, options = {}) {
    return {
      fx: intrinsics.fx,
      fy: intrinsics.fy,
      cx: intrinsics.cx,
      cy: intrinsics.cy,
      distCoeffs: options.distCoeffs || null,
      reprojectionError: options.reprojectionError ?? null,
      imageWidth: options.imageWidth ?? null,
      imageHeight: options.imageHeight ?? null,
      source: options.source || "unknown",
      capturedAt: options.capturedAt || null,
      cameraSettings: options.cameraSettings || {},
    };
  }

  function parseIntrinsicsRecord(record) {
    const parsed = intrinsicsRecordSchema.safeParse(record);
    return parsed.success ? parsed.data : null;
  }

  function loadStoredIntrinsicsMap() {
    try {
      const raw = window.localStorage.getItem(constants.CAMERA_INTRINSICS_STORAGE_KEY);
      if (!raw) {
        return {};
      }

      const parsed = JSON.parse(raw);
      const validated = intrinsicsRecordMapSchema.safeParse(parsed);
      return validated.success ? validated.data : {};
    } catch (_error) {
      return {};
    }
  }

  function saveStoredIntrinsicsMap(recordsByMode) {
    window.localStorage.setItem(constants.CAMERA_INTRINSICS_STORAGE_KEY, JSON.stringify(recordsByMode));
  }

  function saveIntrinsicsRecord(frameWidth, frameHeight, record) {
    const settings = record.cameraSettings || {};
    const modeKey = createCameraModeKey(frameWidth, frameHeight, settings);
    const recordsByMode = loadStoredIntrinsicsMap();
    recordsByMode[modeKey] = record;
    saveStoredIntrinsicsMap(recordsByMode);
  }

  function getExternalIntrinsicsRecord(frameWidth, frameHeight, settings = {}) {
    const externalRecord = window.CAMERA_INTRINSICS;
    const parsedExternalRecord = parseIntrinsicsRecord(externalRecord);
    if (!parsedExternalRecord) {
      return null;
    }

    return buildIntrinsicsRecord(parsedExternalRecord, {
      imageWidth: frameWidth,
      imageHeight: frameHeight,
      source: "window.CAMERA_INTRINSICS",
      cameraSettings: settings,
    });
  }

  function getStoredIntrinsicsRecord(frameWidth, frameHeight, settings = {}) {
    const modeKey = createCameraModeKey(frameWidth, frameHeight, settings);
    const recordsByMode = loadStoredIntrinsicsMap();
    return parseIntrinsicsRecord(recordsByMode[modeKey]);
  }

  function getPreferredIntrinsicsRecord(frameWidth, frameHeight, settings = {}) {
    return (
      getExternalIntrinsicsRecord(frameWidth, frameHeight, settings) ||
      getStoredIntrinsicsRecord(frameWidth, frameHeight, settings) ||
      buildIntrinsicsRecord(createDefaultIntrinsics(frameWidth, frameHeight), {
        imageWidth: frameWidth,
        imageHeight: frameHeight,
        source: "default_approximation",
        cameraSettings: settings,
      })
    );
  }

  function configurePoseEstimation() {
    const frameWidth = dom.video.videoWidth;
    const frameHeight = dom.video.videoHeight;

    if (!frameWidth || !frameHeight) {
      return;
    }

    const settings = ns.getCurrentVideoSettings();
    const intrinsicsRecord = getPreferredIntrinsicsRecord(frameWidth, frameHeight, settings);
    state.currentIntrinsicsRecord = intrinsicsRecord;
    state.apriltagDetector.setCameraInfo(
      intrinsicsRecord.fx,
      intrinsicsRecord.fy,
      intrinsicsRecord.cx,
      intrinsicsRecord.cy
    );
  }

  function configureTagSizes() {
    for (let tagId = 0; tagId <= constants.MAX_CONFIGURED_TAG_ID; tagId += 1) {
      state.apriltagDetector.setTagSize(tagId, constants.DEFAULT_TAG_SIZE_METERS);
    }
  }

  function saveCalibrationResult(result) {
    const parsedResult = calibrationResultSchema.parse(result);
    const record = buildIntrinsicsRecord(parsedResult.intrinsics, {
      distCoeffs: parsedResult.dist_coeffs,
      reprojectionError: parsedResult.reprojection_error,
      imageWidth: parsedResult.image_width,
      imageHeight: parsedResult.image_height,
      source: "server_camera_calibration",
      capturedAt: parsedResult.captured_at,
      cameraSettings: parsedResult.camera_settings || {},
    });
    saveIntrinsicsRecord(parsedResult.image_width, parsedResult.image_height, record);
  }

  function parseCalibrationResult(result) {
    const parsed = calibrationResultSchema.safeParse(result);
    if (!parsed.success) {
      throw new Error(`invalid camera calibration result: ${formatZodError(parsed.error)}`);
    }
    return parsed.data;
  }

  function getCurrentIntrinsicsRecord() {
    const frameWidth = dom.video.videoWidth;
    const frameHeight = dom.video.videoHeight;
    if (!frameWidth || !frameHeight) {
      return null;
    }

    if (
      state.currentIntrinsicsRecord &&
      state.currentIntrinsicsRecord.imageWidth === frameWidth &&
      state.currentIntrinsicsRecord.imageHeight === frameHeight
    ) {
      return state.currentIntrinsicsRecord;
    }

    const settings = ns.getCurrentVideoSettings();
    const intrinsicsRecord = getPreferredIntrinsicsRecord(frameWidth, frameHeight, settings);
    state.currentIntrinsicsRecord = intrinsicsRecord;
    return intrinsicsRecord;
  }

  ns.intrinsics = {
    configurePoseEstimation,
    configureTagSizes,
    getCurrentIntrinsicsRecord,
    parseCalibrationResult,
    saveCalibrationResult,
  };
})(window.CameraPage = window.CameraPage || {});
