const state = {
  lastSweep: []
};

const $ = (id) => document.getElementById(id);

async function postJson(path, payload = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  log(`${path} -> ${data.status}`, data);
  return data;
}

async function getJson(path) {
  const response = await fetch(path);
  const data = await response.json();
  log(`${path} -> ${data.status}`, data);
  return data;
}

function log(title, data) {
  const target = $("eventLog");
  const time = new Date().toLocaleTimeString();
  target.textContent = `[${time}] ${title}\n${JSON.stringify(data, null, 2)}\n\n${target.textContent}`;
}

function writeJson(id, data) {
  $(id).textContent = JSON.stringify(data, null, 2);
}

async function refreshState() {
  const data = await getJson("/api/state");
  const aedt = data.aedt.state;
  const vna = data.vna.state;
  const config = data.vna.config;
  $("aedtState").textContent = aedt.connected ? "Conectado" : "Desconectado";
  $("aedtDetail").textContent = `${aedt.backend} ${aedt.detail || aedt.resource || ""}`;
  $("vnaState").textContent = vna.connected ? "Conectado" : "Desconectado";
  $("vnaDetail").textContent = `${vna.backend} ${vna.detail || vna.resource || ""}`;
  $("sweepRange").textContent = `${formatFreq(config.start_hz)} - ${formatFreq(config.stop_hz)}`;
  $("sweepDetail").textContent = `${config.points} pts, IFBW ${config.ifbw_hz} Hz, ${config.power_dbm} dBm`;
  renderMethods(data.supported);
}

function formatFreq(value) {
  if (value >= 1e9) return `${(value / 1e9).toFixed(3)} GHz`;
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)} MHz`;
  return `${value} Hz`;
}

function renderMethods(supported) {
  const target = $("methodMatrix");
  target.innerHTML = "";
  for (const [group, methods] of Object.entries(supported || {})) {
    const column = document.createElement("section");
    column.className = "method-column";
    const heading = document.createElement("h3");
    heading.textContent = group.toUpperCase();
    column.appendChild(heading);
    for (const method of methods) {
      const chip = document.createElement("button");
      chip.className = "method-chip";
      chip.textContent = method;
      chip.addEventListener("click", () => invokeMethod(group, method));
      column.appendChild(chip);
    }
    target.appendChild(column);
  }
}

async function invokeMethod(group, method) {
  if (group === "vna") {
    writeJson("vnaOutputJson", await postJson(`/${method}`, {}));
    return;
  }
  writeJson("aedtOutputJson", await postJson(`/${group}/${method}`, {}));
}

function activePanel(id) {
  for (const panel of document.querySelectorAll(".content-panel")) {
    panel.classList.toggle("active", panel.id === id);
  }
  for (const tab of document.querySelectorAll(".rail-tab")) {
    tab.classList.toggle("active", tab.dataset.panel === id);
  }
}

async function connectAedt(simulated = false) {
  const payload = {
    backend: simulated ? "simulated" : $("aedtBackend").value,
    project_path: $("aedtProject").value,
    design_name: $("aedtDesign").value
  };
  if (payload.backend === "simulated") {
    payload.project_path = null;
  }
  const data = await postJson("/aedt/openproject", payload);
  writeJson("aedtOutputJson", data);
  await refreshState();
}

async function loadVariables() {
  const data = await postJson("/aedt/getvariables", {});
  writeJson("aedtOutputJson", data);
  if (data.variables) $("variablesJson").value = JSON.stringify(data.variables, null, 2);
}

async function setVariables() {
  const variables = JSON.parse($("variablesJson").value || "{}");
  const data = await postJson("/aedt/setvariablesvalue", {variables});
  writeJson("aedtOutputJson", data);
}

async function evaluateAedt() {
  const variables = JSON.parse($("variablesJson").value || "{}");
  const data = await postJson("/aedt/evaluatedimension", {
    variables,
    output_touchstone: $("aedtOutput").value
  });
  writeJson("aedtOutputJson", data);
}

async function connectVna(simulated = false) {
  const payload = {
    backend: simulated ? "simulated" : $("vnaBackend").value,
    brand: simulated ? "SIM" : $("vnaBrand").value
  };
  const resource = $("vnaResource").value.trim();
  if (resource) payload.resource = resource;
  const data = await postJson("/connect", payload);
  writeJson("vnaOutputJson", data);
  await refreshState();
}

async function applySweep() {
  const data = await postJson("/api/vna/setfrequency", {
    start_hz: Number($("startHz").value),
    stop_hz: Number($("stopHz").value)
  });
  await postJson("/api/vna/setsweeppoints", {points: Number($("points").value)});
  await postJson("/api/vna/setifbw", {ifbw_hz: Number($("ifbw").value)});
  const power = await postJson("/api/vna/setpower", {power_dbm: Number($("power").value)});
  writeJson("vnaOutputJson", {frequency: data, power});
  await refreshState();
}

async function singleSweep() {
  const data = await postJson("/singlesweep", {});
  state.lastSweep = data.data || [];
  drawSweep(state.lastSweep);
  writeJson("vnaOutputJson", data);
}

async function saveTrace() {
  const data = await postJson("/savetracedata", {filePath: $("vnaOutput").value});
  writeJson("vnaOutputJson", data);
}

function drawSweep(points) {
  const canvas = $("sweepChart");
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#f7f8fb";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#d5dae3";
  ctx.lineWidth = 1;
  for (let i = 0; i < 6; i += 1) {
    const y = (height - 24) * i / 5 + 12;
    ctx.beginPath();
    ctx.moveTo(48, y);
    ctx.lineTo(width - 16, y);
    ctx.stroke();
  }
  if (!points.length) return;
  const minFreq = points[0].freq_hz;
  const maxFreq = points[points.length - 1].freq_hz;
  const dbValues = points.map((point) => point.s11_db);
  const minDb = Math.min(-5, ...dbValues);
  const maxDb = Math.max(0, ...dbValues);
  ctx.strokeStyle = "#155e75";
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((point, index) => {
    const x = 48 + (point.freq_hz - minFreq) / (maxFreq - minFreq || 1) * (width - 64);
    const y = 12 + (maxDb - point.s11_db) / (maxDb - minDb || 1) * (height - 36);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.fillStyle = "#22313f";
  ctx.font = "12px system-ui";
  ctx.fillText("S11 dB", 10, 18);
  ctx.fillText(formatFreq(minFreq), 48, height - 8);
  ctx.fillText(formatFreq(maxFreq), width - 110, height - 8);
}

function bind() {
  $("refreshState").addEventListener("click", refreshState);
  $("loadMethods").addEventListener("click", refreshState);
  $("clearLog").addEventListener("click", () => { $("eventLog").textContent = ""; });
  $("connectAedtSim").addEventListener("click", () => connectAedt(true));
  $("openAedt").addEventListener("click", () => connectAedt(false));
  $("loadVariables").addEventListener("click", loadVariables);
  $("setVariables").addEventListener("click", setVariables);
  $("evaluateAedt").addEventListener("click", evaluateAedt);
  $("connectVnaSim").addEventListener("click", () => connectVna(true));
  $("connectVna").addEventListener("click", () => connectVna(false));
  $("applySweep").addEventListener("click", applySweep);
  $("singleSweep").addEventListener("click", singleSweep);
  $("saveTrace").addEventListener("click", saveTrace);
  for (const tab of document.querySelectorAll(".rail-tab")) {
    tab.addEventListener("click", () => activePanel(tab.dataset.panel));
  }
}

window.addEventListener("DOMContentLoaded", async () => {
  bind();
  await refreshState();
});

