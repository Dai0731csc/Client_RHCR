(function initCameraTransportRealtime(ns) {
  const { state, constants, withBasePath } = ns;
  const transport = ns.transport || (ns.transport = {});
  const internals = ns.transportInternals || (ns.transportInternals = {});

  function describeTransportError(error, fallbackMessage) {
    if (!error) {
      return fallbackMessage;
    }

    const message = error.message || String(error);
    return message || fallbackMessage;
  }

  function shouldAttemptWebRTC() {
    return Date.now() >= state.webrtcRetryAtMs;
  }

  function resetWebRTCRetryState() {
    state.webrtcFailureCount = 0;
    state.webrtcRetryAtMs = 0;
    state.lastWebRTCFailureMessage = "";
  }

  function ensureSocket({ socketKey, readyKey, path, errorMessage, onMessage, onClose }) {
    if (state[socketKey] && state[socketKey].readyState === WebSocket.OPEN) {
      return Promise.resolve(state[socketKey]);
    }

    if (state[readyKey]) {
      return state[readyKey];
    }

    state[readyKey] = new Promise((resolve, reject) => {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const socket = new WebSocket(`${protocol}://${location.host}${path}`);
      let settled = false;

      function settleResolve(value) {
        if (settled) {
          return;
        }
        settled = true;
        resolve(value);
      }

      function settleReject(error) {
        if (settled) {
          return;
        }
        settled = true;
        reject(error);
      }

      function settleRejectAsync(error) {
        window.setTimeout(() => {
          settleReject(error);
        }, 0);
      }

      socket.onopen = () => {
        state[socketKey] = socket;
        state[readyKey] = null;
        settleResolve(socket);
      };

      if (onMessage) {
        socket.onmessage = onMessage;
      }

      socket.onerror = () => {
        if (state[socketKey] === socket) {
          state[socketKey] = null;
        }
        state[readyKey] = null;
        settleRejectAsync(new Error(errorMessage));
      };

      socket.onclose = () => {
        if (state[socketKey] === socket) {
          state[socketKey] = null;
        }
        state[readyKey] = null;
        settleRejectAsync(new Error(`${errorMessage}: socket closed before ready`));

        if (onClose) {
          onClose();
        }
      };
    });

    return state[readyKey];
  }

  function closeSocket(socketKey) {
    if (state[socketKey]) {
      state[socketKey].close();
      state[socketKey] = null;
    }
  }

  function waitForIceGatheringComplete(peerConnection, timeoutMs = 5000) {
    if (peerConnection.iceGatheringState === "complete") {
      return Promise.resolve();
    }

    return new Promise((resolve, reject) => {
      const timeoutId = window.setTimeout(() => {
        peerConnection.removeEventListener("icegatheringstatechange", onStateChange);
        reject(new Error("WebRTC ICE gathering timed out"));
      }, timeoutMs);

      function onStateChange() {
        if (peerConnection.iceGatheringState !== "complete") {
          return;
        }

        window.clearTimeout(timeoutId);
        peerConnection.removeEventListener("icegatheringstatechange", onStateChange);
        resolve();
      }

      peerConnection.addEventListener("icegatheringstatechange", onStateChange);
    });
  }

  function waitForDataChannelOpen(channel, timeoutMs = 5000) {
    if (channel.readyState === "open") {
      return Promise.resolve(channel);
    }

    return new Promise((resolve, reject) => {
      const timeoutId = window.setTimeout(() => {
        channel.removeEventListener("open", onOpen);
        reject(new Error("WebRTC data channel open timed out"));
      }, timeoutMs);

      function onOpen() {
        window.clearTimeout(timeoutId);
        channel.removeEventListener("open", onOpen);
        resolve(channel);
      }

      channel.addEventListener("open", onOpen);
    });
  }

  async function fetchWebRTCConfig() {
    if (state.webrtcConfig) {
      return state.webrtcConfig;
    }

    const response = await window.fetch(constants.WEBRTC_SIGNALING_API_PATH, {
      credentials: "same-origin",
    });
    if (!response.ok) {
      throw new Error(`Failed to fetch WebRTC config (${response.status})`);
    }

    state.webrtcConfig = await response.json();
    return state.webrtcConfig;
  }

  function clearPendingRealtimeAnswer(message) {
    if (!state.pendingRealtimeAnswer) {
      return;
    }

    const pending = state.pendingRealtimeAnswer;
    state.pendingRealtimeAnswer = null;
    window.clearTimeout(pending.timeoutId);
    pending.reject(new Error(message));
  }

  function waitForRealtimeAnswer(signalingSocket, peerConnection, timeoutMs = 7000) {
    return new Promise((resolve, reject) => {
      const timeoutId = window.setTimeout(() => {
        if (state.pendingRealtimeAnswer?.timeoutId === timeoutId) {
          state.pendingRealtimeAnswer = null;
        }
        reject(new Error("WebRTC signaling answer timed out"));
      }, timeoutMs);

      state.pendingRealtimeAnswer = {
        resolve: (payload) => {
          window.clearTimeout(timeoutId);
          resolve(payload);
        },
        reject: (error) => {
          window.clearTimeout(timeoutId);
          reject(error);
        },
        timeoutId,
      };

      signalingSocket.send(
        JSON.stringify({
          type: "webrtc_offer",
          sdp: peerConnection.localDescription.sdp,
        })
      );
    });
  }

  function markWebRTCFailure(error, logKey = "apriltag_detection") {
    const message = describeTransportError(error, "WebRTC realtime connection failed");
    const delayMs = Math.min(
      constants.WEBRTC_RETRY_INITIAL_DELAY_MS * (2 ** state.webrtcFailureCount),
      constants.WEBRTC_RETRY_MAX_DELAY_MS
    );

    state.webrtcFailureCount += 1;
    state.webrtcRetryAtMs = Date.now() + delayMs;

    if (state.lastWebRTCFailureMessage !== message) {
      console.warn(
        `${logKey}: ${message}; switched to WebSocket and will retry WebRTC in ${Math.round(delayMs / 1000)}s`
      );
    }
    state.lastWebRTCFailureMessage = message;
    closeRealtimeConnection();
  }

  function handleRealtimeSignalingMessage(event) {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch (_error) {
      return;
    }

    if (payload.type === "webrtc_answer" && state.pendingRealtimeAnswer) {
      const pending = state.pendingRealtimeAnswer;
      state.pendingRealtimeAnswer = null;
      window.clearTimeout(pending.timeoutId);
      pending.resolve(payload);
      return;
    }

    if (payload.type === "webrtc_error") {
      clearPendingRealtimeAnswer(payload.message || "WebRTC signaling failed");
    }
  }

  function ensureRealtimeSignalingSocket() {
    return ensureSocket({
      socketKey: "realtimeSignalingSocket",
      readyKey: "realtimeSignalingSocketReady",
      path: withBasePath("/ws/webrtc"),
      errorMessage: "WebRTC signaling WebSocket connection failed",
      onMessage: handleRealtimeSignalingMessage,
      onClose: () => {
        clearPendingRealtimeAnswer("WebRTC signaling socket closed");
      },
    });
  }

  function ensureCalibrationSocket() {
    if (state.calibrationSocket && state.calibrationSocket.readyState === WebSocket.OPEN) {
      return Promise.resolve(state.calibrationSocket);
    }

    return ensureSocket({
      socketKey: "calibrationSocket",
      readyKey: "calibrationSocketReady",
      path: withBasePath("/ws/calibration/publish"),
      errorMessage: "Calibration WebSocket connection failed",
    });
  }

  function ensureApriltagSocket() {
    return ensureSocket({
      socketKey: "apriltagSocket",
      readyKey: "apriltagSocketReady",
      path: withBasePath("/ws/publish"),
      errorMessage: "Apriltag WebSocket connection failed",
      onMessage: internals.handleRealtimeDataMessage,
      onClose: () => {
        state.timeSyncClient.rejectAllPending("Apriltag WebSocket closed");
      },
    });
  }

  async function createRealtimeChannel() {
    const signalingSocket = await ensureRealtimeSignalingSocket();
    const config = await fetchWebRTCConfig();
    const peerConnection = new RTCPeerConnection({
      iceServers: config.iceServers || [],
    });
    const dataChannel = peerConnection.createDataChannel("apriltag", {
      ordered: false,
      maxRetransmits: 0,
    });

    state.realtimePeerConnection = peerConnection;
    state.realtimeDataChannel = dataChannel;

    peerConnection.addEventListener("connectionstatechange", () => {
      if (!["failed", "closed", "disconnected"].includes(peerConnection.connectionState)) {
        return;
      }
      closeRealtimeConnection();
    });

    dataChannel.addEventListener("close", () => {
      if (state.realtimeDataChannel === dataChannel) {
        state.realtimeDataChannel = null;
      }
    });
    dataChannel.addEventListener("message", internals.handleRealtimeDataMessage);

    const offer = await peerConnection.createOffer();
    await peerConnection.setLocalDescription(offer);
    await waitForIceGatheringComplete(peerConnection);

    const answerPayload = await waitForRealtimeAnswer(signalingSocket, peerConnection);

    await peerConnection.setRemoteDescription({
      type: "answer",
      sdp: answerPayload.sdp,
    });

    await waitForDataChannelOpen(dataChannel);
    resetWebRTCRetryState();
    return dataChannel;
  }

  async function ensureRealtimeChannel(logKey = "apriltag_detection") {
    if (state.realtimeDataChannel && state.realtimeDataChannel.readyState === "open") {
      return state.realtimeDataChannel;
    }

    if (state.realtimeChannelReady) {
      return state.realtimeChannelReady;
    }

    if (!shouldAttemptWebRTC()) {
      throw new Error("WebRTC retry cooldown is active");
    }

    state.realtimeChannelReady = createRealtimeChannel()
      .catch((error) => {
        markWebRTCFailure(error, logKey);
        throw error;
      })
      .finally(() => {
        state.realtimeChannelReady = null;
      });
    return await state.realtimeChannelReady;
  }

  function ensureRealtimeChannelInBackground() {
    if (
      state.realtimeDataChannel?.readyState === "open" ||
      state.realtimeChannelReady ||
      !shouldAttemptWebRTC()
    ) {
      return;
    }

    void ensureRealtimeChannel("apriltag_detection").catch(() => {});
  }

  async function sendRealtimePayload(payload) {
    const message = JSON.stringify(payload);

    const channel = state.realtimeDataChannel;
    if (
      channel?.readyState === "open" &&
      channel.bufferedAmount <= constants.MAX_REALTIME_BUFFERED_BYTES
    ) {
      channel.send(message);
      return true;
    }

    ensureRealtimeChannelInBackground();

    const socket = await ensureApriltagSocket();
    if (socket.readyState !== WebSocket.OPEN) {
      return false;
    }

    if (socket.bufferedAmount > constants.MAX_WS_BUFFERED_BYTES) {
      return false;
    }

    socket.send(message);
    return true;
  }

  async function sendApriltagPayload(detections, timings = {}) {
    return await sendRealtimePayload(transport.createApriltagPayload(detections, timings));
  }

  async function sendDetectionState(active) {
    await sendRealtimePayload(transport.createDetectionStatePayload(active));
  }

  async function sendCalibrationPayload(payload) {
    const socket = await ensureCalibrationSocket();
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      throw new Error("Calibration WebSocket is not open");
    }

    socket.send(JSON.stringify(payload));
  }

  function closeRealtimeConnection() {
    clearPendingRealtimeAnswer("WebRTC realtime connection closed");
    state.timeSyncClient.rejectAllPending("WebRTC realtime connection closed");

    if (state.realtimeDataChannel) {
      state.realtimeDataChannel.close();
      state.realtimeDataChannel = null;
    }

    if (state.realtimePeerConnection) {
      state.realtimePeerConnection.close();
      state.realtimePeerConnection = null;
    }

    closeSocket("realtimeSignalingSocket");
  }

  function closeCalibrationSocket() {
    closeSocket("calibrationSocket");
  }

  function closeApriltagSocket() {
    closeSocket("apriltagSocket");
  }

  transport.ensureRealtimeChannel = ensureRealtimeChannel;
  transport.ensureRealtimeChannelInBackground = ensureRealtimeChannelInBackground;
  transport.ensureApriltagSocket = ensureApriltagSocket;
  transport.ensureCalibrationSocket = ensureCalibrationSocket;
  transport.sendApriltagPayload = sendApriltagPayload;
  transport.sendDetectionState = sendDetectionState;
  transport.sendCalibrationPayload = sendCalibrationPayload;
  transport.closeRealtimeConnection = closeRealtimeConnection;
  transport.closeApriltagSocket = closeApriltagSocket;
  transport.closeCalibrationSocket = closeCalibrationSocket;

  internals.describeTransportError = describeTransportError;
  internals.shouldAttemptWebRTC = shouldAttemptWebRTC;
  internals.resetWebRTCRetryState = resetWebRTCRetryState;
  internals.markWebRTCFailure = markWebRTCFailure;
  internals.ensureSocket = ensureSocket;
  internals.closeSocket = closeSocket;
})(window.CameraPage = window.CameraPage || {});
