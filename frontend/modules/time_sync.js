(function initSharedTimeSync(global) {
  function median(values) {
    if (!values.length) {
      return Number.NaN;
    }

    const sorted = [...values].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    if (sorted.length % 2 === 1) {
      return sorted[mid];
    }

    return (sorted[mid - 1] + sorted[mid]) / 2;
  }

  function createTimeSyncClient(options = {}) {
    const {
      timeoutMs = 2000,
      maxSampleCount = 100,
      offsetSubsetCount = 5,
    } = options;

    let nextSeq = 0;
    const pending = new Map();
    const samples = [];
    let stableOffsetMs = Number.NaN;
    let stableRttMs = Number.NaN;

    function getSnapshot() {
      return {
        offsetMs: stableOffsetMs,
        rttMs: stableRttMs,
        sampleCount: samples.length,
      };
    }

    function rejectAllPending(message) {
      for (const entry of pending.values()) {
        window.clearTimeout(entry.timeoutId);
        entry.reject(new Error(message));
      }
      pending.clear();
    }

    function sendPing(sendFn) {
      const seq = nextSeq;
      nextSeq += 1;

      return new Promise((resolve, reject) => {
        const clientSendPerfMs = performance.now();
        const clientSendWallTime = new Date().toISOString();
        const timeoutId = window.setTimeout(() => {
          pending.delete(seq);
          reject(new Error(`Time sync ping timed out for seq=${seq}`));
        }, timeoutMs);

        pending.set(seq, {
          clientSendPerfMs,
          clientSendWallTime,
          timeoutId,
          resolve,
          reject,
        });

        try {
          sendFn(
            JSON.stringify({
              type: "ping",
              seq,
              client_send_time: clientSendWallTime,
            })
          );
        } catch (error) {
          window.clearTimeout(timeoutId);
          pending.delete(seq);
          reject(error);
        }
      });
    }

    function handleAck(payload) {
      if (payload?.type !== "ack" || payload.received?.type !== "ping") {
        return null;
      }

      const seq = payload.received.seq;
      const entry = pending.get(seq);
      if (!entry) {
        return null;
      }

      pending.delete(seq);
      window.clearTimeout(entry.timeoutId);

      const clientRecvPerfMs = performance.now();
      const clientRecvWallMs = Date.now();
      const clientSendWallMs = Date.parse(entry.clientSendWallTime);
      const masterReceiveWallMs = Date.parse(payload.master_receive_time);
      const masterSendWallMs = Date.parse(payload.master_send_time);

      const rttMs = clientRecvPerfMs - entry.clientSendPerfMs;
      const masterProcMs = masterSendWallMs - masterReceiveWallMs;
      const clientMidWallMs = (clientSendWallMs + clientRecvWallMs) / 2;
      const masterMidWallMs = (masterReceiveWallMs + masterSendWallMs) / 2;
      // Positive offset means the client clock is ahead of the master clock.
      const offsetMs = clientMidWallMs - masterMidWallMs;

      samples.push({
        rttMs,
        offsetMs,
        masterProcMs,
        clientSendWallMs,
        clientRecvWallMs,
        masterReceiveWallMs,
        masterSendWallMs,
      });
      if (samples.length > maxSampleCount) {
        samples.shift();
      }

      const bestSamples = [...samples]
        .sort((a, b) => a.rttMs - b.rttMs)
        .slice(0, Math.min(offsetSubsetCount, samples.length));

      stableOffsetMs = median(bestSamples.map((sample) => sample.offsetMs));
      stableRttMs = median(bestSamples.map((sample) => sample.rttMs));

      const result = {
        seq,
        rttMs,
        offsetMs,
        masterProcMs,
        clientSendWallMs,
        clientRecvWallMs,
        masterReceiveWallMs,
        masterSendWallMs,
        stableOffsetMs,
        stableRttMs,
        bestSampleCount: bestSamples.length,
      };
      entry.resolve(result);
      return result;
    }

    async function syncClock({ sampleCount = 8, sendFn, sleepMs = 60 }) {
      const results = [];

      for (let index = 0; index < sampleCount; index += 1) {
        try {
          results.push(await sendPing(sendFn));
        } catch (_error) {
          continue;
        }

        await new Promise((resolve) => {
          window.setTimeout(resolve, sleepMs);
        });
      }

      if (!results.length || !Number.isFinite(stableOffsetMs)) {
        throw new Error("Clock sync failed");
      }

      return {
        sampleCount: results.length,
        offsetMs: stableOffsetMs,
        rttMs: stableRttMs,
      };
    }

    return {
      getSnapshot,
      sendPing,
      handleAck,
      syncClock,
      rejectAllPending,
    };
  }

  global.SharedTimeSync = {
    createTimeSyncClient,
  };
})(window);
