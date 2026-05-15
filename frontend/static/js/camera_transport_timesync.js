(function initCameraTransportTimeSync(ns) {
  const { state, constants } = ns;
  const transport = ns.transport || (ns.transport = {});
  const internals = ns.transportInternals || (ns.transportInternals = {});

  function handleRealtimeDataMessage(event) {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch (_error) {
      return;
    }

    if (payload.type === "ack" && payload.received?.type === "ping") {
      state.timeSyncClient.handleAck(payload);
    }
  }

  async function syncClock(sampleCount = constants.TIME_SYNC_SAMPLE_COUNT) {
    if (state.realtimeDataChannel?.readyState === "open" || internals.shouldAttemptWebRTC()) {
      try {
        const channel = await transport.ensureRealtimeChannel("time_sync");
        const result = await state.timeSyncClient.syncClock({
          sampleCount,
          sleepMs: constants.TIME_SYNC_SLEEP_MS,
          sendFn: (message) => {
            if (!channel || channel.readyState !== "open") {
              throw new Error("WebRTC realtime data channel is not open");
            }
            channel.send(message);
          },
        });
        return {
          ...result,
          transportLabel: "webrtc:apriltag",
        };
      } catch (_error) {
      }
    }

    const socket = await transport.ensureApriltagSocket();
    const result = await state.timeSyncClient.syncClock({
      sampleCount,
      sleepMs: constants.TIME_SYNC_SLEEP_MS,
      sendFn: (message) => {
        if (!socket || socket.readyState !== WebSocket.OPEN) {
          throw new Error("Apriltag WebSocket is not open");
        }
        socket.send(message);
      },
    });
    return {
      ...result,
      transportLabel: "websocket:apriltag",
    };
  }

  async function reportTimeSyncResult(summary) {
    const message = JSON.stringify({
      type: "time_sync_result",
      ...summary,
    });

    if (summary.transport === "webrtc:apriltag" && state.realtimeDataChannel?.readyState === "open") {
      state.realtimeDataChannel.send(message);
      return true;
    }

    const socket = await transport.ensureApriltagSocket();
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return false;
    }

    socket.send(message);
    return true;
  }

  function closeTimeSyncSocket() {
    state.timeSyncClient.rejectAllPending("Time sync channel closed");
  }

  transport.syncClock = syncClock;
  transport.reportTimeSyncResult = reportTimeSyncResult;
  transport.closeTimeSyncSocket = closeTimeSyncSocket;

  internals.handleRealtimeDataMessage = handleRealtimeDataMessage;
})(window.CameraPage = window.CameraPage || {});
