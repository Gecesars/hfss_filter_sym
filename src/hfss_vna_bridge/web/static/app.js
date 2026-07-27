const workspace = {
  filterType: "BPF",
  dispersion: "symmetric",
  zeros: [],
  result: null,
  measurement: [],
  hfssMeasurement: [],
  chartMode: "sparameter",
  chartFloor: -70,
  visibleSeries: new Set(["s11", "s21", "hfss", "vna"]),
  markerEnabled: false,
  markerIndex: null,
  matrixEditing: false,
  selectedCell: null,
  selectedJob: null,
  activeModule: "single",
  selectedProject: null,
  selectedLibrary: null,
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
  if (!response.ok || data.ok === false) {
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

async function evaluateEditedMatrix() {
  if (!workspace.result?.matrix) return;
  try {
    setOperation("Evaluating coupling matrix...");
    const data = await postJson("/api/synthesis/matrix-response", {
      specification: currentSpecification(),
      matrix: workspace.result.matrix
    });
    workspace.result.series = data.series;
    workspace.result.engine = data.engine;
    workspace.result.summary = {
      ...workspace.result.summary,
      ...data.summary
    };
    drawChart();
    renderSpecification();
    setOperation("Coupling matrix response updated");
    showToast("Matrix response updated");
  } catch (error) {
    setOperation(`Matrix evaluation failed: ${error.message}`);
    showToast(error.message, true);
  }
}

function renderSpecification() {
  const target = $("specificationList");
  const spec = workspace.result.specification;
  const summary = workspace.result.summary;
  const prototype = workspace.result.prototype || {};
  const rows = [
    ["Filter type", spec.filter_type],
    ["Prototype", `${prototype.family || spec.response_family} / order ${spec.order}`],
    ["Order", String(spec.order)],
    ["Center frequency", `${spec.effective_f0_ghz.toFixed(6)} GHz`],
    ["Bandwidth", `${spec.effective_bandwidth_ghz.toFixed(6)} GHz`],
    ["Return loss", `${spec.return_loss_db.toFixed(2)} dB`],
    ["Achieved return loss", `${summary.achieved_return_loss_db.toFixed(3)} dB`],
    ["Prototype ripple", `${prototype.passband_ripple_db.toFixed(6)} dB`],
    ["Frequency span", `${spec.start_ghz.toFixed(6)} - ${spec.stop_ghz.toFixed(6)} GHz`],
    ["Transmission zeros", String(workspace.zeros.length)],
    ["Center insertion loss", `${summary.center_insertion_loss_db.toFixed(4)} dB`],
    ["External Q", `${summary.input_external_q.toFixed(4)} / ${summary.output_external_q.toFixed(4)}`],
    ["Lumped elements", String((workspace.result.elements || []).length)],
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
  if (workspace.hfssMeasurement.length && workspace.visibleSeries.has("hfss")) {
    lines.push({
      key: "hfssS11",
      values: interpolateNetwork(workspace.hfssMeasurement, series.frequencies_ghz, "s11_db"),
      color: "#7a4aa5",
      label: "HFSS - S11",
      dashed: true
    });
    lines.push({
      key: "hfssS21",
      values: interpolateNetwork(workspace.hfssMeasurement, series.frequencies_ghz, "s21_db"),
      color: "#ad76c5",
      label: "HFSS - S21",
      dashed: true
    });
  }
  if (workspace.measurement.length && workspace.visibleSeries.has("vna")) {
    lines.push({
      key: "vnaS11",
      values: interpolateNetwork(workspace.measurement, series.frequencies_ghz, "s11_db"),
      color: "#1e7554",
      label: "VNA - S11",
      dashed: true
    });
    lines.push({
      key: "vnaS21",
      values: interpolateNetwork(workspace.measurement, series.frequencies_ghz, "s21_db"),
      color: "#d4831d",
      label: "VNA - S21",
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

function interpolateNetwork(network, frequencies, parameter) {
  if (!network.length) return [];
  return frequencies.map((frequency) => {
    const targetHz = frequency * 1e9;
    let best = network[0];
    let distance = Math.abs(best.freq_hz - targetHz);
    for (const point of network) {
      const nextDistance = Math.abs(point.freq_hz - targetHz);
      if (nextDistance < distance) {
        best = point;
        distance = nextDistance;
      }
    }
    return Number(best[parameter] ?? -300);
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
  const processId = numericValue("aedtProcessId", 0);
  const grpcPort = numericValue("aedtGrpcPort", 0);
  const payload = {
    backend,
    design_name: $("aedtDesign").value,
    project_path: backend === "simulated" ? null : $("aedtProject").value,
    version: $("aedtVersion").value || "2026.1",
    new_desktop: $("aedtSessionMode").value === "new",
    non_graphical: $("aedtDisplayMode").value === "non_graphical",
    remove_lock: $("aedtRemoveLock").checked,
    machine: grpcPort ? ($("aedtMachine").value.trim() || "localhost") : null,
    port: grpcPort || null,
    aedt_process_id: grpcPort ? null : (processId || null)
  };
  try {
    setOperation("Opening AEDT project...");
    const data = await postJson("/aedt/openproject", payload);
    const session = data.session || {};
    if (session.design_name) $("aedtDesign").value = session.design_name;
    if (session.process_id) $("aedtProcessId").value = session.process_id;
    if (session.grpc_port) $("aedtGrpcPort").value = session.grpc_port;
    if (session.setups?.length) {
      $("aedtSetup").value = session.setups[0];
      const sweeps = session.sweeps?.[session.setups[0]] || [];
      if (sweeps.length) $("aedtSweep").value = sweeps[0];
    }
    await refreshState({quiet: true});
    setOperation(
      `AEDT ${session.version || payload.version} ready - PID ${session.process_id || "attached"}`
    );
    showToast(`AEDT ${session.version || payload.version} session ready`);
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
    const cores = numericValue("aedtCores", 0);
    setOperation("Queueing AEDT analysis...");
    const data = await postJson("/api/jobs", {
      variables,
      setup_name: $("aedtSetup").value.trim() || null,
      sweep_name: $("aedtSweep").value.trim() || null,
      output_touchstone: $("aedtOutput").value,
      cores: cores || null,
      blocking: true
    });
    workspace.selectedJob = data.job?.id || null;
    activateIntegrationView("jobsView");
    await refreshJobs();
    setOperation(`AEDT job queued: ${workspace.selectedJob?.slice(0, 8) || "unknown"}`);
    showToast("AEDT analysis queued");
    if (workspace.selectedJob) pollJob(workspace.selectedJob);
  } catch (error) {
    setOperation(`AEDT error: ${error.message}`);
    showToast(error.message, true);
  }
}

async function configureAedt() {
  try {
    const payload = {
      setup_name: $("aedtSetup").value.trim() || "FilterSetup",
      sweep_name: $("aedtSweep").value.trim() || "FilterSweep",
      f0_ghz: numericValue("f0Ghz", 1),
      start_ghz: numericValue("startGhz", 0.875),
      stop_ghz: numericValue("stopGhz", 1.125),
      points: numericValue("vnaPoints", 401)
    };
    const data = await postJson("/api/aedt/configureanalysis", payload);
    $("aedtSetup").value = data.configuration.setup;
    $("aedtSweep").value = data.configuration.sweep;
    setOperation(`Configured ${data.configuration.setup} : ${data.configuration.sweep}`);
    showToast("HFSS setup configured");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function validateAedt() {
  try {
    const data = await postJson("/api/aedt/validatedesign", {expected_ports: 2});
    logService("HFSS validation", data.validation);
    setOperation(data.validation.valid ? "HFSS design is valid" : "HFSS validation reported issues");
    showToast(data.validation.valid ? "Design validation passed" : "Review validation log", !data.validation.valid);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function exportAedtResults() {
  try {
    const data = await postJson("/api/aedt/exportresults", {output_dir: "data/hfss_results"});
    setOperation(`Exported ${data.files.length} HFSS result files`);
    showToast("HFSS results exported");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function releaseAedt() {
  try {
    const closeDesktop = $("aedtSessionMode").value === "new";
    await postJson("/api/aedt/release", {
      close_projects: closeDesktop,
      close_desktop: closeDesktop
    });
    $("aedtProcessId").value = "";
    $("aedtGrpcPort").value = "";
    await refreshState({quiet: true});
    setOperation("AEDT session released");
    showToast("AEDT session released");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function loadAedtInstallations() {
  try {
    const data = await getJson("/api/aedt/installations");
    const select = $("aedtVersion");
    const current = select.value;
    select.textContent = "";
    (data.installations || []).forEach((installation) => {
      const option = document.createElement("option");
      option.value = installation.version;
      option.textContent = `${installation.version} - ${installation.root}`;
      select.appendChild(option);
    });
    if (!select.options.length) {
      const option = document.createElement("option");
      option.value = "2026.1";
      option.textContent = "2026.1 - not detected";
      select.appendChild(option);
    }
    select.value = data.recommended_version || current || "2026.1";
    const activeSession = (data.running_sessions || []).find(
      (session) => session.version === select.value && session.grpc_port
    );
    if (activeSession) {
      $("aedtSessionMode").value = "attach";
      $("aedtMachine").value = "localhost";
      $("aedtGrpcPort").value = activeSession.grpc_port;
      $("aedtProcessId").value = activeSession.process_id;
      $("aedtDisplayMode").value = activeSession.non_graphical
        ? "non_graphical"
        : "graphical";
    }
    logService("AEDT environment detected", data);
  } catch (error) {
    logService("AEDT environment detection failed", {message: error.message});
  }
}

async function connectVna() {
  const backend = $("vnaBackend").value;
  const payload = {
    backend,
    brand: backend === "simulated" ? "SIM" : $("vnaBrand").value,
    resource: $("vnaResource").value.trim() || undefined,
    visa_library: $("vnaLibrary").value.trim() || undefined,
    channel: numericValue("vnaChannel", 1)
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
    await postJson("/api/vna/setsweeptype", {sweepType: $("vnaSweepType").value});
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

async function discoverVna() {
  try {
    const query = $("vnaLibrary").value.trim();
    const path = query
      ? `/api/vna/resources?visa_library=${encodeURIComponent(query)}`
      : "/api/vna/resources";
    const data = await getJson(path);
    if (data.resources?.length) $("vnaResource").value = data.resources[0];
    logService("VISA resources", data);
    setOperation(`${data.count || 0} VISA resources detected`);
    showToast(`${data.count || 0} VISA resources detected`);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function inspectVna() {
  try {
    const [capabilities, errors] = await Promise.all([
      getJson("/api/vna/capabilities"),
      getJson("/api/vna/errors")
    ]);
    logService("VNA capabilities", capabilities);
    logService("VNA error queue", errors);
    setOperation(`${capabilities.capabilities.profile_name || "VNA"} ready`);
    showToast(errors.errors.length ? `${errors.errors.length} instrument errors` : "Instrument status ready", Boolean(errors.errors.length));
  } catch (error) {
    showToast(error.message, true);
  }
}

async function closeVna() {
  try {
    await postJson("/api/vna/close", {});
    workspace.measurement = [];
    await refreshState({quiet: true});
    drawChart();
    setOperation("VNA session closed");
    showToast("VNA disconnected");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function refreshJobs() {
  try {
    const data = await getJson("/api/jobs");
    renderJobs(data.jobs || []);
  } catch (error) {
    showToast(error.message, true);
  }
}

function renderJobs(jobs) {
  const target = $("jobList");
  target.textContent = "";
  if (!jobs.length) {
    target.textContent = "No jobs";
    return;
  }
  jobs.forEach((job) => {
    const row = document.createElement("button");
    row.className = "job-row";
    row.classList.toggle("selected", workspace.selectedJob === job.id);
    row.type = "button";
    row.innerHTML = `
      <strong>${escapeHtml(job.id.slice(0, 8))}</strong>
      <span>${escapeHtml(job.state)}</span>
      <span>${escapeHtml(job.message || "")}</span>
      <div class="job-progress"><span style="width:${Math.round((job.progress || 0) * 100)}%"></span></div>
      <span>${Math.round((job.progress || 0) * 100)}%</span>
    `;
    row.addEventListener("click", () => {
      workspace.selectedJob = job.id;
      renderJobs(jobs);
      logService(`Job ${job.id}`, job);
    });
    target.appendChild(row);
  });
}

async function cancelActiveJob() {
  if (!workspace.selectedJob) {
    showToast("Select a job first", true);
    return;
  }
  try {
    await postJson(`/api/jobs/${workspace.selectedJob}/cancel`, {});
    await refreshJobs();
    setOperation("Job cancellation requested");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function pollJob(jobId) {
  try {
    const data = await getJson(`/api/jobs/${jobId}`);
    const job = data.job;
    await refreshJobs();
    if (job.state === "completed") {
      const path = job.result?.touchstone;
      if (path) await importTouchstone(path, "hfss");
      setOperation(`AEDT analysis completed: ${job.result?.setup || "setup"}`);
      showToast("AEDT analysis completed");
      return;
    }
    if (["failed", "cancelled"].includes(job.state)) {
      setOperation(`AEDT job ${job.state}: ${job.error || job.message}`);
      showToast(job.error || `AEDT job ${job.state}`, job.state === "failed");
      return;
    }
    setTimeout(() => pollJob(jobId), 1500);
  } catch (error) {
    setOperation(`Job polling failed: ${error.message}`);
  }
}

async function importTouchstone(path, target) {
  const data = await postJson("/api/touchstone/import", {path});
  const points = (data.touchstone.points || []).map((point) => ({
    ...point,
    s11_db: complexDb(point.s11_real, point.s11_imag),
    s21_db: complexDb(point.s21_real, point.s21_imag),
    s12_db: complexDb(point.s12_real, point.s12_imag),
    s22_db: complexDb(point.s22_real, point.s22_imag)
  }));
  if (target === "hfss") workspace.hfssMeasurement = points;
  else workspace.measurement = points;
  drawChart();
  return data.touchstone;
}

function complexDb(real, imaginary) {
  return 20 * Math.log10(Math.max(Math.hypot(Number(real), Number(imaginary)), 1e-15));
}

const MODULES = {
  dipmux: ["Diplexer / Multiplexer", "Multi-channel synthesis"],
  cavity: ["Cavity Modeling", "Parametric HFSS geometry"],
  planar: ["Planar Modeling", "Microstrip, SIW and distributed LPF"],
  cat: ["Computer-Aided Tuning", "Measured response correction"],
  intelligent: ["Intelligent Optimization", "Bounded global search"],
  tuning: ["Filter Tuning", "Target and VNA alignment"],
  montecarlo: ["Monte Carlo", "Tolerance and yield analysis"],
  optimizer: ["Filter Optimization", "Specification objective search"],
  tlcalculator: ["Transmission Line Calculator", "Guided-wave dimensions"],
  projects: ["Project Management", "Versioned local repository"],
  library: ["Engineering Library", "Reusable synthesis and model templates"]
};

async function openEngineeringModule(module) {
  if (module === "single") {
    $("moduleDialog").close();
    return;
  }
  workspace.activeModule = module;
  const [title, subtitle] = MODULES[module] || ["Engineering Module", "HFSS Filter Studio"];
  $("moduleTitle").textContent = title;
  $("moduleSubtitle").textContent = subtitle;
  $("moduleStatus").textContent = "Ready";
  $("moduleSecondary").textContent = "Refresh";
  $("moduleExecute").textContent = "Run";
  renderModule(module);
  $("moduleDialog").showModal();
  if (module === "projects") await loadServerProjects();
  if (module === "library") await loadLibrary();
}

function renderModule(module) {
  if (module === "dipmux") renderMultiplexerModule();
  else if (["cavity", "planar"].includes(module)) renderModelingModule(module);
  else if (["intelligent", "optimizer"].includes(module)) renderOptimizationModule();
  else if (["cat", "tuning"].includes(module)) renderTuningModule();
  else if (module === "montecarlo") renderMonteCarloModule();
  else if (module === "tlcalculator") renderTransmissionLineModule();
  else if (module === "projects") renderProjectsModule();
  else if (module === "library") renderLibraryModule();
}

function moduleWorkspace(form) {
  $("moduleBody").innerHTML = `
    <div class="module-workspace">
      <div class="module-form">${form}</div>
      <div class="module-result">
        <h3>Results</h3>
        <pre id="moduleOutput">Ready</pre>
      </div>
    </div>
  `;
}

function renderMultiplexerModule() {
  moduleWorkspace(`
    <label>Start (GHz)<input id="muxStart" type="number" value="${numericValue("startGhz", 0.875)}" step="0.001"></label>
    <label>Stop (GHz)<input id="muxStop" type="number" value="${numericValue("stopGhz", 1.125)}" step="0.001"></label>
    <label>Points<input id="muxPoints" type="number" value="801" min="101" max="4001"></label>
    <label>Junction<select id="muxJunction"><option value="star">Star</option><option value="manifold">Manifold</option></select></label>
    <div class="channel-editor" id="channelEditor"></div>
    <button class="wide-field" id="addMuxChannel" type="button">Add Channel</button>
  `);
  [
    {name: "CH1", f0: numericValue("f0Ghz", 1) - numericValue("bandwidthGhz", 0.05), bw: numericValue("bandwidthGhz", 0.05), order: 4},
    {name: "CH2", f0: numericValue("f0Ghz", 1) + numericValue("bandwidthGhz", 0.05), bw: numericValue("bandwidthGhz", 0.05), order: 4}
  ].forEach(addMuxChannel);
  $("addMuxChannel").addEventListener("click", () => addMuxChannel());
  $("moduleExecute").textContent = "Synthesize";
}

function addMuxChannel(values = {}) {
  const editor = $("channelEditor");
  const index = editor.children.length + 1;
  const row = document.createElement("div");
  row.className = "channel-row";
  row.innerHTML = `
    <input data-field="name" value="${escapeHtml(values.name || `CH${index}`)}" aria-label="Channel name">
    <input data-field="f0" type="number" value="${values.f0 || 1}" step="0.001" aria-label="Center GHz">
    <input data-field="bw" type="number" value="${values.bw || 0.05}" step="0.001" aria-label="Bandwidth GHz">
    <input data-field="order" type="number" value="${values.order || 4}" min="1" max="12" aria-label="Order">
    <input data-field="rl" type="number" value="${values.rl || 22}" step="0.1" aria-label="Return loss dB">
    <button type="button" title="Remove channel">x</button>
  `;
  row.querySelector("button").addEventListener("click", () => {
    if (editor.children.length > 2) row.remove();
    else showToast("A multiplexer requires at least two channels", true);
  });
  editor.appendChild(row);
}

function renderModelingModule(module) {
  const cavity = module === "cavity";
  moduleWorkspace(`
    <label>Recipe
      <select id="modelRecipe">
        ${cavity
          ? '<option value="cavity">Cavity</option><option value="combline">Combline</option><option value="waveguide">Waveguide</option>'
          : '<option value="planar">Microstrip</option><option value="siw">SIW</option><option value="lpf_step">Stepped LPF</option><option value="lpf_open_stub">Open-stub LPF</option><option value="lpf_elliptic">Elliptic LPF</option>'}
      </select>
    </label>
    <label>Model name<input id="modelName" value="${cavity ? "CavityFilter" : "PlanarFilter"}"></label>
    <label>Order<input id="modelOrder" type="number" min="1" max="24" value="${numericValue("filterOrder", 4)}"></label>
    <label>Length (mm)<input id="modelLength" type="number" value="${cavity ? 120 : 100}" step="0.1"></label>
    <label>${cavity ? "Width" : "Board width"} (mm)<input id="modelWidth" type="number" value="${cavity ? 50 : 40}" step="0.1"></label>
    <label>${cavity ? "Height" : "Substrate height"} (mm)<input id="modelHeight" type="number" value="${cavity ? 25 : 1.524}" step="0.001"></label>
    <label>Setup<input id="modelSetup" value="FilterSetup"></label>
    <label>Sweep<input id="modelSweep" value="FilterSweep"></label>
    <label class="check-field"><input id="modelDryRun" type="checkbox" checked>Preview only</label>
    <label class="check-field"><input id="modelPorts" type="checkbox" checked>Assign two ports</label>
  `);
  $("moduleSecondary").textContent = "Preview";
  $("moduleExecute").textContent = "Build Model";
}

function renderOptimizationModule() {
  moduleWorkspace(`
    <label>Iterations<input id="optimizationIterations" type="number" min="1" max="200" value="12"></label>
    <label>Population<input id="optimizationPopulation" type="number" min="4" max="30" value="8"></label>
    <label>Target center (GHz)<input id="optimizationCenter" type="number" value="${numericValue("f0Ghz", 1)}" step="0.001"></label>
    <label>Target bandwidth (GHz)<input id="optimizationBandwidth" type="number" value="${numericValue("bandwidthGhz", 0.05)}" step="0.001"></label>
    <label>Target return loss (dB)<input id="optimizationReturn" type="number" value="${numericValue("returnLoss", 25)}" step="0.1"></label>
    <label>Maximum IL (dB)<input id="optimizationInsertion" type="number" value="1" step="0.1"></label>
    <label class="wide-field">Variable bounds
      <textarea id="optimizationBounds">{
  "f0_ghz": [${(numericValue("f0Ghz", 1) * 0.95).toFixed(6)}, ${(numericValue("f0Ghz", 1) * 1.05).toFixed(6)}],
  "bandwidth_ghz": [${(numericValue("bandwidthGhz", 0.05) * 0.7).toFixed(6)}, ${(numericValue("bandwidthGhz", 0.05) * 1.3).toFixed(6)}],
  "return_loss_db": [15, 35]
}</textarea>
    </label>
  `);
  $("moduleExecute").textContent = "Optimize";
}

function renderTuningModule() {
  moduleWorkspace(`
    <label>Frequency sensitivity (MHz/turn)<input id="tuneFrequencySensitivity" type="number" value="2" step="0.1"></label>
    <label>Bandwidth sensitivity (MHz/turn)<input id="tuneBandwidthSensitivity" type="number" value="1" step="0.1"></label>
    <label>Return-loss sensitivity (dB/turn)<input id="tuneReturnSensitivity" type="number" value="1" step="0.1"></label>
    <label>Measurement source<select id="tuneSource"><option value="vna">VNA acquisition</option><option value="hfss">HFSS result</option></select></label>
    <label class="wide-field">Reference Touchstone<input id="tuneReferencePath" value="data\\hfss_export.s2p"></label>
    <label class="wide-field">Candidate Touchstone<input id="tuneCandidatePath" value="data\\vna_measurement.s2p"></label>
  `);
  $("moduleSecondary").textContent = "Compare Files";
  $("moduleExecute").textContent = "Calculate Tuning";
}

function renderMonteCarloModule() {
  moduleWorkspace(`
    <label>Samples<input id="mcSamples" type="number" min="10" max="10000" value="250"></label>
    <label>Seed<input id="mcSeed" type="number" value="2026"></label>
    <label>F0 sigma (%)<input id="mcF0" type="number" value="0.2" step="0.01"></label>
    <label>BW sigma (%)<input id="mcBw" type="number" value="3" step="0.1"></label>
    <label>RL sigma (dB)<input id="mcRl" type="number" value="0.5" step="0.1"></label>
    <label>Q sigma (%)<input id="mcQ" type="number" value="5" step="0.1"></label>
    <label>Minimum RL (dB)<input id="mcMinRl" type="number" value="${Math.max(1, numericValue("returnLoss", 25) - 3)}"></label>
    <label>Maximum IL (dB)<input id="mcMaxIl" type="number" value="1.5" step="0.1"></label>
  `);
  $("moduleExecute").textContent = "Run Yield";
}

function renderTransmissionLineModule() {
  moduleWorkspace(`
    <label>Line type
      <select id="tlKind">
        <option value="microstrip">Microstrip</option>
        <option value="stripline">Stripline</option>
        <option value="rectangular_waveguide">Rectangular waveguide</option>
        <option value="siw">SIW</option>
      </select>
    </label>
    <label>Frequency (GHz)<input id="tlFrequency" type="number" value="${numericValue("f0Ghz", 1)}" step="0.001"></label>
    <label>Width / a (mm)<input id="tlWidth" type="number" value="2.9" step="0.001"></label>
    <label>Height / b (mm)<input id="tlHeight" type="number" value="1.6" step="0.001"></label>
    <label>Relative permittivity<input id="tlEr" type="number" value="4.4" step="0.01"></label>
    <label>Conductor thickness (mm)<input id="tlThickness" type="number" value="0.035" step="0.001"></label>
    <label>Via diameter (mm)<input id="tlViaDiameter" type="number" value="0.8" step="0.01"></label>
    <label>Via pitch (mm)<input id="tlViaPitch" type="number" value="1.5" step="0.01"></label>
  `);
  $("moduleExecute").textContent = "Calculate";
}

function renderProjectsModule() {
  moduleWorkspace(`
    <label class="wide-field">Project name<input id="serverProjectName" value="Filter Project"></label>
    <label class="wide-field">Description<textarea id="serverProjectDescription"></textarea></label>
  `);
  $("moduleExecute").textContent = "Save Revision";
}

function renderLibraryModule() {
  moduleWorkspace(`
    <label>Category
      <select id="libraryCategory">
        <option value="">All</option>
        <option value="synthesis">Synthesis</option>
        <option value="cavity">Cavity</option>
        <option value="planar">Planar</option>
      </select>
    </label>
  `);
  $("libraryCategory").addEventListener("change", loadLibrary);
  $("moduleExecute").textContent = "Use Selected";
}

async function runActiveModule() {
  const module = workspace.activeModule;
  try {
    setModuleStatus("Running...");
    let data;
    if (module === "dipmux") data = await runMultiplexer();
    else if (["cavity", "planar"].includes(module)) data = await runModeling(false);
    else if (["intelligent", "optimizer"].includes(module)) data = await runOptimization();
    else if (["cat", "tuning"].includes(module)) data = await runTuning();
    else if (module === "montecarlo") data = await runMonteCarlo();
    else if (module === "tlcalculator") data = await runTransmissionLine();
    else if (module === "projects") data = await saveServerProject();
    else if (module === "library") data = await useLibraryEntry();
    if (data) setModuleOutput(data);
    setModuleStatus("Completed");
  } catch (error) {
    setModuleStatus(error.message);
    showToast(error.message, true);
  }
}

async function refreshActiveModule() {
  const module = workspace.activeModule;
  if (["cavity", "planar"].includes(module)) {
    const data = await runModeling(true);
    setModuleOutput(data);
  } else if (["cat", "tuning"].includes(module)) {
    const reference = $("tuneReferencePath").value.trim();
    const candidate = $("tuneCandidatePath").value.trim();
    const data = await postJson("/api/analysis/compare", {
      reference_path: reference,
      candidate_path: candidate
    });
    setModuleOutput(data);
  } else if (module === "projects") await loadServerProjects();
  else if (module === "library") await loadLibrary();
  else setModuleOutput({status: 0, specification: currentSpecification()});
}

async function runMultiplexer() {
  const channels = [...document.querySelectorAll(".channel-row")].map((row) => ({
    name: row.querySelector('[data-field="name"]').value,
    f0_ghz: Number(row.querySelector('[data-field="f0"]').value),
    bandwidth_ghz: Number(row.querySelector('[data-field="bw"]').value),
    order: Number(row.querySelector('[data-field="order"]').value),
    return_loss_db: Number(row.querySelector('[data-field="rl"]').value)
  }));
  return postJson("/api/synthesis/multiplexer", {
    channels,
    start_ghz: numericValue("muxStart", 0.8),
    stop_ghz: numericValue("muxStop", 1.2),
    points: numericValue("muxPoints", 801),
    junction: $("muxJunction").value
  });
}

function modelingPayload(preview) {
  const cavity = workspace.activeModule === "cavity";
  return {
    method: cavity ? "buildcavityfull3d" : "planarupdatemodel",
    recipe: $("modelRecipe").value,
    name: $("modelName").value,
    order: numericValue("modelOrder", 4),
    length_mm: numericValue("modelLength", cavity ? 120 : 100),
    width_mm: numericValue("modelWidth", 50),
    board_width_mm: numericValue("modelWidth", 40),
    height_mm: numericValue("modelHeight", 25),
    substrate_height_mm: numericValue("modelHeight", 1.524),
    setup_name: $("modelSetup").value,
    sweep_name: $("modelSweep").value,
    f0_ghz: numericValue("f0Ghz", 1),
    start_ghz: numericValue("startGhz", 0.875),
    stop_ghz: numericValue("stopGhz", 1.125),
    points: 401,
    dry_run: preview || $("modelDryRun").checked,
    assign_ports: $("modelPorts").checked
  };
}

async function runModeling(preview) {
  const payload = modelingPayload(preview);
  if (payload.dry_run) return postJson("/api/modeling/plan", payload);
  return postJson(`/api/hfss/${payload.method}`, payload);
}

async function runOptimization() {
  return postJson("/api/engineering/optimize", {
    specification: currentSpecification(),
    targets: {
      center_ghz: numericValue("optimizationCenter", 1),
      bandwidth_ghz: numericValue("optimizationBandwidth", 0.05),
      return_loss_db: numericValue("optimizationReturn", 25),
      maximum_insertion_loss_db: numericValue("optimizationInsertion", 1)
    },
    variables: JSON.parse($("optimizationBounds").value),
    max_iterations: numericValue("optimizationIterations", 12),
    population: numericValue("optimizationPopulation", 8)
  });
}

async function runTuning() {
  const source = $("tuneSource").value === "hfss"
    ? workspace.hfssMeasurement
    : workspace.measurement;
  if (!source.length) {
    throw new Error("Acquire or import a candidate response first");
  }
  return postJson("/api/engineering/tuning", {
    target: {
      center_hz: numericValue("f0Ghz", 1) * 1e9,
      bandwidth_3db_hz: numericValue("bandwidthGhz", 0.05) * 1e9,
      minimum_s11_db: -numericValue("returnLoss", 25)
    },
    measured: networkMetrics(source),
    sensitivities: {
      frequency_hz_per_turn: numericValue("tuneFrequencySensitivity", 2) * 1e6,
      bandwidth_hz_per_turn: numericValue("tuneBandwidthSensitivity", 1) * 1e6,
      return_loss_db_per_turn: numericValue("tuneReturnSensitivity", 1)
    }
  });
}

async function runMonteCarlo() {
  return postJson("/api/engineering/monte-carlo", {
    specification: currentSpecification(),
    samples: numericValue("mcSamples", 250),
    seed: numericValue("mcSeed", 2026),
    tolerances: {
      f0_relative: numericValue("mcF0", 0.2) / 100,
      bandwidth_relative: numericValue("mcBw", 3) / 100,
      return_loss_db: numericValue("mcRl", 0.5),
      unloaded_q_relative: numericValue("mcQ", 5) / 100
    },
    limits: {
      minimum_return_loss_db: numericValue("mcMinRl", 22),
      maximum_insertion_loss_db: numericValue("mcMaxIl", 1.5)
    }
  });
}

async function runTransmissionLine() {
  const kind = $("tlKind").value;
  return postJson("/api/engineering/transmission-line", {
    kind,
    frequency_ghz: numericValue("tlFrequency", 1),
    width_mm: numericValue("tlWidth", 2.9),
    height_mm: numericValue("tlHeight", 1.6),
    spacing_mm: numericValue("tlHeight", 1.6),
    a_mm: numericValue("tlWidth", 22.86),
    b_mm: numericValue("tlHeight", 10.16),
    epsilon_r: numericValue("tlEr", 4.4),
    thickness_mm: numericValue("tlThickness", 0.035),
    via_diameter_mm: numericValue("tlViaDiameter", 0.8),
    via_pitch_mm: numericValue("tlViaPitch", 1.5)
  });
}

async function saveServerProject() {
  const payload = {
    name: $("serverProjectName").value.trim() || "Filter Project",
    description: $("serverProjectDescription").value,
    specification: currentSpecification(),
    matrix: workspace.result?.matrix || null,
    measurements: {
      hfss_points: workspace.hfssMeasurement.length,
      vna_points: workspace.measurement.length
    }
  };
  const data = workspace.selectedProject
    ? await requestJson(`/api/projects/${workspace.selectedProject}`, {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    })
    : await postJson("/api/projects", payload);
  workspace.selectedProject = data.project.id;
  await loadServerProjects();
  setDirty(false);
  return data;
}

async function loadServerProjects() {
  const data = await getJson("/api/projects");
  const result = document.querySelector(".module-result");
  result.innerHTML = `
    <h3>Projects</h3>
    <table>
      <thead><tr><th>Name</th><th>Revision</th><th>Type</th><th>Order</th><th>Updated</th><th></th></tr></thead>
      <tbody id="projectRows"></tbody>
    </table>
  `;
  const rows = $("projectRows");
  (data.projects || []).forEach((project) => {
    const row = document.createElement("tr");
    row.classList.toggle("selected", workspace.selectedProject === project.id);
    row.innerHTML = `
      <td>${escapeHtml(project.name)}</td><td>${project.revision}</td>
      <td>${escapeHtml(project.filter_type || "")}</td><td>${project.order || ""}</td>
      <td>${escapeHtml(formatTimestamp(project.updated_at))}</td>
      <td><button data-load>Load</button> <button data-delete>Delete</button></td>
    `;
    row.addEventListener("click", () => {
      workspace.selectedProject = project.id;
      $("serverProjectName").value = project.name;
      document.querySelectorAll("#projectRows tr").forEach((item) => item.classList.remove("selected"));
      row.classList.add("selected");
    });
    row.querySelector("[data-load]").addEventListener("click", async (event) => {
      event.stopPropagation();
      await loadServerProject(project.id);
    });
    row.querySelector("[data-delete]").addEventListener("click", async (event) => {
      event.stopPropagation();
      await requestJson(`/api/projects/${project.id}`, {method: "DELETE"});
      if (workspace.selectedProject === project.id) workspace.selectedProject = null;
      await loadServerProjects();
    });
    rows.appendChild(row);
  });
  setModuleStatus(`${data.projects.length} projects`);
}

async function loadServerProject(projectId) {
  const data = await getJson(`/api/projects/${projectId}`);
  const project = data.project;
  workspace.selectedProject = project.id;
  applySpecification(project.specification || {});
  await calculateAll({quiet: true});
  if (project.matrix && workspace.result) {
    workspace.result.matrix = project.matrix;
    renderMatrix();
  }
  $("serverProjectName").value = project.name;
  $("serverProjectDescription").value = project.description || "";
  setDirty(false);
  $("moduleDialog").close();
  showToast(`Loaded ${project.name}`);
}

async function loadLibrary() {
  const category = $("libraryCategory")?.value || "";
  const data = await getJson(category ? `/api/library?category=${encodeURIComponent(category)}` : "/api/library");
  const result = document.querySelector(".module-result");
  result.innerHTML = `
    <h3>Library</h3>
    <table>
      <thead><tr><th>Name</th><th>Category</th><th>Description</th><th></th></tr></thead>
      <tbody id="libraryRows"></tbody>
    </table>
  `;
  const rows = $("libraryRows");
  data.entries.forEach((entry) => {
    const row = document.createElement("tr");
    row.classList.toggle("selected", workspace.selectedLibrary === entry.id);
    row.innerHTML = `
      <td>${escapeHtml(entry.name)}</td><td>${escapeHtml(entry.category)}</td>
      <td>${escapeHtml(entry.description)}</td><td><button data-use>Use</button></td>
    `;
    row.addEventListener("click", () => {
      workspace.selectedLibrary = entry.id;
      document.querySelectorAll("#libraryRows tr").forEach((item) => item.classList.remove("selected"));
      row.classList.add("selected");
    });
    row.querySelector("[data-use]").addEventListener("click", async (event) => {
      event.stopPropagation();
      workspace.selectedLibrary = entry.id;
      await useLibraryEntry();
    });
    rows.appendChild(row);
  });
  setModuleStatus(`${data.entries.length} library entries`);
}

async function useLibraryEntry() {
  if (!workspace.selectedLibrary) throw new Error("Select a library entry first");
  const data = await getJson(`/api/library/${workspace.selectedLibrary}`);
  const entry = data.entry;
  if (entry.specification) {
    applySpecification(entry.specification);
    await calculateAll({quiet: true});
    $("moduleDialog").close();
    showToast(`Applied ${entry.name}`);
  } else if (entry.model) {
    const module = entry.category === "cavity" ? "cavity" : "planar";
    $("moduleDialog").close();
    await openEngineeringModule(module);
    const values = entry.model;
    $("modelRecipe").value = values.recipe;
    $("modelName").value = entry.id.replaceAll("-", "_");
    $("modelOrder").value = values.order || 4;
    $("modelLength").value = values.length_mm || 100;
    $("modelWidth").value = values.width_mm || values.board_width_mm || 40;
    $("modelHeight").value = values.height_mm || values.substrate_height_mm || 1.524;
  }
  return data;
}

function networkMetrics(points) {
  const peak = points.reduce((best, point) => point.s21_db > best.s21_db ? point : best, points[0]);
  const threshold = peak.s21_db - 3;
  const passband = points.filter((point) => point.s21_db >= threshold);
  return {
    points: points.length,
    center_hz: peak.freq_hz,
    bandwidth_3db_hz: passband.length > 1
      ? passband[passband.length - 1].freq_hz - passband[0].freq_hz
      : 0,
    minimum_s11_db: Math.min(...points.map((point) => point.s11_db)),
    peak_s21_db: peak.s21_db
  };
}

function setModuleOutput(data) {
  const output = $("moduleOutput");
  if (output) output.textContent = JSON.stringify(data, null, 2);
  logService(`Module ${workspace.activeModule}`, data);
}

function setModuleStatus(message) {
  $("moduleStatus").textContent = message;
}

function escapeHtml(value) {
  const text = document.createElement("span");
  text.textContent = String(value ?? "");
  return text.innerHTML;
}

function formatTimestamp(value) {
  if (!value) return "";
  return new Date(value).toLocaleString();
}

function saveProject() {
  const project = {
    format: "hfss-filter-studio-project",
    version: 2,
    saved_at: new Date().toISOString(),
    specification: currentSpecification(),
    matrix: workspace.result?.matrix || null,
    measurements: {
      hfss: workspace.hfssMeasurement,
      vna: workspace.measurement
    }
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
      workspace.hfssMeasurement = project.measurements?.hfss || [];
      workspace.measurement = project.measurements?.vna || [];
      drawChart();
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

async function editSelectedSign() {
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
  await evaluateEditedMatrix();
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
  $("matrixFit").addEventListener("click", evaluateEditedMatrix);
  $("exportMatrix").addEventListener("click", exportMatrix);
  $("loadProject").addEventListener("click", () => $("projectFile").click());
  $("projectFile").addEventListener("change", (event) => loadProjectFile(event.target.files[0]));
  $("editSign").addEventListener("click", editSelectedSign);
  $("editMatrix").addEventListener("click", async () => {
    workspace.matrixEditing = !workspace.matrixEditing;
    $("editMatrix").classList.toggle("active", workspace.matrixEditing);
    $("editMatrix").textContent = workspace.matrixEditing ? "Finish Edit" : "Edit Matrix";
    renderMatrix();
    if (!workspace.matrixEditing) await evaluateEditedMatrix();
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
    button.addEventListener("click", async () => {
      document.querySelectorAll("[data-module]").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      await openEngineeringModule(button.dataset.module);
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
  $("configureAedt").addEventListener("click", configureAedt);
  $("validateAedt").addEventListener("click", validateAedt);
  $("evaluateAedt").addEventListener("click", evaluateAedt);
  $("exportAedtResults").addEventListener("click", exportAedtResults);
  $("releaseAedt").addEventListener("click", releaseAedt);
  $("discoverVna").addEventListener("click", discoverVna);
  $("connectVna").addEventListener("click", connectVna);
  $("applySweep").addEventListener("click", applySweep);
  $("singleSweep").addEventListener("click", singleSweep);
  $("saveTrace").addEventListener("click", saveTrace);
  $("inspectVna").addEventListener("click", inspectVna);
  $("closeVna").addEventListener("click", closeVna);
  $("refreshJobs").addEventListener("click", refreshJobs);
  $("cancelActiveJob").addEventListener("click", cancelActiveJob);

  $("closeModule").addEventListener("click", () => $("moduleDialog").close());
  $("moduleDialog").addEventListener("click", (event) => {
    if (event.target === $("moduleDialog")) $("moduleDialog").close();
  });
  $("moduleExecute").addEventListener("click", runActiveModule);
  $("moduleSecondary").addEventListener("click", async () => {
    try {
      await refreshActiveModule();
    } catch (error) {
      setModuleStatus(error.message);
      showToast(error.message, true);
    }
  });

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
    calculateAll({quiet: true}),
    loadAedtInstallations()
  ]);
}

document.addEventListener("DOMContentLoaded", initialize);
