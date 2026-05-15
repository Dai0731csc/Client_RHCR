(function initCameraGripper(ns) {
  const { dom, state, constants } = ns;

  async function sendCommand(action) {
    if (state.gripperBusy) {
      return;
    }
    state.gripperBusy = true;
    ns.setGripperUI?.();

    try {
      const response = await window.fetch(constants.GRIPPER_COMMAND_API_PATH, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify({
          action,
          client_time: new Date().toISOString(),
        }),
      });
      const result = await response.json();
      if (!response.ok || !result.success || !result.accepted) {
        throw new Error(result.message || result.error || `gripper command failed with ${response.status}`);
      }
      state.gripperState = action === "open" ? "open" : "closed";
      state.gripperBusy = false;
      ns.setGripperUI?.();
    } catch (error) {
      state.gripperBusy = false;
      ns.setGripperUI?.();
      console.warn("Failed to send gripper command:", error);
    }
  }

  function getToggleAction() {
    return state.gripperState === "open" ? "close" : "open";
  }

  function initialize() {
    dom.gripperToggleBtn?.addEventListener("click", () => {
      const action = getToggleAction();
      void sendCommand(action);
    });
    ns.setGripperUI?.();
  }

  function dispose() {}

  ns.gripper = {
    initialize,
    dispose,
  };
})(window.CameraPage = window.CameraPage || {});
