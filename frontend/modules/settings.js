(function initSettingsPage() {
  const basePath = (window.SettingsPageConfig && window.SettingsPageConfig.basePath) || "";
  const withBasePath = window.SharedBasePath.createWithBasePath(basePath);

  const SETTINGS_API = withBasePath("/api/settings");

  const TRANSPORT_INPUT_IDS = [
    "transport-local-udp",
    "transport-local-tcp",
    "transport-cloud-tcp",
    "transport-cloud-udp",
  ];

  const TRANSPORT_MODE_BY_ID = {
    "transport-local-udp": "local_udp",
    "transport-local-tcp": "local_tcp",
    "transport-cloud-tcp": "cloud_tcp",
    "transport-cloud-udp": "cloud_udp",
  };

  const TRANSPORT_MODE_DEFAULT = "local_udp";
  const TEXT_APPLY_DELAY_MS = 400;

  const el = {
    backLink: document.getElementById("back-link"),
    sessionId: document.getElementById("session-id"),
    cloudHost: document.getElementById("cloud-host"),
    topologySameMachine: document.getElementById("topology-same-machine"),
    topologySameLan: document.getElementById("topology-same-lan"),
    feedback: document.getElementById("save-feedback"),
    configPath: document.getElementById("config-path"),
    effectiveMode: document.getElementById("effective-mode"),
    activeOutbound: document.getElementById("active-outbound"),
    outboundConnected: document.getElementById("outbound-connected"),
    relayUrl: document.getElementById("relay-url"),
  };

  TRANSPORT_INPUT_IDS.forEach((id) => {
    el[id] = document.getElementById(id);
  });

  let syncingUi = false;
  let applyInFlight = false;
  let applyQueued = false;
  let textApplyTimer = null;

  el.backLink.href = withBasePath("/");

  function setFeedback(message, tone = "") {
    el.feedback.textContent = message || "";
    el.feedback.classList.remove("is-error", "is-success");
    if (tone) {
      el.feedback.classList.add(tone);
    }
  }

  function setTransportModeSelection(mode) {
    const selectedMode = mode || TRANSPORT_MODE_DEFAULT;
    TRANSPORT_INPUT_IDS.forEach((id) => {
      el[id].checked = TRANSPORT_MODE_BY_ID[id] === selectedMode;
    });
  }

  function getSelectedTransportMode() {
    for (const id of TRANSPORT_INPUT_IDS) {
      if (el[id].checked) {
        return TRANSPORT_MODE_BY_ID[id];
      }
    }
    return TRANSPORT_MODE_DEFAULT;
  }

  function setTopologySelection(topologies) {
    const sameMachine = Boolean(topologies?.same_machine);
    const sameLan = Boolean(topologies?.same_lan);
    el.topologySameMachine.checked = sameMachine || !sameLan;
    el.topologySameLan.checked = sameLan;
  }

  function getTopologySelection() {
    return {
      same_machine: el.topologySameMachine.checked,
      same_lan: el.topologySameLan.checked,
    };
  }

  function buildPayload() {
    return {
      transport_mode: getSelectedTransportMode(),
      session_id: el.sessionId.value.trim(),
      cloud_host: el.cloudHost.value.trim(),
      local_topologies: getTopologySelection(),
    };
  }

  function applySettingsToUi(settings) {
    syncingUi = true;
    setTransportModeSelection(settings.transport_mode);
    el.sessionId.value = settings.session_id || "default";
    el.cloudHost.value = settings.cloud_host || "";
    setTopologySelection(settings.local_topologies);
    el.configPath.textContent = settings.config_path || "-";
    el.effectiveMode.textContent = settings.transport_mode || "-";
    el.activeOutbound.textContent = settings.active_outbound || "-";
    el.outboundConnected.textContent = settings.outbound_connected ? "yes" : "no";
    el.relayUrl.textContent = settings.relay_url || "-";
    syncingUi = false;
  }

  async function loadSettings() {
    setFeedback("Loading…");
    try {
      const response = await fetch(SETTINGS_API, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      applySettingsToUi(await response.json());
      setFeedback("");
    } catch (error) {
      setFeedback(`Failed to load settings: ${error.message}`, "is-error");
    }
  }

  async function applySettingsNow() {
    if (syncingUi) {
      return;
    }
    if (applyInFlight) {
      applyQueued = true;
      return;
    }

    applyInFlight = true;
    setFeedback("Applying…");

    try {
      const response = await fetch(SETTINGS_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      const body = await response.json();
      if (!response.ok || !body.success) {
        throw new Error(body.message || body.error || `HTTP ${response.status}`);
      }
      applySettingsToUi(body.settings);
      setFeedback(body.message || "Applied.", "is-success");
    } catch (error) {
      setFeedback(`Apply failed: ${error.message}`, "is-error");
      await loadSettings();
    } finally {
      applyInFlight = false;
      if (applyQueued) {
        applyQueued = false;
        applySettingsNow();
      }
    }
  }

  function scheduleApply() {
    if (syncingUi) {
      return;
    }
    if (textApplyTimer) {
      clearTimeout(textApplyTimer);
    }
    textApplyTimer = setTimeout(() => {
      textApplyTimer = null;
      applySettingsNow();
    }, TEXT_APPLY_DELAY_MS);
  }

  TRANSPORT_INPUT_IDS.forEach((id) => {
    el[id].addEventListener("change", () => {
      if (syncingUi) {
        return;
      }
      if (!el[id].checked) {
        if (!TRANSPORT_INPUT_IDS.some((otherId) => el[otherId].checked)) {
          el[id].checked = true;
        }
        return;
      }
      TRANSPORT_INPUT_IDS.forEach((otherId) => {
        el[otherId].checked = otherId === id;
      });
      applySettingsNow();
    });
  });

  [el.topologySameMachine, el.topologySameLan].forEach((input) => {
    input.addEventListener("change", () => {
      if (syncingUi) {
        return;
      }
      if (!input.checked) {
        if (!el.topologySameMachine.checked && !el.topologySameLan.checked) {
          input.checked = true;
        }
        return;
      }
      if (input === el.topologySameMachine) {
        el.topologySameLan.checked = false;
      } else {
        el.topologySameMachine.checked = false;
      }
      applySettingsNow();
    });
  });

  [el.sessionId, el.cloudHost].forEach((input) => {
    input.addEventListener("input", scheduleApply);
    input.addEventListener("change", scheduleApply);
  });

  loadSettings();
})();
