const workspace = {
  filterType: "BPF",
  dispersion: "symmetric",
  zeros: [],
  result: null,
  measurement: [],
  chartMode: "sparameter",
  chartFloor: -70,
  visibleSeries: new Set(["s11", "s21"]),
  markerEnabled: false,
  markerIndex: null,
  matrixEditing: false,
  selectedCell: null,
  dirty: true,
  toastTimer: null
};

const $ = (id) => document.getElementById(id);

async function requestJson(path, options = {}) {
  const response = await fetch(path, options);
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : {status: -500, ok: false, message: await response.text()};
  logService(`${options.method || "GET"} ${path}`, data);
  if (!response.ok || data.ok === false && data.status !== -501) {
    throw new Error(data.message || `Request failed with HTTP ${response.status}`);
  }
  return data;
}

function getJson(path) {
  return requestJson(path);
}

function postJson(path, payload = {}) {
  return requestJson(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });
}

function logService(title, data) {
  const target = $("eventLog");
  if (!target) return;
  const time = new Date().toLocaleTimeString();
  const entry = `[${time}] ${title}\n${JSON.stringify(data, null, 2)}\n\n`;
  target.textContent = `${entry}${target.textContent}`.slice(0, 50000);
}

function setOperation(message) {
  $("operationStatus").textContent = message;
  $("dialogStatus").textContent = message;
}

function showToast(message, error = false) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.toggle("error", error);
  toast.classList.add("visible");
  clearTimeout(workspace.toastTimer);
  workspace.toastTimer = setTimeout(() => toast.classList.remove("visible"), 2600);
}

function setDirty(dirty = true) {
  workspace.dirty = dirty;
  const name = $("projectName");
  name.textContent = dirty ? "Unsaved Project *" : "Filter Project";
}

function numericValue(id, fallback = 0) {
  const value = Number($(id).value);
  return Number.isFinite(value) ? value : fallback;
}

function currentSpecification() {
  const unloadedQ = $("unloadedQ").value.trim();
  return {
    filter_type: workspace.filterType,
    order: numericValue("filterOrder", 4),
    return_loss_db: numericValue("returnLoss", 25),
    f0_ghz: numericValue("f0Ghz", 1),
    bandwidth_ghz: numericValue("bandwidthGhz", 0.05),
    start_ghz: numericValue("startGhz", 0.875),
    stop_ghz: numericValue("stopGhz", 1.125),
    shift_mhz: numericValue("shiftMhz", 0),
    delta_bandwidth_mhz: numericValue("deltaBandwidthMhz", 0),
    unloaded_q: /^infinity$/i.test(unloadedQ) || unloadedQ === "" ? null : Number(unloadedQ),
    points: 401,
    response_family: $("responseFamily").value,
    dispersion: workspace.dispersion,
    dispersion_value: numericValue("dispersionValue", 0),
    zeros: workspace.zeros.map(({frequency_ghz, depth_db}) => ({frequency_ghz, depth_db}))
  };
}

async function calculateAll({quiet = false} = {}) {
  setOperation("Calculating filter synthesis...");
  $("calculateAll").disabled = true;
  try {
    const result = await postJson("/api/synthesis/calculate", currentSpecification());
    workspace.result = result;
    workspace.selectedCell = null;
    renderAll();
    const spec = result.specification;
    $("calculationStatus").textContent =
      `${result.summary.frequency_points} points | ${spec.filter_type} | Order ${spec.order}`;
    setOperation(
      `Calculated ${spec.filter_type} order ${spec.order} at ${spec.effective_f0_ghz.toFixed(4)} GHz`
    );
    if (!quiet) showToast("Synthesis updated");
  } catch (error) {
    setOperation(`Calculation failed: ${error.message}`);
    showToast(error.message, true);
  } finally {
    $("calculateAll").disabled = false;
  }
}

function renderAll() {
  if (!workspace.result) return;
  renderTopology();
  renderMatrix();
  renderSpecification();
  renderDispersionSummary();
  drawChart();
}

function renderTopology() {
  const svg = $("topologyDiagram");
  const topology = workspace.result.topology;
  const namespace = "http://www.w3.org/2000/svg";
  const width = 720;
  const height = 180;
  const margin = 42;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.textContent = "";

  const positions = new Map();
  topology.nodes.forEach((node) => {
    positions.set(node.id, {
      x: margin + node.x * (width - margin * 2),
      y: height / 2
    });
  });

  topology.edges.forEach((edge) => {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (!source || !target) return;
    const path = document.createElementNS(namespace, "path");
    if (edge.kind === "cross") {
      const rise = Math.max(34, Math.abs(target.x - source.x) * 0.28);
      path.setAttribute(
        "d",
        `M ${source.x} ${source.y} Q ${(source.x + target.x) / 2} ${source.y - rise} ${target.x} ${target.y}`
      );
      path.setAttribute("stroke", "#e5a333");
      path.setAttribute("stroke-dasharray", "5 4");
      path.setAttribute("stroke-width", "3");
    } else {
      path.setAttribute("d", `M ${source.x} ${source.y} L ${target.x} ${target.y}`);
      path.setAttribute("stroke", "#666a6e");
      path.setAttribute("stroke-width", "6");
    }
    path.setAttribute("fill", "none");
    path.setAttribute("stroke-linecap", "round");
    svg.appendChild(path);
  });

  topology.nodes.forEach((node) => {
    const point = positions.get(node.id);
    const group = document.createElementNS(namespace, "g");
    const circle = document.createElementNS(namespace, "circle");
    const label = document.createElementNS(namespace, "text");
    circle.setAttribute("cx", point.x);
    circle.setAttribute("cy", point.y);
    circle.setAttribute("r", node.kind === "port" ? "23" : "22");
    circle.setAttribute("fill", "#ed1018");
    circle.setAttribute("stroke", "#fff");
    circle.setAttribute("stroke-width", "2");
    label.setAttribute("x", point.x);
    label.setAttribute("y", point.y + 4);
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("font-family", "Segoe UI, Arial, sans-serif");
    label.setAttribute("font-size", "14");
    label.setAttribute("font-weight", "600");
    label.setAttribute("fill", "#17191b");
    label.textContent = node.label;
    group.append(circle, label);
    svg.appendChild(group);
  });
}

function renderMatrix() {
  const table = $("couplingMatrix");
  const matrix = workspace.result.matrix;
  table.textContent = "";

  const header = document.createElement("tr");
  header.appendChild(document.createElement("th"));
  matrix.labels.forEach((label) => {
    const cell = document.createElement("th");
    cell.textContent = label;
    header.appendChild(cell);
  });
  table.appendChild(header);

  matrix.values.forEach((row, rowIndex) => {
    const tr = document.createElement("tr");
    const heading = document.createElement("th");
    heading.textContent = matrix.labels[rowIndex];
    tr.appendChild(heading);
    row.forEach((value, columnIndex) => {
      const cell = document.createElement("td");
      const isDiagonal = rowIndex === columnIndex;
      cell.classList.toggle("diagonal", isDiagonal);
      cell.classList.toggle("nonzero", !isDiagonal && Math.abs(value) > 1e-8);
      cell.classList.toggle(
        "selected",
        workspace.selectedCell?.row === rowIndex &&
          workspace.selectedCell?.column === columnIndex
      );
      cell.dataset.row = rowIndex;
      cell.dataset.column = columnIndex;

      if (workspace.matrixEditing) {
        const input = document.createElement("input");
        input.type = "number";
        input.step = "0.0001";
        input.value = formatMatrixValue(value);
        input.addEventListener("focus", () => selectMatrixCell(rowIndex, columnIndex));
        input.addEventListener("change", () => {
          updateMatrixValue(rowIndex, columnIndex, Number(input.value));
        });
        cell.appendChild(input);
      } else {
        cell.textContent = formatMatrixValue(value);
        cell.addEventListener("click", () => selectMatrixCell(rowIndex, columnIndex));
      }
      tr.appendChild(cell);
    });
    table.appendChild(tr);
  });
}

function formatMatrixValue(value) {
  return Math.abs(value) < 1e-8 ? "0" : Number(value).toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

function selectMatrixCell(row, column) {
  workspace.selectedCell = {row, column};
  renderMatrix();
}

function updateMatrixValue(row, column, value) {
  if (!Number.isFinite(value)) return;
  const values = workspace.result.matrix.values;
  values[row][column] = value;
  values[column][row] = value;
  setDirty();
  renderMatrix();
}

function renderSpecification() {
  const target = $("specificationList");
  const spec = workspace.result.specification;
  const summary = workspace.result.summary;
  const rows = [
    ["Filter type", spec.filter_type],
    ["Order", String(spec.order)],
    ["Center frequency", `${spec.effective_f0_ghz.toFixed(6)} GHz`],
    ["Bandwidth", `${spec.effective_bandwidth_ghz.toFixed(6)} GHz`],
    ["Return loss", `${spec.return_loss_db.toFixed(2)} dB`],
    ["Frequency span", `${spec.start_ghz.toFixed(6)} - ${spec.stop_ghz.toFixed(6)} GHz`],
    ["Transmission zeros", String(workspace.zeros.length)],
    ["Center insertion loss", `${summary.center_insertion_loss_db.toFixed(4)} dB`],
    ["Minimum S11", `${summary.minimum_s11_db.toFixed(3)} dB`],
    ["Dispersion", workspace.dispersion]
  ];
  target.textContent = "";
  rows.forEach(([label, value]) => {
    const term = document.createElement("dt");
    const description = document.createElement("dd");
    term.textContent = label;
    description.textContent = value;
    target.append(term, description);
  });
}

function renderDispersionSummary() {
  const dispersion = workspace.result.dispersion;
  $("inputGroupDelay").textContent = dispersion.input_group_delay_ns.toFixed(3);
  $("outputGroupDelay").textContent = dispersion.output_group_delay_ns.toFixed(3);
}

function chartGeometry() {
  const canvas = $("responseChart");
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(280, rect.width);
  const height = Math.max(240, rect.height);
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return {
    canvas,
    context,
    width,
    height,
    plot: {left: 58, right: width - 18, top: 22, bottom: height - 38}
  };
}

function chartDefinition() {
  const series = workspace.result.series;
  if (workspace.chartMode === "groupdelay") {
    const maximum = Math.max(...series.group_delay_ns, 1);
    return {
      title: "Group Delay",
      axis: "Delay (ns)",
      minimum: 0,
      maximum: maximum * 1.12,
      lines: [{key: "groupDelay", values: series.group_delay_ns, color: "#0c728c", label: "Group Delay"}]
    };
  }
  if (workspace.chartMode === "power") {
    const maximum = Math.max(...series.power_w, 0.1);
    return {
      title: "Power Analysis",
      axis: "Power (W)",
      minimum: 0,
      maximum: maximum * 1.1,
      lines: [{key: "power", values: series.power_w, color: "#d4831d", label: "Delivered Power"}]
    };
  }
  const lines = [];
  if (workspace.visibleSeries.has("s11")) {
    lines.push({key: "s11", values: series.s11_db, color: "#62aefa", label: "Matrix - S11"});
  }
  if (workspace.visibleSeries.has("s21")) {
    lines.push({key: "s21", values: series.s21_db, color: "#ff4b87", label: "Matrix - S21"});
  }
  if (workspace.visibleSeries.has("s22")) {
    lines.push({key: "s22", values: series.s22_db, color: "#a7afb7", label: "Matrix - S22"});
  }
  if (workspace.measurement.length) {
    lines.push({
      key: "measured",
      values: interpolateMeasurement(series.frequencies_ghz),
      color: "#1e7554",
      label: "VNA - S11",
      dashed: true
    });
  }
  return {
    title: "S-Parameter",
    axis: "Magnitude (dB)",
    minimum: workspace.chartFloor,
    maximum: 5,
    lines
  };
}

function interpolateMeasurement(frequencies) {
  if (!workspace.measurement.length) return [];
  return frequencies.map((frequency) => {
    const targetHz = frequency * 1e9;
    let best = workspace.measurement[0];
    let distance = Math.abs(best.freq_hz - targetHz);
    for (const point of workspace.measurement) {
      const nextDistance = Math.abs(point.freq_hz - targetHz);
      if (nextDistance < distance) {
        best = point;
        distance = nextDistance;
      }
    }
    return best.s11_db;
  });
}

function drawChart() {
  if (!workspace.result) return;
  const {context: ctx, width, height, plot} = chartGeometry();
  const definition = chartDefinition();
  const frequencies = workspace.result.series.frequencies_ghz;
  const frequencyStart = frequencies[0];
  const frequencyStop = frequencies[frequencies.length - 1];
  const plotWidth = plot.right - plot.left;
  const plotHeight = plot.bottom - plot.top;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#dcecf8";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "rgba(255,255,255,0.95)";
  ctx.lineWidth = 1;
  ctx.font = "9px Segoe UI, Arial";
  ctx.fillStyle = "#5d6e7c";

  for (let index = 0; index <= 10; index += 1) {
    const x = plot.left + plotWidth * index / 10;
    ctx.beginPath();
    ctx.moveTo(x, plot.top);
    ctx.lineTo(x, plot.bottom);
    ctx.stroke();
    const frequency = frequencyStart + (frequencyStop - frequencyStart) * index / 10;
    ctx.textAlign = "center";
    ctx.fillText(trimNumber(frequency, 4), x, plot.bottom + 17);
  }

  for (let index = 0; index <= 7; index += 1) {
    const y = plot.top + plotHeight * index / 7;
    ctx.beginPath();
    ctx.moveTo(plot.left, y);
    ctx.lineTo(plot.right, y);
    ctx.stroke();
    const value = definition.maximum -
      (definition.maximum - definition.minimum) * index / 7;
    ctx.textAlign = "right";
    ctx.fillText(trimNumber(value, definition.maximum <= 1 ? 3 : 1), plot.left - 8, y + 3);
  }

  ctx.fillStyle = "#506271";
  ctx.textAlign = "center";
  ctx.fillText("Frequency (GHz)", plot.left + plotWidth / 2, height - 8);
  ctx.save();
  ctx.translate(13, plot.top + plotHeight / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText(definition.axis, 0, 0);
  ctx.restore();

  definition.lines.forEach((line) => {
    ctx.save();
    ctx.strokeStyle = line.color;
    ctx.lineWidth = line.key === "s21" ? 1.7 : 1.35;
    if (line.dashed) ctx.setLineDash([6, 4]);
    ctx.beginPath();
    line.values.forEach((value, index) => {
      const x = plot.left + plotWidth * index / Math.max(line.values.length - 1, 1);
      const clipped = Math.max(definition.minimum, Math.min(definition.maximum, value));
      const y = plot.top +
        (definition.maximum - clipped) /
        Math.max(definition.maximum - definition.minimum, 1e-9) *
        plotHeight;
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.restore();
  });

  if (workspace.markerEnabled && workspace.markerIndex !== null) {
    const markerIndex = Math.max(0, Math.min(frequencies.length - 1, workspace.markerIndex));
    const x = plot.left + plotWidth * markerIndex / Math.max(frequencies.length - 1, 1);
    ctx.strokeStyle = "#2b3035";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(x, plot.top);
    ctx.lineTo(x, plot.bottom);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "#2b3035";
    ctx.fillRect(x - 3, plot.top - 2, 6, 6);
  }

  $("chartTitle").textContent = definition.title;
}

function trimNumber(value, decimals) {
  return Number(value).toFixed(decimals).replace(/0+$/, "").replace(/\.$/, "");
}

function chartIndexFromEvent(event) {
  if (!workspace.result) return null;
  const rect = $("responseChart").getBoundingClientRect();
  const left = 58;
  const right = rect.width - 18;
  const x = Math.max(left, Math.min(right, event.clientX - rect.left));
  const count = workspace.result.series.frequencies_ghz.length;
  return Math.round((x - left) / Math.max(right - left, 1) * (count - 1));
}

function showChartTooltip(event) {
  const index = chartIndexFromEvent(event);
  if (index === null) return;
  const tooltip = $("chartTooltip");
  const series = workspace.result.series;
  const frequency = series.frequencies_ghz[index];
  let lines = [`${frequency.toFixed(6)} GHz`];
  if (workspace.chartMode === "sparameter") {
    lines = [
      ...lines,
      `S11 ${series.s11_db[index].toFixed(3)} dB`,
      `S21 ${series.s21_db[index].toFixed(3)} dB`
    ];
  } else if (workspace.chartMode === "groupdelay") {
    lines.push(`GD ${series.group_delay_ns[index].toFixed(4)} ns`);
  } else {
    lines.push(`Power ${series.power_w[index].toFixed(6)} W`);
  }
  const stage = event.currentTarget.parentElement;
  const stageRect = stage.getBoundingClientRect();
  tooltip.textContent = lines.join("\n");
  tooltip.style.whiteSpace = "pre-line";
  tooltip.style.display = "block";
  tooltip.style.left = `${Math.min(event.clientX - stageRect.left + 12, stageRect.width - 130)}px`;
  tooltip.style.top = `${Math.max(8, event.clientY - stageRect.top - 44)}px`;
}

function addTransmissionZero() {
  const center = numericValue("f0Ghz", 1);
  const bandwidth = numericValue("bandwidthGhz", 0.05);
  workspace.zeros.push({
    id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${workspace.zeros.length}`,
    frequency_ghz: Number((center + bandwidth * (1.35 + workspace.zeros.length * 0.35)).toFixed(6)),
    depth_db: 60
  });
  renderZeros();
  setDirty();
}

function renderZeros() {
  const target = $("zeroList");
  target.textContent = "";
  if (!workspace.zeros.length) {
    const empty = document.createElement("div");
    empty.className = "zero-empty";
    empty.id = "zeroEmpty";
    empty.textContent = "No finite transmission zeros";
    target.appendChild(empty);
    return;
  }
  workspace.zeros.forEach((zero, index) => {
    const row = document.createElement("div");
    row.className = "zero-row";

    const number = document.createElement("span");
    number.textContent = `Z${index + 1}`;
    const frequency = document.createElement("input");
    frequency.type = "number";
    frequency.step = "0.001";
    frequency.value = zero.frequency_ghz;
    frequency.title = "Frequency in GHz";
    const depthLabel = document.createElement("span");
    depthLabel.textContent = "dB";
    const depth = document.createElement("input");
    depth.type = "number";
    depth.step = "1";
    depth.value = zero.depth_db;
    depth.title = "Zero depth in dB";
    const remove = document.createElement("button");
    remove.textContent = "x";
    remove.title = "Remove transmission zero";

    frequency.addEventListener("change", () => {
      zero.frequency_ghz = Number(frequency.value);
      setDirty();
    });
    depth.addEventListener("change", () => {
      zero.depth_db = Number(depth.value);
      setDirty();
    });
    remove.addEventListener("click", () => {
      workspace.zeros = workspace.zeros.filter((item) => item.id !== zero.id);
      renderZeros();
      setDirty();
    });

    row.append(number, frequency, depthLabel, depth, remove);
    target.appendChild(row);
  });
}

async function refreshState({quiet = false} = {}) {
  try {
    const state = await getJson("/api/state");
    updateAdapterState("aedt", state.aedt?.state);
    updateAdapterState("vna", state.vna?.state);
    if (!quiet) showToast("Integration state refreshed");
  } catch (error) {
    showToast(error.message, true);
  }
}

function updateAdapterState(prefix, adapter) {
  const connected = Boolean(adapter?.connected);
  const backend = adapter?.backend || "offline";
  $(`${prefix}State`).textContent = connected
    ? backend.toUpperCase().slice(0, 7)
    : backend === "simulated" ? "SIM" : "OFF";
  const dot = $(`${prefix}Dot`);
  dot.classList.toggle("connected", connected);
  dot.classList.toggle("simulated", !connected && backend === "simulated");
}

function openIntegration(view = "aedtView") {
  $("integrationDialog").showModal();
  activateIntegrationView(view);
}

function activateIntegrationView(view) {
  document.querySelectorAll(".integration-view").forEach((panel) => {
    panel.classList.toggle("active", panel.id === view);
  });
  document.querySelectorAll(".integration-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.integrationView === view);
  });
}

async function openAedt() {
  const backend = $("aedtBackend").value;
  const payload = {
    backend,
    design_name: $("aedtDesign").value,
    project_path: backend === "simulated" ? null : $("aedtProject").value
  };
  try {
    setOperation("Opening AEDT project...");
    await postJson("/aedt/openproject", payload);
    await refreshState({quiet: true});
    setOperation("AEDT project session ready");
    showToast("AEDT session ready");
  } catch (error) {
    setOperation(`AEDT error: ${error.message}`);
    showToast(error.message, true);
  }
}

async function loadVariables() {
  try {
    const data = await postJson("/aedt/getvariables", {});
    $("variablesJson").value = JSON.stringify(data.variables || {}, null, 2);
    setOperation("AEDT variables loaded");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function setVariables() {
  try {
    const variables = JSON.parse($("variablesJson").value || "{}");
    await postJson("/aedt/setvariablesvalue", {variables});
    setOperation("AEDT variables applied");
    showToast("Variables applied");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function evaluateAedt() {
  try {
    const variables = JSON.parse($("variablesJson").value || "{}");
    setOperation("Running AEDT analysis...");
    await postJson("/aedt/evaluatedimension", {
      variables,
      output_touchstone: $("aedtOutput").value
    });
    setOperation("AEDT analysis completed");
    showToast("AEDT analysis completed");
  } catch (error) {
    setOperation(`AEDT error: ${error.message}`);
    showToast(error.message, true);
  }
}

async function connectVna() {
  const backend = $("vnaBackend").value;
  const payload = {
    backend,
    brand: backend === "simulated" ? "SIM" : $("vnaBrand").value,
    resource: $("vnaResource").value.trim() || undefined
  };
  try {
    setOperation("Connecting VNA...");
    await postJson("/connect", payload);
    await refreshState({quiet: true});
    setOperation("VNA connected");
    showToast("VNA connected");
  } catch (error) {
    setOperation(`VNA error: ${error.message}`);
    showToast(error.message, true);
  }
}

async function applySweep() {
  try {
    setOperation("Configuring VNA sweep...");
    await postJson("/api/vna/setfrequency", {
      start_hz: numericValue("startGhz", 0.875) * 1e9,
      stop_hz: numericValue("stopGhz", 1.125) * 1e9
    });
    await postJson("/api/vna/setsweeppoints", {points: numericValue("vnaPoints", 401)});
    await postJson("/api/vna/setifbw", {ifbw_hz: numericValue("vnaIfbw", 1000)});
    await postJson("/api/vna/setpower", {power_dbm: numericValue("vnaPower", -10)});
    setOperation("VNA sweep configured");
    showToast("Sweep configuration applied");
  } catch (error) {
    setOperation(`VNA error: ${error.message}`);
    showToast(error.message, true);
  }
}

async function singleSweep() {
  try {
    setOperation("Acquiring VNA sweep...");
    const data = await postJson("/singlesweep", {});
    workspace.measurement = data.data || [];
    workspace.chartMode = "sparameter";
    activateChartTab("sparameter");
    drawChart();
    setOperation(`VNA sweep acquired: ${workspace.measurement.length} points`);
    showToast("VNA trace added to chart");
  } catch (error) {
    setOperation(`VNA error: ${error.message}`);
    showToast(error.message, true);
  }
}

async function saveTrace() {
  try {
    const data = await postJson("/savetracedata", {filePath: $("vnaOutput").value});
    setOperation(`VNA trace saved: ${data.path || $("vnaOutput").value}`);
    showToast("Touchstone file saved");
  } catch (error) {
    showToast(error.message, true);
  }
}

function saveProject() {
  const project = {
    format: "hfss-filter-studio-project",
    version: 1,
    saved_at: new Date().toISOString(),
    specification: currentSpecification(),
    matrix: workspace.result?.matrix || null
  };
  downloadFile(
    `hfss-filter-${workspace.filterType.toLowerCase()}.json`,
    JSON.stringify(project, null, 2),
    "application/json"
  );
  setDirty(false);
  setOperation("Project exported to JSON");
  showToast("Project saved");
}

function loadProjectFile(file) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = async () => {
    try {
      const project = JSON.parse(String(reader.result));
      if (project.format !== "hfss-filter-studio-project") {
        throw new Error("Unsupported project file");
      }
      applySpecification(project.specification || {});
      await calculateAll({quiet: true});
      if (project.matrix?.values && workspace.result) {
        workspace.result.matrix = project.matrix;
        renderMatrix();
      }
      setDirty(false);
      setOperation(`Project loaded: ${file.name}`);
      showToast("Project loaded");
    } catch (error) {
      showToast(error.message, true);
    }
  };
  reader.readAsText(file);
}

function applySpecification(spec) {
  const values = {
    filterOrder: spec.order,
    returnLoss: spec.return_loss_db,
    f0Ghz: spec.f0_ghz,
    bandwidthGhz: spec.bandwidth_ghz,
    startGhz: spec.start_ghz,
    stopGhz: spec.stop_ghz,
    shiftMhz: spec.shift_mhz,
    deltaBandwidthMhz: spec.delta_bandwidth_mhz,
    unloadedQ: spec.unloaded_q === null || spec.unloaded_q === undefined
      ? "Infinity"
      : spec.unloaded_q,
    dispersionValue: spec.dispersion_value
  };
  Object.entries(values).forEach(([id, value]) => {
    if (value !== undefined && $(id)) $(id).value = value;
  });
  workspace.filterType = spec.filter_type || "BPF";
  workspace.dispersion = spec.dispersion || "symmetric";
  workspace.zeros = (spec.zeros || []).map((zero, index) => ({
    id: `${Date.now()}-${index}`,
    frequency_ghz: Number(zero.frequency_ghz),
    depth_db: Number(zero.depth_db)
  }));
  document.querySelectorAll(".mode-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.filterType === workspace.filterType);
  });
  document.querySelectorAll(".dispersion-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.dispersion === workspace.dispersion);
  });
  renderZeros();
}

function exportMatrix() {
  if (!workspace.result) return;
  const matrix = workspace.result.matrix;
  const rows = [
    ["", ...matrix.labels],
    ...matrix.values.map((row, index) => [matrix.labels[index], ...row])
  ];
  const csv = rows.map((row) => row.join(",")).join("\r\n");
  downloadFile("coupling-matrix.csv", csv, "text/csv");
  showToast("Coupling matrix exported");
}

function downloadFile(name, content, type) {
  const blob = new Blob([content], {type});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function activateChartTab(mode) {
  workspace.chartMode = mode;
  document.querySelectorAll(".result-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.chartMode === mode);
  });
  $("chartLegend").style.visibility = mode === "sparameter" ? "visible" : "hidden";
  drawChart();
}

function resetInputs() {
  applySpecification({
    filter_type: "BPF",
    order: 4,
    return_loss_db: 25,
    f0_ghz: 1,
    bandwidth_ghz: 0.05,
    start_ghz: 0.875,
    stop_ghz: 1.125,
    shift_mhz: 0,
    delta_bandwidth_mhz: 0,
    unloaded_q: null,
    dispersion: "symmetric",
    dispersion_value: 0,
    zeros: []
  });
  setDirty();
  calculateAll({quiet: true});
}

function editSelectedSign() {
  if (!workspace.result || !workspace.selectedCell) {
    showToast("Select a matrix cell first", true);
    return;
  }
  const {row, column} = workspace.selectedCell;
  const values = workspace.result.matrix.values;
  values[row][column] *= -1;
  values[column][row] = values[row][column];
  setDirty();
  renderMatrix();
}

function bindEvents() {
  $("calculateAll").addEventListener("click", () => calculateAll());
  $("refreshState").addEventListener("click", () => refreshState());
  $("saveProject").addEventListener("click", saveProject);
  $("saveMenu").addEventListener("click", () => showToast("Project JSON includes specification and matrix"));
  $("resetInput").addEventListener("click", resetInputs);
  $("applyShift").addEventListener("click", () => calculateAll());
  $("addZero").addEventListener("click", addTransmissionZero);
  $("applyDispersion").addEventListener("click", () => calculateAll());
  $("editTopology").addEventListener("click", () => showToast("Topology follows order, zeros and matrix couplings"));
  $("matrixFit").addEventListener("click", renderMatrix);
  $("exportMatrix").addEventListener("click", exportMatrix);
  $("loadProject").addEventListener("click", () => $("projectFile").click());
  $("projectFile").addEventListener("change", (event) => loadProjectFile(event.target.files[0]));
  $("editSign").addEventListener("click", editSelectedSign);
  $("editMatrix").addEventListener("click", () => {
    workspace.matrixEditing = !workspace.matrixEditing;
    $("editMatrix").classList.toggle("active", workspace.matrixEditing);
    $("editMatrix").textContent = workspace.matrixEditing ? "Finish Edit" : "Edit Matrix";
    renderMatrix();
  });

  document.querySelectorAll(".mode-button").forEach((button) => {
    button.addEventListener("click", () => {
      workspace.filterType = button.dataset.filterType;
      document.querySelectorAll(".mode-button").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      setDirty();
      calculateAll({quiet: true});
    });
  });

  document.querySelectorAll(".dispersion-button").forEach((button) => {
    button.addEventListener("click", () => {
      workspace.dispersion = button.dataset.dispersion;
      document.querySelectorAll(".dispersion-button").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      setDirty();
    });
  });

  document.querySelectorAll(".result-tab").forEach((tab) => {
    tab.addEventListener("click", () => activateChartTab(tab.dataset.chartMode));
  });

  document.querySelectorAll(".matrix-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const matrixActive = tab.dataset.matrixTab === "matrix";
      document.querySelectorAll(".matrix-tab").forEach((item) => {
        item.classList.toggle("active", item === tab);
      });
      $("matrixContent").classList.toggle("active", matrixActive);
      $("specificationContent").classList.toggle("active", !matrixActive);
    });
  });

  document.querySelectorAll(".legend-item").forEach((button) => {
    button.addEventListener("click", () => {
      const series = button.dataset.series;
      if (workspace.visibleSeries.has(series)) workspace.visibleSeries.delete(series);
      else workspace.visibleSeries.add(series);
      button.classList.toggle("active", workspace.visibleSeries.has(series));
      drawChart();
    });
  });

  document.querySelectorAll("[data-nav-toggle]").forEach((button) => {
    button.addEventListener("click", () => button.parentElement.classList.toggle("open"));
  });

  document.querySelectorAll("[data-module]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.module === "single") return;
      showToast(`${button.textContent.trim()} module is staged for the next implementation phase`);
    });
  });

  document.querySelectorAll(".row-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      button.classList.toggle("active");
      const input = $(button.dataset.toggleTarget);
      input.disabled = !button.classList.contains("active");
      setDirty();
    });
  });

  document.querySelectorAll(
    ".input-panel input, .input-panel select, .zeros-panel select, .dispersion-modes input"
  ).forEach((input) => input.addEventListener("change", () => setDirty()));

  $("toggleSetup").addEventListener("click", () => {
    const workspaceElement = document.querySelector(".engineering-workspace");
    const collapsed = workspaceElement.classList.toggle("setup-collapsed");
    $("toggleSetup").textContent = collapsed ? "v" : "^";
    setTimeout(drawChart, 140);
  });

  $("toggleMarker").addEventListener("click", () => {
    workspace.markerEnabled = !workspace.markerEnabled;
    $("toggleMarker").classList.toggle("active", workspace.markerEnabled);
    if (workspace.markerEnabled && workspace.result) {
      workspace.markerIndex = Math.floor(workspace.result.series.frequencies_ghz.length / 2);
    }
    drawChart();
  });

  $("matrixMarker").addEventListener("click", () => $("toggleMarker").click());
  $("setChartFloor").addEventListener("click", () => {
    workspace.chartFloor = numericValue("chartFloor", -70);
    drawChart();
  });
  $("resetChart").addEventListener("click", () => {
    workspace.chartFloor = -70;
    $("chartFloor").value = -70;
    workspace.markerIndex = null;
    drawChart();
  });

  const chart = $("responseChart");
  chart.addEventListener("mousemove", showChartTooltip);
  chart.addEventListener("mouseleave", () => {
    $("chartTooltip").style.display = "none";
  });
  chart.addEventListener("click", (event) => {
    if (!workspace.markerEnabled) return;
    workspace.markerIndex = chartIndexFromEvent(event);
    drawChart();
  });

  $("openIntegration").addEventListener("click", () => openIntegration("aedtView"));
  $("closeIntegration").addEventListener("click", () => $("integrationDialog").close());
  $("integrationDialog").addEventListener("click", (event) => {
    if (event.target === $("integrationDialog")) $("integrationDialog").close();
  });
  document.querySelectorAll("[data-integration-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      openIntegration(button.dataset.integrationTab === "vna" ? "vnaView" : "aedtView");
    });
  });
  document.querySelectorAll(".integration-tab").forEach((button) => {
    button.addEventListener("click", () => activateIntegrationView(button.dataset.integrationView));
  });

  $("openAedt").addEventListener("click", openAedt);
  $("loadVariables").addEventListener("click", loadVariables);
  $("setVariables").addEventListener("click", setVariables);
  $("evaluateAedt").addEventListener("click", evaluateAedt);
  $("connectVna").addEventListener("click", connectVna);
  $("applySweep").addEventListener("click", applySweep);
  $("singleSweep").addEventListener("click", singleSweep);
  $("saveTrace").addEventListener("click", saveTrace);

  new ResizeObserver(() => drawChart()).observe(document.querySelector(".chart-stage"));
  window.addEventListener("keydown", (event) => {
    if (event.ctrlKey && event.key.toLowerCase() === "s") {
      event.preventDefault();
      saveProject();
    }
    if (event.key === "F5") {
      event.preventDefault();
      calculateAll();
    }
  });
}

function updateClock() {
  $("clock").textContent = new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit"
  });
}

async function initialize() {
  bindEvents();
  renderZeros();
  updateClock();
  setInterval(updateClock, 30000);
  await Promise.all([
    refreshState({quiet: true}),
    calculateAll({quiet: true})
  ]);
}

document.addEventListener("DOMContentLoaded", initialize);
