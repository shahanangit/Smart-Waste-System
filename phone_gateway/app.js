// Phone-side classifier gateway.
// Camera inference stays in the browser; only the classification decision is sent by MQTT.

const $ = id => document.getElementById(id);

let client = null;
let model = null;
let stream = null;
let running = false;
let inferenceTimer = null;
let sequence = 1;
let previousCandidate = "unknown";
let stableCount = 0;
let itemLatched = false;
let absenceFrames = 0;
let lastPublishedLabel = null;
let lastPublishAt = 0;
let locationData = null;

function log(message, data) {
  const line = `[${new Date().toLocaleTimeString()}] ${message}` +
    (data ? ` ${JSON.stringify(data)}` : "");
  $("log").textContent = `${line}\n${$("log").textContent}`.slice(0, 12000);
}

function settings() {
  const s = {
    teamId: $("teamId").value.trim(),
    binId: $("binId").value.trim(),
    phoneId: $("phoneId").value.trim(),
    modelUrl: $("modelUrl").value.trim(),
    brokerUrl: $("brokerUrl").value.trim(),
    username: $("username").value.trim(),
    password: $("password").value,
    threshold: Number($("threshold").value),
    scoreMargin: Number($("scoreMargin").value),
    stableFrames: Number($("stableFrames").value),
    resetFrames: Number($("resetFrames").value),
    cooldown: Number($("cooldown").value)
  };

  if (!s.teamId || s.teamId === "teamXX") throw new Error("Set your team ID");
  if (!s.binId) throw new Error("Set the bin ID");
  if (!s.phoneId) throw new Error("Set the phone ID");
  if (!Number.isFinite(s.threshold) || s.threshold < 0 || s.threshold > 1) throw new Error("Threshold must be 0 to 1");
  if (!Number.isFinite(s.scoreMargin) || s.scoreMargin < 0 || s.scoreMargin > 1) throw new Error("Score margin must be 0 to 1");
  if (!Number.isInteger(s.stableFrames) || s.stableFrames < 1) throw new Error("Stable frames must be at least 1");
  if (!Number.isInteger(s.resetFrames) || s.resetFrames < 1) throw new Error("Reset frames must be at least 1");
  if (!Number.isFinite(s.cooldown) || s.cooldown < 0) throw new Error("Cooldown must be 0 or greater");
  return s;
}

function detectionTopic(s) {
  return `prog6002/${s.teamId}/${s.binId}/detection`;
}

// Model labels can vary, so tested labels are mapped to the three project bins.
function mapToWasteClass(className) {
  const x = String(className || "").trim().toLowerCase();
  if (["recycled", "recyclable", "plastic", "yellow", "bottle"].some(k => x.includes(k))) return "recycled";
  if (["green", "organic", "food", "banana", "apple", "orange"].some(k => x.includes(k))) return "green";
  if (["landfill", "general", "trash", "red", "cup"].some(k => x.includes(k))) return "landfill";
  return "unknown";
}

async function connectMqtt() {
  const s = settings();
  if (!s.brokerUrl.startsWith("wss://")) throw new Error("Use the HiveMQ secure WebSocket URL beginning wss://");
  if (client) client.end(true);

  const clientId = `prog6002-${s.phoneId}-${Math.random().toString(16).slice(2, 8)}`;
  client = mqtt.connect(s.brokerUrl, {
    clientId,
    username: s.username || undefined,
    password: s.password || undefined,
    clean: true,
    keepalive: 30,
    reconnectPeriod: 2000,
    connectTimeout: 10000
  });

  client.on("connect", () => {
    $("mqttState").textContent = "Connected";
    log("MQTT connected", {clientId, topic: detectionTopic(s)});
  });
  client.on("reconnect", () => $("mqttState").textContent = "Reconnecting");
  client.on("offline", () => $("mqttState").textContent = "Offline");
  client.on("close", () => $("mqttState").textContent = "Disconnected");
  client.on("error", err => log("MQTT error", {message: err.message}));
}

function updateGps() {
  if (!navigator.geolocation) {
    $("gpsState").textContent = "Unavailable";
    return;
  }

  $("gpsState").textContent = "Requesting";
  navigator.geolocation.getCurrentPosition(pos => {
    locationData = {
      latitude: Number(pos.coords.latitude.toFixed(6)),
      longitude: Number(pos.coords.longitude.toFixed(6)),
      accuracy_m: Math.round(pos.coords.accuracy)
    };
    $("gpsState").textContent = `±${locationData.accuracy_m} m`;
    log("GPS updated", locationData);
  }, err => {
    $("gpsState").textContent = "Denied/unavailable";
    log("GPS error", {message: err.message});
  }, {enableHighAccuracy: true, timeout: 10000, maximumAge: 10000});
}

function buildEvent(label, confidence, inferenceMs, classification) {
  const s = settings();
  return {
    schema_version: 1,
    event_id: `${s.phoneId}-${String(sequence++).padStart(5, "0")}`,
    bin_id: s.binId,
    label,
    confidence: Number(confidence.toFixed(3)),
    classification: classification || label,
    inference_ms: Math.round(inferenceMs || 0),
    source: s.phoneId,
    timestamp: new Date().toISOString(),
    ...(locationData || {})
  };
}

function publishEvent(label, confidence = 0.95, inferenceMs = 0, classification = label) {
  if (!client || !client.connected) {
    log("Publish blocked: MQTT not connected");
    return false;
  }
  if (!["recycled", "green", "landfill"].includes(label)) {
    log("Unknown/unmapped class: no sorting event published", {classification});
    return false;
  }

  const s = settings();
  const event = buildEvent(label, confidence, inferenceMs, classification);
  const topic = detectionTopic(s);
  const text = JSON.stringify(event);

  client.publish(topic, text, {qos: 1, retain: false}, err => {
    if (err) log("Publish failed", {message: err.message});
    else log("Published detection", event);
  });
  $("lastPayload").textContent = text;
  return true;
}

async function loadModel() {
  const s = settings();
  if (!s.modelUrl) throw new Error("Enter your Teachable Machine model URL");
  if (!s.modelUrl.startsWith("https://")) throw new Error("Model URL must use HTTPS");

  const base = s.modelUrl.endsWith("/") ? s.modelUrl : s.modelUrl + "/";
  $("modelState").textContent = "Loading";
  model = await tmImage.load(base + "model.json", base + "metadata.json");
  const classes = model.getClassLabels();
  if (!Array.isArray(classes) || classes.length < 3) throw new Error("Model needs at least three useful classes");
  $("modelState").textContent = `Ready (${classes.length} classes)`;
  log("Model loaded", {classes});
}

async function startCamera() {
  if (running) stopAll();
  if (!model) await loadModel();

  stream = await navigator.mediaDevices.getUserMedia({
    video: {facingMode: {ideal: "environment"}, width: {ideal: 640}, height: {ideal: 480}},
    audio: false
  });
  $("video").srcObject = stream;
  await $("video").play();

  previousCandidate = "unknown";
  stableCount = 0;
  itemLatched = false;
  absenceFrames = 0;
  $("cameraState").textContent = "Running";
  running = true;
  updateGps();
  inferenceLoop();
}

function stopAll() {
  running = false;
  if (inferenceTimer) clearTimeout(inferenceTimer);
  inferenceTimer = null;
  if (stream) stream.getTracks().forEach(t => t.stop());
  stream = null;
  $("video").srcObject = null;
  $("cameraState").textContent = "Stopped";
}

// A decision needs confidence, separation from the second score and repeated frames.
async function inferenceLoop() {
  if (!running || !model) return;
  const started = performance.now();

  try {
    const predictions = await model.predict($("video"), false);
    if (!Array.isArray(predictions) || !predictions.length) throw new Error("Model returned no predictions");
    predictions.sort((a, b) => b.probability - a.probability);

    const top = predictions[0];
    const second = predictions[1] || {probability: 0};
    const elapsed = performance.now() - started;
    const mapped = mapToWasteClass(top.className);

    $("topClass").textContent = top.className;
    $("mappedBin").textContent = mapped;
    $("confidence").textContent = `${(top.probability * 100).toFixed(1)}%`;
    $("inferenceMs").textContent = elapsed.toFixed(0);

    const s = settings();
    const marginOk = (top.probability - second.probability) >= s.scoreMargin;
    const candidate = top.probability >= s.threshold && marginOk ? mapped : "unknown";

    if (candidate === previousCandidate) stableCount += 1;
    else {
      previousCandidate = candidate;
      stableCount = 1;
    }

    // Seeing enough empty/unknown frames means the previous item has left the camera.
    if (candidate === "unknown") {
      absenceFrames += 1;
      if (absenceFrames >= s.resetFrames) {
        itemLatched = false;
        lastPublishedLabel = null;
      }
    } else {
      absenceFrames = 0;
    }

    const now = Date.now();
    const cooldownOk = (now - lastPublishAt) >= s.cooldown;
    if (!itemLatched && candidate !== "unknown" && stableCount >= s.stableFrames && cooldownOk) {
      if (publishEvent(candidate, top.probability, elapsed, top.className)) {
        itemLatched = true;
        lastPublishedLabel = candidate;
        lastPublishAt = now;
        log("Item latched; remove item before next automatic event", {label: candidate});
      }
      stableCount = 0;
    }
  } catch (err) {
    log("Inference error", {message: err.message});
  }

  if (running) inferenceTimer = setTimeout(inferenceLoop, 250);
}

$("connectBtn").addEventListener("click", () => connectMqtt().catch(e => log("Connect failed", {message: e.message})));
$("startBtn").addEventListener("click", () => startCamera().catch(e => {
  $("cameraState").textContent = "Error";
  log("Camera/model start failed", {message: e.message});
}));
$("stopBtn").addEventListener("click", stopAll);
$("gpsBtn").addEventListener("click", updateGps);

document.querySelectorAll(".manual").forEach(btn => btn.addEventListener("click", () => {
  const label = btn.dataset.label;
  publishEvent(label, 0.95, 0, `manual:${label}`);
}));
