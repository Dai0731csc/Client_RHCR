class ApriltagDetector {
  constructor() {
    this.module = null;
    this.detectFn = null;
    this.destroyFn = null;
    this.setImageBufferFn = null;
    this.setDetectorOptionsFn = null;
    this.setPoseInfoFn = null;
    this.setTagSizeFn = null;
    this.textDecoder = new TextDecoder("utf-8");
    this.ready = false;
  }

  async init() {
    if (this.ready) {
      return;
    }

    const basePath = (window.CameraPageConfig && window.CameraPageConfig.basePath) || "";

    this.module = await AprilTagWasm({
      locateFile(path) {
        return `${basePath}/static/vendor/apriltag/${path}`;
      },
    });

    const initFn = this.module.cwrap("atagjs_init", "number", []);
    this.detectFn = this.module.cwrap("atagjs_detect", "number", []);
    this.destroyFn = this.module.cwrap("atagjs_destroy", null, []);
    this.setImageBufferFn = this.module.cwrap("atagjs_set_img_buffer", "number", ["number", "number", "number"]);
    this.setDetectorOptionsFn = this.module.cwrap(
      "atagjs_set_detector_options",
      "number",
      ["number", "number", "number", "number", "number", "number", "number"]
    );
    this.setPoseInfoFn = this.module.cwrap(
      "atagjs_set_pose_info",
      "number",
      ["number", "number", "number", "number"]
    );
    this.setTagSizeFn = this.module.cwrap("atagjs_set_tag_size", null, ["number", "number"]);

    initFn();

    this.setDetectorOptionsFn(
      2.0, // quad_decimate: downsample image by 2x before detection for speed
      0.0, // quad_sigma: no Gaussian blur before quad detection
      1, // nthreads: use a single worker thread
      1, // refine_edges: enable edge refinement
      0, // max_detections: 0 means no explicit limit on returned detections
      1, // return_pose: include pose.t and pose.R in each detection
      1 // return_solutions: include pose solution candidates from the solver
    );

    this.ready = true;
  }

  destroy() {
    if (!this.ready) {
      return;
    }

    if (this.destroyFn) {
      this.destroyFn();
    }

    this.module = null;
    this.detectFn = null;
    this.destroyFn = null;
    this.setImageBufferFn = null;
    this.setDetectorOptionsFn = null;
    this.setPoseInfoFn = null;
    this.setTagSizeFn = null;
    this.ready = false;
  }

  setCameraInfo(fx, fy, cx, cy) {
    if (!this.ready) {
      throw new Error("Apriltag detector is not ready");
    }

    this.setPoseInfoFn(fx, fy, cx, cy);
  }

  setTagSize(tagId, sizeInMeters) {
    if (!this.ready) {
      throw new Error("Apriltag detector is not ready");
    }

    this.setTagSizeFn(tagId, sizeInMeters);
  }

  detect(grayscalePixels, width, height) {
    if (!this.ready) {
      throw new Error("Apriltag detector is not ready");
    }

    if (grayscalePixels.length !== width * height) {
      throw new Error(
        `Invalid grayscale buffer length: expected ${width * height}, got ${grayscalePixels.length}`
      );
    }

    const imageBufferPtr = this.setImageBufferFn(width, height, width);
    this.module.HEAPU8.set(grayscalePixels, imageBufferPtr);

    const resultPtr = this.detectFn();
    const jsonLength = this.module.getValue(resultPtr, "i32");

    if (!jsonLength) {
      return [];
    }

    const jsonStringPtr = this.module.getValue(resultPtr + 4, "i32");
    const jsonBytes = new Uint8Array(this.module.HEAPU8.buffer, jsonStringPtr, jsonLength);
    const jsonText = this.textDecoder.decode(jsonBytes);

    return JSON.parse(jsonText);
  }
}
