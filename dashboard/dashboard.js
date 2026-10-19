// Fleet dashboard for live bin telemetry.
// It keeps the latest state per bin and a short in-memory history for charts/prediction.

const $ = id => document.getElementById(id);
const fleet = new Map();
const history = new Map();
const alertState = new Map();
const markers = new Map();
const STALE_MS = 30000;
const ALERT_ON = 85;
const ALERT_OFF = 80;

let client = null;
let routeLine = null;
let chart = null;
let map = L.map("map").setView([-37.8136, 144.9631], 11);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap"
}).addTo(map);

function log(msg, obj) {
  const line = `[${new Date().toLocaleTimeString()}] ${msg}` + (obj ? ` ${JSON.stringify(obj)}` : "");
  $("log").textContent = `${line}\n${$("log").textContent}`.slice(0, 15000);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[char]);
}

function depot() {
  const lat = Number($("depotLat").value);
  const lon = Number($("depotLon").value);
  if (!Number.isFinite(lat) || lat < -90 || lat > 90) throw new Error("Invalid depot latitude");
  if (!Number.isFinite(lon) || lon < -180 || lon > 180) throw new Error("Invalid depot longitude");
  return {lat, lon, device_id: "Depot"};
}

function validate(p) {
  if (!p || p.schema_version !== 1) throw new Error("schema version");
  if (typeof p.device_id !== "string" || !p.device_id) throw new Error("device id");

  const caps = p.capacity_pct || p.capacities;
  if (!caps || typeof caps !== "object") throw new Error("capacity object");

  const clean = {};
  for (const name of ["recycled", "green", "landfill"]) {
    const v = Number(caps[name]);
    if (!Number.isFinite(v) || v < 0 || v > 100) throw new Error(`capacity ${name}`);
    clean[name] = v;
  }

  if (p.latitude !== undefined || p.longitude !== undefined) {
    const lat = Number(p.latitude);
    const lon = Number(p.longitude);
    if (!Number.isFinite(lat) || lat < -90 || lat > 90) throw new Error("latitude");
    if (!Number.isFinite(lon) || lon < -180 || lon > 180) throw new Error("longitude");
    p.latitude = lat;
    p.longitude = lon;
  }

  if (p.accuracy_m !== undefined && p.accuracy_m !== null) {
    const accuracy = Number(p.accuracy_m);
    if (!Number.isFinite(accuracy) || accuracy < 0) throw new Error("accuracy");
    p.accuracy_m = accuracy;
  }

  p.capacity_pct = clean;
  p.received_at = Date.now();
  return p;
}

// Hysteresis stops the alert flickering when a reading sits close to 85%.
function updateAlert(bin) {
  const max = Math.max(...Object.values(bin.capacity_pct));
  const previous = alertState.get(bin.device_id) || false;
  const active = previous ? max >= ALERT_OFF : max >= ALERT_ON;
  alertState.set(bin.device_id, active);
  bin.alert = active;
  bin.max_capacity = max;
}

function addHistory(bin) {
  if (!history.has(bin.device_id)) history.set(bin.device_id, []);
  const rows = history.get(bin.device_id);
  rows.push({t: Date.now(), ...bin.capacity_pct});
  while (rows.length > 60) rows.shift();
}

function connect() {
  let dep;
  try { dep = depot(); } catch (err) { log("Configuration error", {message: err.message}); return; }
  const team = $("teamId").value.trim();
  const url = $("brokerUrl").value.trim();

  if (!team || team === "teamXX") { log("Set your team ID"); return; }
  if (!url.startsWith("wss://")) { log("Use a secure HiveMQ WebSocket URL beginning wss://"); return; }

  map.setView([dep.lat, dep.lon], 11);
  if (client) client.end(true);
  client = mqtt.connect(url, {
    username: $("username").value.trim() || undefined,
    password: $("password").value || undefined,
    clientId: `prog6002-dashboard-${Math.random().toString(16).slice(2, 8)}`,
    clean: true,
    keepalive: 30,
    reconnectPeriod: 2000,
    connectTimeout: 10000
  });

  client.on("connect", () => {
    $("connection").textContent = "Connected";
    const topic = `prog6002/${team}/+/telemetry`;
    client.subscribe(topic, {qos: 1}, err => log(err ? "Subscribe failed" : "Subscribed", {topic}));
  });
  client.on("reconnect", () => $("connection").textContent = "Reconnecting");
  client.on("offline", () => $("connection").textContent = "Offline");
  client.on("close", () => $("connection").textContent = "Disconnected");
  client.on("error", err => log("MQTT error", {message: err.message}));

  client.on("message", (topic, bytes) => {
    try {
      const p = validate(JSON.parse(bytes.toString()));
      updateAlert(p);
      fleet.set(p.device_id, p);
      addHistory(p);
      render();
    } catch (err) {
      log("Rejected telemetry", {topic, reason: err.message, payload: bytes.toString().slice(0, 300)});
    }
  });
}


function latencyStats(bin) {
  const raw = bin?.validation?.latency_samples_ms;
  const values = Array.isArray(raw) ? raw.map(Number).filter(Number.isFinite).sort((a, b) => a - b) : [];
  if (!values.length) return null;
  const mid = Math.floor(values.length / 2);
  const median = values.length % 2 ? values[mid] : (values[mid - 1] + values[mid]) / 2;
  return {count: values.length, min: values[0], max: values[values.length - 1], median};
}

function totalSorts(bin) {
  const counts = bin?.sorting?.counts || {};
  return ["recycled", "green", "landfill"].reduce((sum, name) => sum + (Number(counts[name]) || 0), 0);
}

function fleetSortCounts() {
  const totals = {recycled: 0, green: 0, landfill: 0};
  for (const bin of fleet.values()) {
    const counts = bin?.sorting?.counts || {};
    for (const name of Object.keys(totals)) totals[name] += Number(counts[name]) || 0;
  }
  return totals;
}

// Simple linear trend: estimate when the fullest compartment may reach 85%.
function predictionFor(binId) {
  const rows = history.get(binId) || [];
  if (rows.length < 3) return {text: "Collecting trend data", rate: null};

  const recent = rows.slice(-12).map(row => ({
    t: row.t,
    y: Math.max(row.recycled, row.green, row.landfill)
  }));
  const t0 = recent[0].t;
  const xs = recent.map(row => (row.t - t0) / 60000);
  const ys = recent.map(row => row.y);
  const xMean = xs.reduce((a, b) => a + b, 0) / xs.length;
  const yMean = ys.reduce((a, b) => a + b, 0) / ys.length;
  let numerator = 0;
  let denominator = 0;
  for (let i = 0; i < xs.length; i++) {
    numerator += (xs[i] - xMean) * (ys[i] - yMean);
    denominator += (xs[i] - xMean) ** 2;
  }
  const rate = denominator > 0 ? numerator / denominator : 0;
  const current = ys[ys.length - 1];

  if (current >= ALERT_ON) return {text: "Collection threshold reached", rate};
  if (rate <= 0.01) return {text: "No rising fill trend", rate};
  const minutes = (ALERT_ON - current) / rate;
  if (!Number.isFinite(minutes) || minutes < 0 || minutes > 10080) return {text: "Prediction unavailable", rate};
  return {text: `Predicted 85% in ${minutes < 60 ? `${minutes.toFixed(0)} min` : `${(minutes / 60).toFixed(1)} h`}`, rate};
}

function renderSummary() {
  const values = [...fleet.values()];
  const stale = values.filter(b => Date.now() - b.received_at > STALE_MS).length;
  const alerts = values.filter(b => b.alert).length;
  $("summary").innerHTML = `
    <div class="card"><div>Bins online</div><div class="metric">${values.length - stale}</div></div>
    <div class="card"><div>Stale bins</div><div class="metric">${stale}</div></div>
    <div class="card"><div>Collection alerts</div><div class="metric">${alerts}</div></div>
    <div class="card"><div>Last refresh</div><div class="metric">${new Date().toLocaleTimeString()}</div></div>`;
}

function renderAnalytics() {
  const values = [...fleet.values()];
  const counts = fleetSortCounts();
  const total = counts.recycled + counts.green + counts.landfill;
  const averageMax = values.length ? values.reduce((sum, b) => sum + b.max_capacity, 0) / values.length : 0;
  const busiest = values.length ? [...values].sort((a, b) => totalSorts(b) - totalSorts(a))[0] : null;
  $("analytics").innerHTML = `
    <div class="card"><div>Fleet average max fill</div><div class="metric">${averageMax.toFixed(1)}%</div></div>
    <div class="card"><div>Total sorted items</div><div class="metric">${total}</div></div>
    <div class="card"><div>Sort mix</div><div>R ${counts.recycled} • G ${counts.green} • L ${counts.landfill}</div></div>
    <div class="card"><div>Busiest bin</div><div class="metric">${busiest ? escapeHtml(busiest.device_id) : "—"}</div></div>`;
}

function gauge(name, value) {
  const safe = Math.max(0, Math.min(100, Number(value) || 0));
  return `<div class="gauge"><span>${name}</span><div class="bar"><div class="fill" style="width:${safe}%"></div></div><strong>${safe.toFixed(1)}%</strong></div>`;
}

function renderBins() {
  const values = [...fleet.values()].sort((a, b) => a.device_id.localeCompare(b.device_id));
  $("bins").innerHTML = values.map(b => {
    const stale = Date.now() - b.received_at > STALE_MS;
    const accuracy = Number.isFinite(Number(b.accuracy_m)) ? ` • GPS ±${Number(b.accuracy_m).toFixed(0)} m` : "";
    return `<article class="card ${b.alert ? "alert" : ""} ${stale ? "stale" : ""}">
      <div class="bin-title"><h3>${escapeHtml(b.device_id)}</h3><span>${b.alert ? "COLLECT" : "Normal"}${stale ? " • STALE" : ""}</span></div>
      <div class="gauge-row">
        ${gauge("Recycled", b.capacity_pct.recycled)}
        ${gauge("Green", b.capacity_pct.green)}
        ${gauge("Landfill", b.capacity_pct.landfill)}
      </div>
      <p>Max: ${b.max_capacity.toFixed(1)}% • Age: ${Math.floor((Date.now() - b.received_at) / 1000)}s${accuracy}</p>
      <p>Prediction: ${predictionFor(b.device_id).text}</p>
      <p>Sorted items: ${totalSorts(b)}</p>
      <p>Pi receive→servo latency: ${(() => { const x = latencyStats(b); return x ? `median ${x.median.toFixed(1)} ms (min ${x.min.toFixed(1)}, max ${x.max.toFixed(1)}, n=${x.count})` : "collecting samples"; })()}</p>
    </article>`;
  }).join("");

  const select = $("selectedBin");
  const current = select.value;
  select.innerHTML = values.map(b => `<option value="${escapeHtml(b.device_id)}">${escapeHtml(b.device_id)}</option>`).join("");
  if (values.some(b => b.device_id === current)) select.value = current;
}

function haversineKm(a, b) {
  const R = 6371;
  const rad = x => x * Math.PI / 180;
  const dLat = rad(b.lat - a.lat);
  const dLon = rad(b.lon - a.lon);
  const q = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(q));
}

function classifyRouteEligibility(bin) {
  if (!bin.alert) return {eligible: false, reason: "below alert threshold"};
  if (Date.now() - bin.received_at > STALE_MS) return {eligible: false, reason: "stale telemetry"};
  if (!Number.isFinite(Number(bin.latitude)) || !Number.isFinite(Number(bin.longitude))) return {eligible: false, reason: "missing/invalid location"};
  return {eligible: true};
}

// Greedy nearest-neighbour routing is easy to explain and adequate for the small demo fleet.
function nearestNeighbour(points, dep) {
  const left = [...points];
  const ordered = [];
  let current = dep;
  while (left.length) {
    left.sort((a, b) => haversineKm(current, a) - haversineKm(current, b));
    const next = left.shift();
    ordered.push(next);
    current = next;
  }
  return ordered;
}

function markerIcon(bin) {
  const stale = Date.now() - bin.received_at > STALE_MS;
  const symbol = stale ? "?" : (bin.alert ? "!" : "✓");
  const cls = stale ? "map-pin stale-pin" : (bin.alert ? "map-pin alert-pin" : "map-pin normal-pin");
  return L.divIcon({
    className: "",
    html: `<div class="${cls}" title="${escapeHtml(bin.device_id)}">${symbol}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14]
  });
}

function renderMapAndRoute() {
  for (const [id, marker] of markers) {
    if (!fleet.has(id)) {
      map.removeLayer(marker);
      markers.delete(id);
    }
  }

  for (const b of fleet.values()) {
    if (!Number.isFinite(Number(b.latitude)) || !Number.isFinite(Number(b.longitude))) continue;
    const latlng = [Number(b.latitude), Number(b.longitude)];
    const accuracy = Number.isFinite(Number(b.accuracy_m)) ? ` • accuracy ±${Number(b.accuracy_m).toFixed(0)}m` : "";
    const text = `${escapeHtml(b.device_id)}: ${b.max_capacity.toFixed(1)}%${b.alert ? " • COLLECT" : ""}${accuracy}`;

    if (markers.has(b.device_id)) {
      markers.get(b.device_id).setLatLng(latlng).setIcon(markerIcon(b)).bindPopup(text);
    } else {
      markers.set(b.device_id, L.marker(latlng, {icon: markerIcon(b)}).addTo(map).bindPopup(text));
    }
  }

  if (routeLine) {
    map.removeLayer(routeLine);
    routeLine = null;
  }

  let dep;
  try { dep = depot(); } catch (err) { $("routeText").textContent = err.message; return; }
  const eligible = [];
  const excluded = [];

  for (const b of fleet.values()) {
    const status = classifyRouteEligibility(b);
    if (status.eligible) {
      eligible.push({lat: Number(b.latitude), lon: Number(b.longitude), device_id: b.device_id});
    } else if (b.alert) {
      excluded.push(`${b.device_id}: ${status.reason}`);
    }
  }

  if (!eligible.length) {
    $("routeText").textContent = `No eligible collection route.${excluded.length ? `\nExcluded:\n${excluded.join("\n")}` : ""}`;
    return;
  }

  const ordered = nearestNeighbour(eligible, dep);
  const coords = [[dep.lat, dep.lon], ...ordered.map(p => [p.lat, p.lon])];
  routeLine = L.polyline(coords).addTo(map);
  map.fitBounds(routeLine.getBounds(), {padding: [30, 30]});

  let total = 0;
  let previous = dep;
  const lines = ordered.map((p, index) => {
    const distance = haversineKm(previous, p);
    total += distance;
    previous = p;
    return `${index + 1}. ${p.device_id} (${distance.toFixed(2)} km from previous)`;
  });
  $("routeText").textContent = `Collection route:\n${lines.join("\n")}\nEstimated route distance: ${total.toFixed(2)} km${excluded.length ? `\nExcluded:\n${excluded.join("\n")}` : ""}`;
}

function renderChart() {
  const id = $("selectedBin").value;
  const rows = history.get(id) || [];
  const data = {
    labels: rows.map(r => new Date(r.t).toLocaleTimeString()),
    datasets: [
      {label: "Recycled", data: rows.map(r => r.recycled)},
      {label: "Green", data: rows.map(r => r.green)},
      {label: "Landfill", data: rows.map(r => r.landfill)}
    ]
  };

  if (chart) {
    chart.data = data;
    chart.update();
    return;
  }
  chart = new Chart($("historyChart"), {
    type: "line",
    data,
    options: {responsive: true, animation: false, scales: {y: {min: 0, max: 100}}}
  });
}

function render() {
  renderSummary();
  renderAnalytics();
  renderBins();
  renderMapAndRoute();
  renderChart();
  setTimeout(() => map.invalidateSize(), 0);
}

$("connectBtn").addEventListener("click", connect);
$("selectedBin").addEventListener("change", renderChart);
$("depotLat").addEventListener("change", renderMapAndRoute);
$("depotLon").addEventListener("change", renderMapAndRoute);
setInterval(() => { if (fleet.size) render(); }, 5000);
render();
