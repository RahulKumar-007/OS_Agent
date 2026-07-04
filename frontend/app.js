/**
 * FileAgent — Frontend Application
 * Connects to FastAPI backend via REST + WebSocket
 */

const API_BASE = "http://localhost:8000";
let ws = null;
let currentTaskId = null;
let currentPlan = null;
let permissionMode = "ask_each";
let mediaRecorder = null;
let audioChunks = [];
const prefersReducedMotion = window.matchMedia(
  "(prefers-reduced-motion: reduce)",
).matches;

// ─── Sidebar toggle (mobile) ──────────────────────
 const sidebarToggleBtn = document.getElementById("sidebarToggle");
if (sidebarToggleBtn) {
  sidebarToggleBtn.addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("open");
  });
}

// ─── AI Presence State ──────────────────────
const STATUS_LABELS = {
  idle: "SYSTEM READY",
  thinking: "ANALYZING REQUEST",
  listening: "LISTENING",
  speaking: "RESPONDING",
  executing: "EXECUTING PLAN",
};

function setAiState(state) {
  const aiCore = document.getElementById("aiCore");
  const strip = document.getElementById("consoleStatusStrip");
  const stripText = document.getElementById("consoleStatusText");
  const heroStatus = document.getElementById("heroStatus");

  [aiCore, strip].forEach((el) => {
    if (!el) return;
    el.classList.remove("thinking", "listening", "speaking", "executing");
    if (state !== "idle") el.classList.add(state);
  });

  const label = STATUS_LABELS[state] || STATUS_LABELS.idle;
  if (stripText) stripText.textContent = label;
  if (heroStatus) {
    const span = heroStatus.querySelector("span:last-child");
    if (span) span.textContent = `${label} — AEGIS ONLINE`;
  }
}

// ─── Ambient Background Field ──────────────────
function initBackgroundFX() {
  const canvas = document.getElementById("bgCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let w, h, particles;

  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  }

  function makeParticles() {
    const count = Math.min(90, Math.floor((w * h) / 16000));
    particles = Array.from({ length: count }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.12,
      vy: (Math.random() - 0.5) * 0.12,
      r: Math.random() * 1.6 + 0.4,
    }));
  }

  resize();
  makeParticles();
  window.addEventListener("resize", () => {
    resize();
    makeParticles();
  });

  function draw() {
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "rgba(79, 243, 255, 0.55)";
    for (const p of particles) {
      if (!prefersReducedMotion) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0) p.x = w;
        if (p.x > w) p.x = 0;
        if (p.y < 0) p.y = h;
        if (p.y > h) p.y = 0;
      }
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
    // faint connecting lines between nearby particles
    ctx.strokeStyle = "rgba(79, 243, 255, 0.08)";
    ctx.lineWidth = 1;
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const a = particles[i],
          b = particles[j];
        const dx = a.x - b.x,
          dy = a.y - b.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 120) {
          ctx.globalAlpha = 1 - dist / 120;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }
    ctx.globalAlpha = 1;
    if (!prefersReducedMotion) requestAnimationFrame(draw);
  }
  draw();
}

// ─── Holographic Wireframe Globe (AI Core hero) ────────
function initGlobe() {
  const canvas = document.getElementById("globeCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const size = canvas.width;
  const cx = size / 2,
    cy = size / 2;
  const radius = size * 0.38;
  let rotation = 0;

  const satellites = [
    { angle: 0, speed: 0.014, dist: radius + 22, size: 2.6 },
    { angle: 2.1, speed: -0.009, dist: radius + 34, size: 2 },
  ];

  function project(lat, lon) {
    const x = radius * Math.cos(lat) * Math.sin(lon);
    const y = radius * Math.sin(lat);
    const z = radius * Math.cos(lat) * Math.cos(lon);
    return { x, y, z };
  }

  function drawLine(points, alphaScale = 1) {
    ctx.beginPath();
    let started = false;
    for (const p of points) {
      const cosR = Math.cos(rotation),
        sinR = Math.sin(rotation);
      const x = p.x * cosR + p.z * sinR;
      const z = -p.x * sinR + p.z * cosR;
      const scale = (z + radius * 2.2) / (radius * 3.2);
      const sx = cx + x * scale;
      const sy = cy + p.y * scale;
      if (!started) {
        ctx.moveTo(sx, sy);
        started = true;
      } else {
        ctx.lineTo(sx, sy);
      }
    }
    ctx.globalAlpha = 0.35 * alphaScale;
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  function draw() {
    ctx.clearRect(0, 0, size, size);
    ctx.strokeStyle = "#4ff3ff";
    ctx.lineWidth = 1;

    // latitude rings
    for (let lat = -60; lat <= 60; lat += 30) {
      const pts = [];
      for (let lon = 0; lon <= 360; lon += 6) {
        pts.push(project((lat * Math.PI) / 180, (lon * Math.PI) / 180));
      }
      drawLine(pts, lat === 0 ? 1.4 : 0.8);
    }
    // longitude rings
    for (let lon = 0; lon < 180; lon += 30) {
      const pts = [];
      for (let lat = -90; lat <= 90; lat += 6) {
        pts.push(project((lat * Math.PI) / 180, (lon * Math.PI) / 180));
      }
      drawLine(pts, 0.7);
    }

    // outer atmosphere glow
    const grad = ctx.createRadialGradient(cx, cy, radius * 0.9, cx, cy, radius * 1.35);
    grad.addColorStop(0, "rgba(79,243,255,0.12)");
    grad.addColorStop(1, "rgba(79,243,255,0)");
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, radius * 1.35, 0, Math.PI * 2);
    ctx.fill();

    // orbiting satellites
    satellites.forEach((s) => {
      if (!prefersReducedMotion) s.angle += s.speed;
      const sx = cx + Math.cos(s.angle) * s.dist;
      const sy = cy + Math.sin(s.angle) * s.dist * 0.4;
      ctx.fillStyle = "#8ff5ff";
      ctx.beginPath();
      ctx.arc(sx, sy, s.size, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "rgba(143,245,255,0.5)";
      ctx.beginPath();
      ctx.ellipse(cx, cy, s.dist, s.dist * 0.4, 0, 0, Math.PI * 2);
      ctx.globalAlpha = 0.15;
      ctx.stroke();
      ctx.globalAlpha = 1;
    });

    if (!prefersReducedMotion) {
      rotation += 0.0035;
      requestAnimationFrame(draw);
    }
  }
  draw();
}

// ─── Page Navigation + Module Lifecycle ───
document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    const page = btn.dataset.page;
    document
      .querySelectorAll(".nav-item")
      .forEach((b) => b.classList.remove("active"));
    document
      .querySelectorAll(".page")
      .forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`page-${page}`).classList.add("active");
    if (page === "history") loadHistory();
    if (page === "settings") loadSettings();
    if (page === "permissions") loadPermissions();
    // Module lifecycle — triggered after modules are defined below
    if (typeof SystemMonitor !== "undefined") {
      if (page === "system") SystemMonitor.start();
      else SystemMonitor.stop();
    }
    if (page === "terminal" && typeof TerminalModule !== "undefined") TerminalModule.init();
    if (page === "webintel" && typeof WebIntel !== "undefined") WebIntel.init();
  });
});

// ─── Permission Mode ────────────────────────────
const permissionDropdown = document.getElementById("permissionMode");
permissionDropdown.addEventListener("change", (e) => {
  permissionMode = e.target.value;
  console.log("Permission mode:", permissionMode);
});

// ─── Voice Input ────────────────────────────────
const voiceBtn = document.getElementById("voiceBtn");
let isRecording = false;

voiceBtn.addEventListener("click", async () => {
  if (!isRecording) {
    startVoiceRecognition();
  } else {
    stopVoiceRecognition();
  }
});

let recognition = null;

function startVoiceRecognition() {
  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    alert("Speech recognition not supported. Use Chrome/Edge.");
    return;
  }

  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "en-US";

  recognition.onstart = () => {
    isRecording = true;
    voiceBtn.classList.add("recording");
    chatInput.placeholder = "🎤 Listening...";
    setAiState("listening");
  };

  recognition.onresult = (event) => {
    let transcript = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      transcript += event.results[i][0].transcript;
    }
    chatInput.value = transcript;
  };

  recognition.onerror = (event) => {
    console.error("Speech recognition error:", event.error);
    stopVoiceRecognition();
  };

  recognition.onend = () => {
    stopVoiceRecognition();
  };

  recognition.start();
}

function stopVoiceRecognition() {
  if (recognition) {
    recognition.stop();
    recognition = null;
  }
  isRecording = false;
  voiceBtn.classList.remove("recording");
  chatInput.placeholder = "Enter command or natural language directive...";
  setAiState("idle");
}

async function transcribeAudio(audioBlob) {
  // For now, just show placeholder
  // In production, use Web Speech API or send to backend STT service
  const recognition = new (
    window.SpeechRecognition || window.webkitSpeechRecognition
  )();
  if (!recognition) {
    alert("Speech recognition not supported in this browser");
    return;
  }
  // Simple implementation - use Web Speech API
  // Note: For better accuracy, send to backend with Whisper API
  chatInput.value =
    "[Voice transcription would appear here - implement with Web Speech API or Whisper]";
}

// ─── Chat Form ──────────────────────────────────
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chatMessages = document.getElementById("chatMessages");

chatInput.addEventListener("input", () => {
  chatInput.style.height = "auto";
  chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
});

chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    chatForm.dispatchEvent(new Event("submit"));
  }
});

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;

  // Clear welcome message
  const welcome = document.querySelector(".welcome-message");
  if (welcome) welcome.remove();

  addMessage("user", message);
  chatInput.value = "";
  chatInput.style.height = "auto";

  // Show typing indicator
  const typingEl = addTypingIndicator();
  setAiState("thinking");

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    typingEl.remove();

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      addMessage("agent", `❌ Error: ${err.detail || "Failed to create plan"}`);
      setAiState("idle");
      return;
    }

    const data = await res.json();
    currentTaskId = data.task_id;
    currentPlan = data.plan;
    addPlanCard(data.plan, data.task_id);
    setAiState("speaking");
    setTimeout(() => setAiState("idle"), 1600);
  } catch (err) {
    typingEl.remove();
    setAiState("idle");
    addMessage(
      "agent",
      `❌ Cannot connect to backend at ${API_BASE}. Make sure the server is running.`,
    );
  }
});

function useSuggestion(text) {
  chatInput.value = text;
  chatForm.dispatchEvent(new Event("submit"));
}

// ─── Message Rendering ─────────────────────────
function addMessage(role, content) {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.innerHTML = `
        <div class="message-avatar">${role === "user" ? "U" : "A"}</div>
        <div class="message-content">${escapeHtml(content)}</div>
    `;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

function addTypingIndicator() {
  const div = document.createElement("div");
  div.className = "message agent";
  div.innerHTML = `
        <div class="message-avatar">A</div>
        <div class="message-content">
            <div class="typing-indicator"><span></span><span></span><span></span></div>
        </div>
    `;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

function addPlanCard(plan, taskId) {
  const div = document.createElement("div");
  div.className = "plan-card";

  let stepsHtml = "";
  (plan.steps || []).forEach((step, i) => {
    stepsHtml += `
            <div class="plan-step ${step.is_destructive ? "step-destructive" : ""}">
                <div class="step-number">${i + 1}</div>
                <div class="step-info">
                    <div class="step-tool">${escapeHtml(step.tool)}</div>
                    <div class="step-desc">${escapeHtml(step.description)}</div>
                </div>
            </div>`;
  });

  let warningsHtml = "";
  if (plan.warnings && plan.warnings.length > 0) {
    warningsHtml = `<div class="plan-warnings">⚠️ ${plan.warnings.map(escapeHtml).join("<br>")}</div>`;
  }

  // Auto-approve based on permission mode
  const shouldAutoApprove =
    permissionMode === "allow_session" ||
    (permissionMode === "allow_safe" && !plan.has_destructive_steps);

  if (shouldAutoApprove) {
    div.innerHTML = `
        <h3>📋 Execution Plan (Auto-approved)</h3>
        <p class="plan-summary">${escapeHtml(plan.summary || plan.goal || "")}</p>
        <div class="plan-steps">${stepsHtml}</div>
        ${warningsHtml}
        <div class="plan-actions">
            <span class="auto-approve-badge">✨ Auto-executing (${permissionMode === "allow_session" ? "session allowed" : "safe ops only"})</span>
        </div>
    `;
  } else {
    div.innerHTML = `
        <h3>📋 Execution Plan</h3>
        <p class="plan-summary">${escapeHtml(plan.summary || plan.goal || "")}</p>
        <div class="plan-steps">${stepsHtml}</div>
        ${warningsHtml}
        <div class="plan-actions">
            <button class="btn btn-success" onclick="approvePlan('${taskId}')">✓ Approve & Execute</button>
            <button class="btn btn-danger" onclick="rejectPlan('${taskId}')">✕ Reject</button>
        </div>
    `;
  }

  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  if (shouldAutoApprove) {
    setTimeout(() => approvePlan(taskId), 500);
  }
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addReportCard(report) {
  const synthesis = report.synthesis;
  const hasSynthesis = synthesis && synthesis.summary;

  // ── Synthesized response (shown first) ──
  if (hasSynthesis) {
    const summaryDiv = document.createElement("div");
    summaryDiv.className = "message agent";
    summaryDiv.innerHTML = `
            <div class="message-avatar">A</div>
            <div class="message-content synthesis-summary">${escapeHtml(synthesis.summary)}</div>
        `;
    chatMessages.appendChild(summaryDiv);
  }

  // ── Main report card ──
  const div = document.createElement("div");
  div.className = "report-card";
  const statusEmoji = report.status === "completed" ? "✅" : "⚠️";

  // Filter badges
  let filterBadges = "";
  if (
    hasSynthesis &&
    synthesis.filters_applied &&
    synthesis.filters_applied.length > 0
  ) {
    filterBadges = `
            <div class="filter-badges">
                <span class="filter-label">Filters:</span>
                ${synthesis.filters_applied.map((f) => `<span class="filter-badge">${escapeHtml(f)}</span>`).join("")}
            </div>`;
  }

  // Synthesized filtered data (priority display)
  let filteredDataHtml = "";
  if (hasSynthesis && synthesis.filtered_data) {
    filteredDataHtml = renderStepData("synthesized", synthesis.filtered_data);
  }

  // Notes from synthesizer
  let notesHtml = "";
  if (hasSynthesis && synthesis.notes) {
    notesHtml = `<div class="synthesis-notes">💡 ${escapeHtml(synthesis.notes)}</div>`;
  }

  // Raw step results (collapsible)
  let rawStepsHtml = "";
  if (report.steps && report.steps.length > 0) {
    const rawId = "raw-" + Date.now();
    let stepsContent = "";
    report.steps.forEach((step) => {
      const stepStatus =
        step.status === "completed"
          ? "✅"
          : step.status === "denied"
            ? "🚫"
            : "❌";
      let dataHtml = step.data ? renderStepData(step.tool, step.data) : "";
      stepsContent += `
                <div class="step-result">
                    <div class="step-result-header">
                        <span>${stepStatus} <strong>${escapeHtml(step.tool)}</strong></span>
                        <span class="step-result-msg">${escapeHtml(step.message || step.error || "")}</span>
                    </div>
                    ${dataHtml}
                </div>`;
    });

    rawStepsHtml = `
            <div class="raw-results-toggle">
                <button class="btn btn-small btn-secondary" onclick="toggleRawResults('${rawId}')">
                    ▶ Show raw tool output
                </button>
            </div>
            <div class="raw-results-content" id="${rawId}" style="display:none;">
                ${stepsContent}
            </div>`;
  }

  div.innerHTML = `
        <h3>${statusEmoji} Execution Report</h3>
        <div class="report-stats">
            <div class="report-stat">
                <div class="stat-value success">${report.completed_steps}</div>
                <div class="stat-label">Completed</div>
            </div>
            <div class="report-stat">
                <div class="stat-value danger">${report.failed_steps}</div>
                <div class="stat-label">Failed</div>
            </div>
            <div class="report-stat">
                <div class="stat-value info">${hasSynthesis ? synthesis.total_results || report.total_files_affected : report.total_files_affected}</div>
                <div class="stat-label">${hasSynthesis ? "Results" : "Files Affected"}</div>
            </div>
            <div class="report-stat">
                <div class="stat-value">${report.duration_seconds?.toFixed(1) || "0"}s</div>
                <div class="stat-label">Duration</div>
            </div>
        </div>
        ${filterBadges}
        ${filteredDataHtml}
        ${notesHtml}
        ${report.errors?.length > 0 ? `<div class="plan-warnings">Errors:<br>${report.errors.map((e) => escapeHtml(e.error)).join("<br>")}</div>` : ""}
        ${rawStepsHtml}
    `;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function toggleRawResults(id) {
  const el = document.getElementById(id);
  const btn = el.previousElementSibling.querySelector("button");
  if (el.style.display === "none") {
    el.style.display = "block";
    btn.textContent = "▼ Hide raw tool output";
  } else {
    el.style.display = "none";
    btn.textContent = "▶ Show raw tool output";
  }
}

async function openFile(path) {
  try {
    const response = await fetch(`${API_BASE}/api/open?path=${encodeURIComponent(path)}`, {
      method: "POST",
    });
    const result = await response.json();
    if (!response.ok) {
      alert(`Error opening file: ${result.detail || result.message}`);
    } else {
      console.log(`Opened: ${path}`);
    }
  } catch (error) {
    console.error("Error opening file:", error);
    alert("Failed to open file.");
  }
}

function renderStepData(tool, data) {
  // Unwrap {results: [...]} wrappers returned by advanced_search, search_files, etc.
  if (data && typeof data === "object" && !Array.isArray(data) && Array.isArray(data.results)) {
    data = data.results;
  }

  // File listing (list_directory, search_files)
  if (Array.isArray(data) && data.length > 0 && data[0].path) {
    const maxShow = 50;
    const items = data.slice(0, maxShow);
    let rows = items
      .map((f) => {
        const icon = f.is_dir ? "📁" : getFileIcon(f.name || f.path);
        const size = f.is_dir ? "—" : formatSize(f.size);
        const name = escapeHtml(f.name || f.path.split("/").pop());
        const modified = f.modified
          ? new Date(f.modified).toLocaleDateString()
          : "—";
        const escapedPath = (f.path || "").replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        return `<tr onclick="openFile('${escapedPath}')" style="cursor: pointer;" title="Click to open ${name}"><td>${icon} ${name}</td><td>${size}</td><td>${modified}</td></tr>`;
      })
      .join("");

    let overflow = "";
    if (data.length > maxShow) {
      overflow = `<div class="results-overflow">...and ${data.length - maxShow} more items</div>`;
    }

    return `
            <div class="results-table-wrap">
                <table class="results-table">
                    <thead><tr><th>Name</th><th>Size</th><th>Modified</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
                ${overflow}
            </div>`;
  }

  // Duplicate detection results
  if (data.duplicate_groups) {
    if (data.duplicate_groups.length === 0) {
      return `<div class="results-message">✨ No duplicates found!</div>`;
    }
    let groups = data.duplicate_groups
      .map((g) => {
        const files = g.files
          .map(
            (f) =>
              `<div class="dup-file">${escapeHtml(f.split("/").pop())}</div>`,
          )
          .join("");
        return `
                <div class="dup-group">
                    <div class="dup-header">${g.count} copies · ${formatSize(g.wasted_bytes)} wasted</div>
                    ${files}
                </div>`;
      })
      .join("");
    return `
            <div class="results-duplicates">
                <div class="dup-summary">Found ${data.total_groups} duplicate groups · ${formatSize(data.total_wasted_bytes)} total wasted</div>
                ${groups}
            </div>`;
  }

  // File metadata
  if (data.path && data.permissions) {
    return `
            <div class="results-metadata">
                <div><strong>Path:</strong> ${escapeHtml(data.path)}</div>
                <div><strong>Size:</strong> ${formatSize(data.size)}</div>
                <div><strong>Type:</strong> ${escapeHtml(data.extension || "Unknown")}</div>
                <div><strong>Permissions:</strong> <code>${escapeHtml(data.permissions)}</code></div>
                <div><strong>Modified:</strong> ${new Date(data.modified).toLocaleString()}</div>
            </div>`;
  }

  // Hash result
  if (data.hash) {
    return `<div class="results-message">SHA-256: <code>${escapeHtml(data.hash)}</code></div>`;
  }

  // Generic: show as message if it's simple
  if (typeof data === "string") {
    return `<div class="results-message">${escapeHtml(data)}</div>`;
  }

  return "";
}

function getFileIcon(name) {
  const ext = (name || "").split(".").pop().toLowerCase();
  const icons = {
    pdf: "📄",
    doc: "📝",
    docx: "📝",
    txt: "📝",
    md: "📝",
    jpg: "🖼️",
    jpeg: "🖼️",
    png: "🖼️",
    gif: "🖼️",
    svg: "🖼️",
    webp: "🖼️",
    mp4: "🎬",
    mkv: "🎬",
    avi: "🎬",
    mov: "🎬",
    mp3: "🎵",
    wav: "🎵",
    flac: "🎵",
    ogg: "🎵",
    zip: "📦",
    tar: "📦",
    gz: "📦",
    rar: "📦",
    "7z": "📦",
    js: "⚡",
    ts: "⚡",
    py: "🐍",
    go: "🔵",
    rs: "🦀",
    c: "⚙️",
    cpp: "⚙️",
    java: "☕",
    html: "🌐",
    css: "🎨",
    json: "📋",
    yaml: "📋",
    yml: "📋",
    exe: "⚙️",
    sh: "⚙️",
    bin: "⚙️",
  };
  return icons[ext] || "📄";
}

function formatSize(bytes) {
  if (bytes == null || bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + " " + units[i];
}

// ─── Plan Actions ───────────────────────────────
async function approvePlan(taskId) {
  const typingEl = addTypingIndicator();
  setAiState("executing");

  try {
    const res = await fetch(`${API_BASE}/api/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task_id: taskId }),
    });

    typingEl.remove();

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      addMessage(
        "agent",
        `❌ Execution failed: ${err.detail || "Unknown error"}`,
      );
      setAiState("idle");
      return;
    }

    const data = await res.json();
    addReportCard(data.report);
    setAiState("speaking");
    setTimeout(() => setAiState("idle"), 1600);
    loadSystemStatus();
  } catch (err) {
    typingEl.remove();
    setAiState("idle");
    addMessage("agent", `❌ Execution error: ${err.message}`);
  }
}

async function rejectPlan(taskId) {
  try {
    await fetch(`${API_BASE}/api/reject/${taskId}`, { method: "POST" });
    addMessage(
      "agent",
      "❌ Plan rejected. Let me know if you want to try something different.",
    );
  } catch (err) {
    addMessage("agent", "❌ Failed to reject plan.");
  }
}

// ─── History ────────────────────────────────────
async function loadHistory() {
  const list = document.getElementById("historyList");
  try {
    const res = await fetch(`${API_BASE}/api/tasks`);
    if (!res.ok) throw new Error("Failed to load");
    const data = await res.json();

    if (!data.tasks || data.tasks.length === 0) {
      list.innerHTML = `<div class="empty-state">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                <p>No tasks yet. Start chatting to create your first task!</p>
            </div>`;
      return;
    }

    list.innerHTML = data.tasks
      .map(
        (task) => `
            <div class="history-item" onclick="viewTask('${task.id}')">
                <div class="history-info">
                    <div class="history-input">${escapeHtml(task.user_input)}</div>
                    <div class="history-meta">${task.goal || ""} · ${new Date(task.created_at).toLocaleString()}</div>
                </div>
                <span class="history-status ${task.status}">${task.status.replace(/_/g, " ")}</span>
            </div>
        `,
      )
      .join("");
  } catch (err) {
    list.innerHTML = `<div class="empty-state"><p>Cannot load history. Is the backend running?</p></div>`;
  }
}

async function viewTask(taskId) {
  // Switch to chat and show task details
  document
    .querySelectorAll(".nav-item")
    .forEach((b) => b.classList.remove("active"));
  document
    .querySelectorAll(".page")
    .forEach((p) => p.classList.remove("active"));
  document.getElementById("nav-chat").classList.add("active");
  document.getElementById("page-chat").classList.add("active");

  try {
    const res = await fetch(`${API_BASE}/api/tasks/${taskId}`);
    const task = await res.json();

    const welcome = document.querySelector(".welcome-message");
    if (welcome) welcome.remove();

    addMessage("user", task.user_input);

    if (task.plan_json) {
      addPlanCard(task.plan_json, task.id);
    }
    if (task.result_json) {
      addReportCard(task.result_json);
    }
  } catch (err) {
    addMessage("agent", "❌ Failed to load task details.");
  }
}

// ─── Settings ───────────────────────────────────
async function loadSettings() {
  try {
    const res = await fetch(`${API_BASE}/api/settings/llm`);
    if (!res.ok) return;
    const config = await res.json();

    document.getElementById("llmProvider").value =
      config.provider || "lmstudio";
    document.getElementById("llmBaseUrl").value = config.base_url || "";
    document.getElementById("llmModel").value = config.model || "";
    document.getElementById("llmTemp").value = config.temperature || 0.3;
    document.getElementById("tempValue").textContent =
      config.temperature || 0.3;
    document.getElementById("llmMaxTokens").value = config.max_tokens || 4096;
  } catch (err) {
    // Backend not available
  }

  checkLlmHealth();
  loadMemories();
}

document.getElementById("llmTemp").addEventListener("input", (e) => {
  document.getElementById("tempValue").textContent = e.target.value;
});

document
  .getElementById("saveLlmSettings")
  .addEventListener("click", async () => {
    const config = {
      provider: document.getElementById("llmProvider").value,
      base_url: document.getElementById("llmBaseUrl").value,
      model: document.getElementById("llmModel").value,
      temperature: parseFloat(document.getElementById("llmTemp").value),
      max_tokens: parseInt(document.getElementById("llmMaxTokens").value),
    };

    try {
      const res = await fetch(`${API_BASE}/api/settings/llm`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (res.ok) {
        showToast("Settings saved!");
        checkLlmHealth();
      }
    } catch (err) {
      showToast("Failed to save settings", "error");
    }
  });

document
  .getElementById("testLlmConnection")
  .addEventListener("click", checkLlmHealth);

async function checkLlmHealth() {
  const statusEl = document.getElementById("llmStatus");
  const connEl = document.getElementById("connectionStatus");

  try {
    const res = await fetch(`${API_BASE}/api/settings/llm/health`);
    const data = await res.json();

    if (data.status === "connected") {
      statusEl.innerHTML = `<div class="status-dot connected"></div><span>Connected</span>`;
      connEl.innerHTML = `<div class="status-dot connected"></div><span>LLM Connected</span>`;

      // Show available models
      const modelsList = document.getElementById("modelsList");
      if (data.available_models?.length > 0) {
        modelsList.innerHTML = data.available_models
          .map(
            (m) =>
              `<span class="model-chip ${m === data.model ? "selected" : ""}" onclick="selectModel('${m}')">${m}</span>`,
          )
          .join("");
      }
    } else {
      statusEl.innerHTML = `<div class="status-dot disconnected"></div><span>${data.error || "Disconnected"}</span>`;
      connEl.innerHTML = `<div class="status-dot disconnected"></div><span>LLM Disconnected</span>`;
    }
  } catch (err) {
    statusEl.innerHTML = `<div class="status-dot disconnected"></div><span>Backend offline</span>`;
    connEl.innerHTML = `<div class="status-dot disconnected"></div><span>Backend Offline</span>`;
  }
}

async function selectModel(model) {
  document.getElementById("llmModel").value = model;
  document
    .querySelectorAll(".model-chip")
    .forEach((c) => c.classList.remove("selected"));
  event.target.classList.add("selected");
}

async function loadMemories() {
  try {
    const res = await fetch(`${API_BASE}/api/memory`);
    const data = await res.json();
    const list = document.getElementById("memoryList");

    if (Object.keys(data).length === 0) {
      list.innerHTML = `<p class="muted">No memories stored yet.</p>`;
      return;
    }

    list.innerHTML = Object.entries(data)
      .map(
        ([key, val]) => `
            <div class="path-item">
                <span><strong>${escapeHtml(key)}</strong>: ${escapeHtml(JSON.stringify(val))}</span>
                <button class="path-remove" onclick="deleteMemory('${escapeHtml(key)}')" title="Delete">✕</button>
            </div>
        `,
      )
      .join("");
  } catch (err) {
    // Backend not available
  }
}

async function deleteMemory(key) {
  try {
    await fetch(`${API_BASE}/api/memory/${key}`, { method: "DELETE" });
    loadMemories();
  } catch (err) {}
}

// ─── Permissions ────────────────────────────────
async function loadPermissions() {
  try {
    const res = await fetch(`${API_BASE}/api/permissions`);
    if (!res.ok) return;
    const config = await res.json();

    renderPathList("allowedPaths", config.allowed_paths || []);
    renderPathList("deniedPaths", config.denied_paths || []);
  } catch (err) {}
}

function renderPathList(containerId, paths) {
  const container = document.getElementById(containerId);
  if (paths.length === 0) {
    container.innerHTML = `<p class="muted" style="padding:4px 0">No paths configured</p>`;
    return;
  }
  container.innerHTML = paths
    .map(
      (p) => `
        <div class="path-item">
            <span>${escapeHtml(p)}</span>
            <button class="path-remove" onclick="removePath('${containerId}', '${escapeHtml(p)}')" title="Remove">✕</button>
        </div>
    `,
    )
    .join("");
}

function removePath(containerId, path) {
  const container = document.getElementById(containerId);
  const items = container.querySelectorAll(".path-item");
  items.forEach((item) => {
    if (item.querySelector("span").textContent === path) item.remove();
  });
  if (container.children.length === 0) {
    container.innerHTML = `<p class="muted" style="padding:4px 0">No paths configured</p>`;
  }
}

document.getElementById("addAllowedPath").addEventListener("click", () => {
  const input = document.getElementById("newAllowedPath");
  if (!input.value.trim()) return;
  const container = document.getElementById("allowedPaths");
  const muted = container.querySelector(".muted");
  if (muted) muted.remove();
  const div = document.createElement("div");
  div.className = "path-item";
  div.innerHTML = `<span>${escapeHtml(input.value.trim())}</span><button class="path-remove" onclick="this.parentElement.remove()" title="Remove">✕</button>`;
  container.appendChild(div);
  input.value = "";
});

document.getElementById("addDeniedPath").addEventListener("click", () => {
  const input = document.getElementById("newDeniedPath");
  if (!input.value.trim()) return;
  const container = document.getElementById("deniedPaths");
  const muted = container.querySelector(".muted");
  if (muted) muted.remove();
  const div = document.createElement("div");
  div.className = "path-item";
  div.innerHTML = `<span>${escapeHtml(input.value.trim())}</span><button class="path-remove" onclick="this.parentElement.remove()" title="Remove">✕</button>`;
  container.appendChild(div);
  input.value = "";
});

document
  .getElementById("savePermissions")
  .addEventListener("click", async () => {
    const allowed = [
      ...document
        .getElementById("allowedPaths")
        .querySelectorAll(".path-item span"),
    ].map((s) => s.textContent);
    const denied = [
      ...document
        .getElementById("deniedPaths")
        .querySelectorAll(".path-item span"),
    ].map((s) => s.textContent);

    try {
      const res = await fetch(`${API_BASE}/api/permissions`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ allowed_paths: allowed, denied_paths: denied }),
      });
      if (res.ok) showToast("Permissions saved!");
    } catch (err) {
      showToast("Failed to save permissions", "error");
    }
  });

// ─── Provider Presets ───────────────────────────
document.getElementById("llmProvider").addEventListener("change", (e) => {
  const urlInput = document.getElementById("llmBaseUrl");
  switch (e.target.value) {
    case "lmstudio":
      urlInput.value = "http://localhost:1234/v1";
      break;
    case "ollama":
      urlInput.value = "http://localhost:11434/v1";
      break;
    case "openai_compatible":
      urlInput.value = "http://localhost:8080/v1";
      break;
  }
});

// ─── Toast Notifications ────────────────────────
function showToast(msg, type = "success") {
  const toast = document.createElement("div");
  toast.className = `holo-toast${type === "error" ? " error" : ""}`;
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.classList.add("fade-out");
    setTimeout(() => toast.remove(), 300);
  }, 2800);
}

// ─── Utility ────────────────────────────────────
function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ─── System Telemetry ────────────────────────────
async function loadSystemStatus() {
  try {
    const [toolsRes, memRes, tasksRes] = await Promise.all([
      fetch(`${API_BASE}/api/tools`).catch(() => null),
      fetch(`${API_BASE}/api/memory`).catch(() => null),
      fetch(`${API_BASE}/api/tasks?limit=1000`).catch(() => null),
    ]);

    if (toolsRes?.ok) {
      const data = await toolsRes.json();
      const el = document.getElementById("sidebarToolCount");
      if (el) el.textContent = (data.tools || []).length;
    }
    if (memRes?.ok) {
      const data = await memRes.json();
      const el = document.getElementById("sidebarMemoryCount");
      if (el) el.textContent = Object.keys(data || {}).length;
    }
    if (tasksRes?.ok) {
      const data = await tasksRes.json();
      const el = document.getElementById("sidebarTaskCount");
      if (el) el.textContent = data.total ?? (data.tasks || []).length;

      const missionEl = document.getElementById("sidebarMissionText");
      if (missionEl && data.tasks && data.tasks.length > 0) {
        const last = data.tasks[0];
        const label =
          last.status === "executing"
            ? "EXECUTING TASK"
            : last.status === "awaiting_approval"
              ? "AWAITING AUTHORIZATION"
              : "STANDING BY";
        missionEl.textContent = label;
      }
    }
  } catch (err) {
    console.warn("System telemetry unavailable:", err);
  }
}

// ─── Init ───────────────────────────────────────
checkLlmHealth();
setInterval(checkLlmHealth, 30000);
loadSystemStatus();
setInterval(loadSystemStatus, 30000);
initBackgroundFX();
initGlobe();



// ══════════════════════════════════════════════════
// SYSTEM MONITOR MODULE
// ══════════════════════════════════════════════════

const SystemMonitor = (() => {
  let pollTimer = null;
  let networkHistory = []; // [{sent, recv, ts}]
  const MAX_NET_HISTORY = 40;
  let prevNetBytes = null;

  // ── DOM refs ──────────────────────────────────
  const el = (id) => document.getElementById(id);

  // ── Start / Stop ──────────────────────────────
  function start() {
    if (pollTimer) return; // already running
    fetchMetrics();
    fetchProcesses();
    fetchIndexStatus();
    pollTimer = setInterval(() => {
      fetchMetrics();
      fetchProcesses();
      fetchIndexStatus();
    }, 3000);
  }

  function stop() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  // ── Metrics ───────────────────────────────────
  async function fetchMetrics() {
    try {
      const res = await fetch(`${API_BASE}/api/system/metrics`);
      if (!res.ok) return;
      const m = await res.json();
      updateCpu(m.cpu);
      updateMemory(m.memory, m.swap);
      updateDisks(m.disks);
      updateNetwork(m.network, m.timestamp);
      updateGpu(m.gpu);
      updateUptime(m.uptime_seconds);
      // Sidebar gauges
      updateSidebarGauge("gaugeCpu", "gaugeCpuRing", "gaugeCpuValue", m.cpu.percent);
      updateSidebarGauge("gaugeRam", "gaugeRamRing", "gaugeRamValue", m.memory.percent);
      const diskMain = m.disks?.[0];
      if (diskMain) updateSidebarGauge("gaugeDisk", "gaugeDiskRing", "gaugeDiskValue", diskMain.percent);
    } catch (e) {
      console.warn("System metrics unavailable:", e);
    }
  }

  function updateSidebarGauge(gaugeId, ringId, valueId, percent) {
    const ring = el(ringId);
    const value = el(valueId);
    if (!ring || !value) return;
    const r = 26;
    const circ = 2 * Math.PI * r;
    const pct = Math.min(100, Math.max(0, percent));
    const dashOffset = circ * (1 - pct / 100);
    ring.style.strokeDasharray = circ;
    ring.style.strokeDashoffset = dashOffset;
    // color
    const hue = 120 - (pct / 100) * 120; // green→red
    ring.style.stroke = `hsl(${hue},90%,55%)`;
    value.textContent = `${Math.round(pct)}%`;
  }

  function updateCpu(cpu) {
    const badge = el("cpuBadge");
    const cores = el("cpuCores");
    const foot = el("cpuFootnote");
    if (!badge) return;
    badge.textContent = `${Math.round(cpu.percent)}%`;
    if (cores && cpu.per_core) {
      cores.innerHTML = cpu.per_core.map((p, i) => {
        const pct = Math.round(p);
        const hue = 120 - (pct / 100) * 120;
        return `<div class="core-bar-wrap" title="Core ${i}: ${pct}%">
          <div class="core-bar" style="height:${Math.max(4, pct)}%;background:hsl(${hue},90%,55%)"></div>
          <span class="core-label">${i}</span>
        </div>`;
      }).join("");
    }
    if (foot) {
      const load = cpu.load_avg?.map(v => v.toFixed(2)).join(", ") || "—";
      foot.textContent = `${cpu.physical_cores}P / ${cpu.cores}L cores · ${cpu.freq_mhz || "—"} MHz · Load: ${load}`;
    }
  }

  function fmtBytes(b) {
    if (b == null) return "—";
    const u = ["B","KB","MB","GB","TB"];
    let i = 0;
    while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
    return `${b.toFixed(1)} ${u[i]}`;
  }

  function updateMemory(mem, swap) {
    const badge = el("ramBadge");
    const meterFill = el("ramMeterFill");
    const foot = el("ramFootnote");
    const swapFill = el("swapMeterFill");
    const swapFoot = el("swapFootnote");
    if (badge) badge.textContent = `${Math.round(mem.percent)}%`;
    if (meterFill) {
      meterFill.style.width = `${mem.percent}%`;
      const hue = 120 - (mem.percent / 100) * 120;
      meterFill.style.background = `hsl(${hue},80%,50%)`;
    }
    if (foot) foot.textContent = `${fmtBytes(mem.used)} / ${fmtBytes(mem.total)} used`;
    if (swapFill && swap) {
      swapFill.style.width = `${swap.percent}%`;
    }
    if (swapFoot && swap) swapFoot.textContent = `Swap: ${fmtBytes(swap.used)} / ${fmtBytes(swap.total)}`;
  }

  function updateDisks(disks) {
    const list = el("diskList");
    if (!list || !disks) return;
    list.innerHTML = disks.map(d => {
      const hue = 120 - (d.percent / 100) * 120;
      return `<div class="disk-item">
        <div class="disk-label">
          <span class="disk-mount">${escapeHtml(d.mountpoint)}</span>
          <span class="disk-pct" style="color:hsl(${hue},80%,55%)">${Math.round(d.percent)}%</span>
        </div>
        <div class="disk-bar-bg"><div class="disk-bar-fill" style="width:${d.percent}%;background:hsl(${hue},80%,50%)"></div></div>
        <div class="disk-sub">${fmtBytes(d.used)} / ${fmtBytes(d.total)} · ${escapeHtml(d.fstype || "")} · ${escapeHtml(d.device)}</div>
      </div>`;
    }).join("");
  }

  function updateNetwork(net, ts) {
    const foot = el("networkFootnote");
    const canvas = el("networkSparkline");
    if (!net) return;

    let sentRate = 0, recvRate = 0;
    if (prevNetBytes && ts) {
      const dt = (ts - prevNetBytes.ts) || 1;
      sentRate = (net.bytes_sent - prevNetBytes.sent) / dt;
      recvRate = (net.bytes_recv - prevNetBytes.recv) / dt;
    }
    prevNetBytes = { sent: net.bytes_sent, recv: net.bytes_recv, ts };

    networkHistory.push({ sent: sentRate, recv: recvRate });
    if (networkHistory.length > MAX_NET_HISTORY) networkHistory.shift();

    if (foot) foot.textContent = `↓ ${fmtBytes(recvRate)}/s  ·  ↑ ${fmtBytes(sentRate)}/s  ·  Total ↓ ${fmtBytes(net.bytes_recv)}`;

    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const maxVal = Math.max(...networkHistory.map(p => Math.max(p.sent, p.recv)), 1);
    const drawLine = (data, color) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      data.forEach((v, i) => {
        const x = (i / (MAX_NET_HISTORY - 1)) * w;
        const y = h - (v / maxVal) * (h - 4) - 2;
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.stroke();
    };
    drawLine(networkHistory.map(p => p.recv), "#4ff3ff");
    drawLine(networkHistory.map(p => p.sent), "#a78bfa");
  }

  function updateGpu(gpu) {
    const card = el("gpuCard");
    const badge = el("gpuBadge");
    const foot = el("gpuFootnote");
    if (!gpu || gpu.length === 0) { if (card) card.style.display = "none"; return; }
    if (card) card.style.display = "";
    const g = gpu[0];
    if (badge) badge.textContent = `${Math.round(g.utilization_percent)}%`;
    if (foot) foot.textContent = `${escapeHtml(g.name)} · ${fmtBytes(g.memory_used_mb * 1024 * 1024)}/${fmtBytes(g.memory_total_mb * 1024 * 1024)} · ${g.temperature_c}°C`;
  }

  function updateUptime(seconds) {
    const display = el("uptimeDisplay");
    if (!display) return;
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    display.textContent = `${d}d ${h}h ${m}m`;
  }

  // ── Processes ─────────────────────────────────
  async function fetchProcesses() {
    try {
      const res = await fetch(`${API_BASE}/api/system/processes?limit=30`);
      if (!res.ok) return;
      const data = await res.json();
      renderProcessTable(data.processes || []);
      const badge = el("processCountBadge");
      if (badge) badge.textContent = `${data.count} procs`;
    } catch (e) {}
  }

  function renderProcessTable(procs) {
    const tbody = el("processTableBody");
    if (!tbody) return;
    if (!procs.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="muted">No processes</td></tr>`;
      return;
    }
    tbody.innerHTML = procs.slice(0, 30).map(p => {
      const cpuHue = 120 - (Math.min(p.cpu, 100) / 100) * 120;
      const memHue = 120 - (Math.min(p.memory, 100) / 100) * 120;
      const isZombie = p.status === "zombie";
      return `<tr class="${isZombie ? "zombie-proc" : ""}">
        <td class="proc-name" title="${escapeHtml(p.name)}">${escapeHtml(p.name.length > 22 ? p.name.slice(0, 22) + "…" : p.name)}${isZombie ? " 🧟" : ""}</td>
        <td>${p.pid}</td>
        <td class="muted">${escapeHtml(p.user || "—")}</td>
        <td style="color:hsl(${cpuHue},80%,55%)">${p.cpu.toFixed(1)}%</td>
        <td style="color:hsl(${memHue},80%,55%)">${p.memory.toFixed(1)}%</td>
        <td><button class="proc-kill-btn" onclick="SystemMonitor.killProcess(${p.pid}, false)" title="Terminate">⊗</button></td>
      </tr>`;
    }).join("");
  }

  async function killProcess(pid, force = false) {
    if (!confirm(`Terminate process ${pid}?`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/system/kill?pid=${pid}&force=${force}`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        showToast(`Sent SIGTERM to PID ${pid}`);
        fetchProcesses();
      } else {
        showToast(data.detail || "Kill failed", "error");
      }
    } catch (e) {
      showToast("Cannot reach backend", "error");
    }
  }

  // ── Search Index Status ───────────────────────
  async function fetchIndexStatus() {
    const card = el("indexStatusCard");
    if (!card) return;
    try {
      const res = await fetch(`${API_BASE}/api/index/status`);
      if (!res.ok) { card.style.display = "none"; return; }
      const d = await res.json();
      card.style.display = "";
      const pct = d.is_building ? Math.round((d.indexed / Math.max(d.total_to_index || 1, 1)) * 100) : 100;
      card.innerHTML = `
        <div class="card-header">
          <h3>Search Index</h3>
          <span class="metric-badge" id="indexBadge">${d.is_building ? "Building…" : "Ready"}</span>
        </div>
        <div class="metric-footnote">${d.total_indexed?.toLocaleString() || 0} files indexed · ${d.is_watching ? "🟢 Live watch" : "🔴 No watch"}</div>
        ${d.is_building ? `<div class="meter" style="margin-top:8px"><div class="meter-fill" style="width:${pct}%;background:var(--accent)"></div></div>` : ""}
        <div style="margin-top:10px;display:flex;gap:8px">
          <button class="btn btn-small btn-secondary" onclick="SystemMonitor.rebuildIndex()">🔄 Rebuild</button>
          <a class="btn btn-small btn-secondary" onclick="document.querySelector('[data-page=explorer]').click();document.getElementById('explorerSearchInput').focus()">🔍 Search</a>
        </div>
      `;
    } catch (e) {
      if (card) card.style.display = "none";
    }
  }

  async function rebuildIndex() {
    try {
      const res = await fetch(`${API_BASE}/api/index/rebuild`, { method: "POST" });
      if (res.ok) showToast("Index rebuild started");
      else showToast("Rebuild failed", "error");
    } catch (e) { showToast("Cannot reach backend", "error"); }
  }

  return { start, stop, killProcess, rebuildIndex };
})();


// ══════════════════════════════════════════════════
// INTERACTIVE TERMINAL MODULE
// ══════════════════════════════════════════════════

const TerminalModule = (() => {
  let term = null;
  let fitAddon = null;
  let ws = null;
  let initialized = false;

  function init() {
    if (initialized) {
      // already set up — just re-fit on layout change
      if (fitAddon) setTimeout(() => fitAddon.fit(), 100);
      return;
    }

    const container = document.getElementById("xtermContainer");
    if (!container) return;

    // Guard: xterm must be loaded
    if (typeof Terminal === "undefined") {
      container.innerHTML = `<div style="color:#ef4444;padding:20px">xterm.js not loaded. Check CDN connectivity.</div>`;
      return;
    }

    term = new Terminal({
      theme: {
        background: "#050810",
        foreground: "#e2e8f0",
        cursor: "#4ff3ff",
        cursorAccent: "#050810",
        selection: "rgba(79,243,255,0.2)",
        black: "#1e293b",
        red: "#f87171",
        green: "#4ade80",
        yellow: "#facc15",
        blue: "#60a5fa",
        magenta: "#a78bfa",
        cyan: "#4ff3ff",
        white: "#e2e8f0",
        brightBlack: "#475569",
        brightRed: "#fca5a5",
        brightGreen: "#86efac",
        brightYellow: "#fde047",
        brightBlue: "#93c5fd",
        brightMagenta: "#c4b5fd",
        brightCyan: "#67e8f9",
        brightWhite: "#f8fafc",
      },
      fontFamily: '"JetBrains Mono", "Cascadia Code", monospace',
      fontSize: 14,
      lineHeight: 1.4,
      cursorBlink: true,
      cursorStyle: "bar",
      scrollback: 5000,
      allowTransparency: true,
    });

    if (typeof FitAddon !== "undefined") {
      fitAddon = new FitAddon.FitAddon();
      term.loadAddon(fitAddon);
    }

    term.open(container);
    if (fitAddon) fitAddon.fit();

    const statusEl = document.getElementById("terminalStatus");
    if (statusEl) statusEl.textContent = "CONNECTING…";

    connectWebSocket();
    initialized = true;

    // Re-fit on window resize
    window.addEventListener("resize", () => {
      if (fitAddon) fitAddon.fit();
    });
  }

  function connectWebSocket() {
    const wsUrl = `ws://${location.hostname}:8000/ws/terminal`;
    ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      const statusEl = document.getElementById("terminalStatus");
      if (statusEl) statusEl.textContent = "SHELL ACTIVE";
      term.write("\r\n\x1b[1;36m╔══════════════════════════════════════╗\x1b[0m\r\n");
      term.write("\x1b[1;36m║   AEGIS Interactive Terminal          ║\x1b[0m\r\n");
      term.write("\x1b[1;36m╚══════════════════════════════════════╝\x1b[0m\r\n\r\n");
      // Send initial resize
      sendResize();
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "output") {
          term.write(msg.data);
        } else if (msg.type === "exit") {
          term.write("\r\n\x1b[1;33m[Shell exited]\x1b[0m\r\n");
          const statusEl = document.getElementById("terminalStatus");
          if (statusEl) statusEl.textContent = "SHELL EXITED";
          initialized = false;
        } else if (msg.type === "error") {
          term.write(`\r\n\x1b[1;31m[Error: ${msg.message}]\x1b[0m\r\n`);
        }
      } catch (e) {}
    };

    ws.onclose = () => {
      const statusEl = document.getElementById("terminalStatus");
      if (statusEl) statusEl.textContent = "DISCONNECTED";
      term?.write("\r\n\x1b[1;31m[Connection closed — navigate away and back to reconnect]\x1b[0m\r\n");
      initialized = false;
    };

    ws.onerror = () => {
      term?.write("\r\n\x1b[1;31m[WebSocket error — is the backend running?]\x1b[0m\r\n");
    };

    // Forward keyboard input
    term.onData((data) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data }));
      }
    });

    // Forward resize
    term.onResize(({ cols, rows }) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", rows, cols }));
      }
    });
  }

  function sendResize() {
    if (!term || !ws || ws.readyState !== WebSocket.OPEN) return;
    const dims = fitAddon ? { cols: term.cols, rows: term.rows } : { cols: 80, rows: 24 };
    ws.send(JSON.stringify({ type: "resize", ...dims }));
  }

  return { init };
})();


// ══════════════════════════════════════════════════
// WEB INTEL MODULE
// ══════════════════════════════════════════════════

const WebIntel = (() => {
  let initialized = false;

  function init() {
    if (initialized) return;
    initialized = true;

    const searchBtn = document.getElementById("webSearchBtn");
    const searchInput = document.getElementById("webSearchInput");
    const scrapeBtn = document.getElementById("webScrapeBtn");
    const scrapeInput = document.getElementById("webScrapeInput");

    if (searchBtn) {
      searchBtn.addEventListener("click", () => runSearch());
      searchInput?.addEventListener("keydown", (e) => { if (e.key === "Enter") runSearch(); });
    }
    if (scrapeBtn) {
      scrapeBtn.addEventListener("click", () => runScrape());
      scrapeInput?.addEventListener("keydown", (e) => { if (e.key === "Enter") runScrape(); });
    }
  }

  async function runSearch() {
    const input = document.getElementById("webSearchInput");
    const results = document.getElementById("webSearchResults");
    const query = input?.value.trim();
    if (!query || !results) return;

    results.innerHTML = `<div class="webintel-loading"><div class="loading-spinner"></div><span>Scanning the web for "${escapeHtml(query)}"…</span></div>`;

    const btn = document.getElementById("webSearchBtn");
    if (btn) btn.disabled = true;

    try {
      const res = await fetch(`${API_BASE}/api/web/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, max_results: 8 }),
      });
      const data = await res.json();

      if (!res.ok) {
        results.innerHTML = `<div class="empty-state"><p>⚠️ ${escapeHtml(data.detail || "Search failed")}</p></div>`;
        return;
      }

      if (!data.results?.length) {
        results.innerHTML = `<div class="empty-state"><p>No results found for "${escapeHtml(query)}"</p></div>`;
        return;
      }

      results.innerHTML = `
        <div class="webintel-result-meta">Found ${data.count} result${data.count !== 1 ? "s" : ""} for <strong>"${escapeHtml(query)}"</strong></div>
        ${data.results.map((r, i) => `
          <div class="webintel-result-card" style="animation-delay:${i * 0.06}s">
            <div class="result-favicon">🌐</div>
            <div class="result-body">
              <a class="result-title" href="${escapeHtml(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.title || r.url)}</a>
              <div class="result-url">${escapeHtml(r.url)}</div>
              ${r.snippet ? `<div class="result-snippet">${escapeHtml(r.snippet)}</div>` : ""}
              <div class="result-actions">
                <button class="btn btn-small btn-secondary" onclick="WebIntel.scrapeUrl('${r.url.replace(/'/g, "\\'")}')">📄 Fetch Full Page</button>
              </div>
            </div>
          </div>`).join("")}`;
    } catch (e) {
      results.innerHTML = `<div class="empty-state"><p>⚠️ Network error — is the backend running?</p></div>`;
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function runScrape(url) {
    const input = document.getElementById("webScrapeInput");
    const output = document.getElementById("webScrapeOutput");
    const targetUrl = url || input?.value.trim();
    if (!targetUrl || !output) return;

    if (input && !url) {
      // Update input if using manual entry
    } else if (input) {
      input.value = targetUrl;
    }

    output.innerHTML = `<div class="webintel-loading"><div class="loading-spinner"></div><span>Fetching ${escapeHtml(targetUrl)}…</span></div>`;

    const btn = document.getElementById("webScrapeBtn");
    if (btn) btn.disabled = true;

    try {
      const res = await fetch(`${API_BASE}/api/web/scrape`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: targetUrl, max_length: 8000 }),
      });
      const data = await res.json();

      if (!res.ok) {
        output.innerHTML = `<div class="webintel-scrape-error">⚠️ ${escapeHtml(data.detail || "Fetch failed")}</div>`;
        return;
      }

      const linksHtml = data.links?.slice(0, 10).map(l =>
        `<a href="${escapeHtml(l.url)}" target="_blank" rel="noopener" class="scrape-link">${escapeHtml(l.text || l.url)}</a>`
      ).join("") || "";

      output.innerHTML = `
        <div class="scrape-header">
          <div class="scrape-title">${escapeHtml(data.title || targetUrl)}</div>
          <div class="scrape-meta"><a href="${escapeHtml(data.url)}" target="_blank" rel="noopener">${escapeHtml(data.url)}</a>${data.truncated ? " · <em>truncated</em>" : ""}</div>
        </div>
        <pre class="scrape-content">${escapeHtml(data.text || "")}</pre>
        ${linksHtml ? `<div class="scrape-links-section"><strong>Links extracted:</strong><div class="scrape-links">${linksHtml}</div></div>` : ""}`;
    } catch (e) {
      output.innerHTML = `<div class="webintel-scrape-error">⚠️ Cannot reach backend</div>`;
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function scrapeUrl(url) {
    const input = document.getElementById("webScrapeInput");
    const scrapeCard = document.querySelector(".webintel-scrape-card");
    if (input) input.value = url;
    if (scrapeCard) scrapeCard.scrollIntoView({ behavior: "smooth" });
    runScrape(url);
  }

  return { init, scrapeUrl };
})();

// ══════════════════════════════════════════════════
// FILE EXPLORER MODULE
// ══════════════════════════════════════════════════

const Explorer = (() => {
  // ─── State ──────────────────────────────────
  let currentPath = null;
  let historyStack = [];
  let historyIndex = -1;
  let viewMode = "grid"; // 'grid' | 'list'
  let selectedEntry = null;
  let isSearchMode = false;
  let bookmarks = [];

  // ─── DOM refs ───────────────────────────────
  const el = (id) => document.getElementById(id);

  // ─── Init ───────────────────────────────────
  async function init() {
    await loadCommonFolders();
    await loadBookmarks();
    await loadRecentFolders();
    await navigate("~");
  }

  // ─── Navigation ─────────────────────────────
  async function navigate(path, addToHistory = true) {
    const expanded = path === "~" ? await getHomePath() : path;

    if (addToHistory) {
      // Trim forward history
      historyStack = historyStack.slice(0, historyIndex + 1);
      historyStack.push(expanded);
      historyIndex = historyStack.length - 1;
    }

    currentPath = expanded;
    updateNavButtons();
    updateBreadcrumb(expanded);
    isSearchMode = false;

    // Remove search banner if present
    const banner = document.querySelector(".search-results-banner");
    if (banner) banner.remove();

    await browseDirectory(expanded);
    await recordRecent(expanded);
    await loadRecentFolders();
    highlightActiveSidebarItem(expanded);
  }

  async function getHomePath() {
    try {
      const data = await apiFetch("/api/browse/common-folders");
      return data["Home"]?.path || "~";
    } catch {
      return "~";
    }
  }

  function goBack() {
    if (historyIndex > 0) {
      historyIndex--;
      navigate(historyStack[historyIndex], false);
    }
  }

  function goForward() {
    if (historyIndex < historyStack.length - 1) {
      historyIndex++;
      navigate(historyStack[historyIndex], false);
    }
  }

  function goUp() {
    if (!currentPath || currentPath === "/") return;
    const parts = currentPath.split("/").filter(Boolean);
    const parent = parts.length <= 1 ? "/" : "/" + parts.slice(0, -1).join("/");
    navigate(parent);
  }

  function updateNavButtons() {
    el("explorerBack").disabled = historyIndex <= 0;
    el("explorerForward").disabled = historyIndex >= historyStack.length - 1;
  }

  // ─── Breadcrumb ─────────────────────────────
  function updateBreadcrumb(path) {
    const crumb = el("explorerBreadcrumb");
    const parts = path.split("/").filter(Boolean);
    let html = `<span class="breadcrumb-item" data-path="/">/ root</span>`;
    let built = "";
    parts.forEach((part, i) => {
      built += "/" + part;
      const p = built;
      const isCurrent = i === parts.length - 1;
      html += `<span class="breadcrumb-sep">/</span>`;
      html += `<span class="breadcrumb-item ${isCurrent ? "current" : ""}" data-path="${escapeHtml(p)}">${escapeHtml(part)}</span>`;
    });
    crumb.innerHTML = html;
    crumb.querySelectorAll(".breadcrumb-item:not(.current)").forEach((item) => {
      item.addEventListener("click", () => navigate(item.dataset.path));
    });
    // Scroll to end
    crumb.scrollLeft = crumb.scrollWidth;
  }

  // ─── Browse ─────────────────────────────────
  async function browseDirectory(path) {
    showLoading();
    try {
      const showHidden = el("explorerShowHidden").checked;
      const sortBy = el("explorerSort").value;
      const params = new URLSearchParams({
        path,
        show_hidden: showHidden,
        sort_by: sortBy,
      });
      const data = await apiFetch(`/api/browse?${params}`);
      renderEntries(data.entries, data);
    } catch (err) {
      showError(`Cannot browse: ${err.message}`);
    }
  }

  function renderEntries(entries, meta = {}) {
    const container = el("explorerFiles");
    const status = el("explorerStatusText");

    if (meta.path) {
      status.textContent = `${meta.dirs || 0} folders, ${meta.files || 0} files · ${meta.path}`;
    }

    if (!entries || entries.length === 0) {
      container.innerHTML = `<div class="explorer-empty">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                <p>This folder is empty</p>
            </div>`;
      return;
    }

    if (viewMode === "grid") renderGrid(entries, container);
    else renderList(entries, container);
  }

  function renderGrid(entries, container) {
    const grid = document.createElement("div");
    grid.className = "files-grid";
    entries.forEach((entry) => {
      const card = document.createElement("div");
      card.className = `file-card ${entry.is_dir ? "dir-card" : ""}`;
      const icon = entry.is_dir ? "📁" : getFileIcon(entry.name);
      const size = entry.is_dir
        ? ""
        : `<div class="file-size">${entry.size_formatted || formatSize(entry.size)}</div>`;
      card.innerHTML = `<div class="file-icon">${icon}</div><div class="file-name">${escapeHtml(entry.name)}</div>${size}`;
      card.addEventListener("click", () => onEntryClick(entry, card));
      card.addEventListener("dblclick", () => onEntryDblClick(entry));
      grid.appendChild(card);
    });
    container.innerHTML = "";
    container.appendChild(grid);
  }

  function renderList(entries, container) {
    const wrap = document.createElement("div");
    wrap.className = "files-list";
    const header = document.createElement("div");
    header.className = "list-header";
    header.innerHTML = `<span></span><span>Name</span><span>Size</span><span>Modified</span><span>Permissions</span>`;
    wrap.appendChild(header);
    entries.forEach((entry) => {
      const row = document.createElement("div");
      row.className = "file-list-row";
      const icon = entry.is_dir ? "📁" : getFileIcon(entry.name);
      const size = entry.is_dir
        ? "—"
        : entry.size_formatted || formatSize(entry.size);
      const mod = entry.modified
        ? new Date(entry.modified).toLocaleDateString()
        : "—";
      const perms = entry.permissions || "";
      row.innerHTML = `
                <span class="row-icon">${icon}</span>
                <span class="row-name">${escapeHtml(entry.name)}</span>
                <span class="row-size">${size}</span>
                <span class="row-modified">${mod}</span>
                <span class="row-perms">${escapeHtml(perms)}</span>`;
      row.addEventListener("click", () => onEntryClick(entry, row));
      row.addEventListener("dblclick", () => onEntryDblClick(entry));
      wrap.appendChild(row);
    });
    container.innerHTML = "";
    container.appendChild(wrap);
  }

  function onEntryClick(entry, el_) {
    // Deselect all
    document
      .querySelectorAll(".file-card.selected, .file-list-row.selected")
      .forEach((e) => e.classList.remove("selected"));
    el_.classList.add("selected");
    selectedEntry = entry;
    if (isSearchMode) {
      // In search mode, single-click opens the file or navigates to directory
      onEntryDblClick(entry);
    } else {
      showInfoPanel(entry);
    }
  }

  function onEntryDblClick(entry) {
    if (entry.is_dir) {
      navigate(entry.path);
    } else {
      openFile(entry.path);
    }
  }

  // ─── Info Panel ─────────────────────────────
  function showInfoPanel(entry) {
    el("infoPanelEmpty").style.display = "none";
    el("infoPanelContent").style.display = "block";
    const icon = entry.is_dir ? "📁" : getFileIcon(entry.name);
    const rows = [
      ["Type", entry.is_dir ? "Directory" : entry.extension || "File"],
      [
        "Size",
        entry.is_dir ? "—" : entry.size_formatted || formatSize(entry.size),
      ],
      ["Owner", entry.owner || "—"],
      ["Perms", entry.permissions || "—"],
      [
        "Modified",
        entry.modified ? new Date(entry.modified).toLocaleString() : "—",
      ],
      [
        "Created",
        entry.created ? new Date(entry.created).toLocaleString() : "—",
      ],
      ["Path", entry.path],
    ];
    const tableRows = rows
      .map(
        ([k, v]) => `<tr><td>${k}</td><td>${escapeHtml(String(v))}</td></tr>`,
      )
      .join("");

    const safePath = entry.path.replace(/'/g, "\\'");
    const actions = entry.is_dir
      ? `<button class="info-action-btn" onclick="Explorer.navigateTo('${safePath}')">📂 Open</button>
               <button class="info-action-btn" onclick="Explorer.sendToChat('Browse ${entry.path}')">💬 Chat</button>`
      : `<button class="info-action-btn" onclick="Explorer.openFile('${safePath}')">🚀 Open</button>
               <button class="info-action-btn" onclick="Explorer.previewFile('${safePath}')">👁️ Preview</button>
               <button class="info-action-btn" onclick="Explorer.sendToChat('Show metadata for ${entry.path}')">ℹ️ Info</button>
               <button class="info-action-btn" onclick="Explorer.sendToChat('Copy ${entry.path} to ...')">📋 Copy</button>
               <button class="info-action-btn danger" onclick="Explorer.sendToChat('Delete ${entry.path}')">🗑️ Delete</button>`;

    el("infoPanelContent").innerHTML = `
            <div class="info-panel-icon">${icon}</div>
            <div class="info-panel-name">${escapeHtml(entry.name)}</div>
            <div class="info-panel-actions">${actions}</div>
            <table class="info-meta-table">${tableRows}</table>
            <div id="filePreviewArea"></div>`;
  }

  function hideInfoPanel() {
    el("infoPanelEmpty").style.display = "";
    el("infoPanelContent").style.display = "none";
    selectedEntry = null;
  }

  // ─── Quick access sidebar ────────────────────
  async function loadCommonFolders() {
    try {
      const data = await apiFetch("/api/browse/common-folders");
      const container = el("commonFolders");
      container.innerHTML = "";
      const folderSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`;
      Object.entries(data).forEach(([name, info]) => {
        if (!info.exists) return;
        const item = document.createElement("div");
        item.className = "sidebar-folder-item";
        item.innerHTML = `${folderSvg}<span class="folder-name">${escapeHtml(name)}</span>`;
        item.dataset.path = info.path;
        item.addEventListener("click", () => navigate(info.path));
        container.appendChild(item);
      });
    } catch {}
  }

  async function loadBookmarks() {
    try {
      bookmarks = await apiFetch("/api/bookmarks");
      renderBookmarks();
    } catch {}
  }

  function renderBookmarks() {
    const container = el("bookmarkList");
    el("bookmarkCount").textContent = bookmarks.length;
    if (bookmarks.length === 0) {
      container.innerHTML = `<div style="padding:6px 14px;font-size:0.75rem;color:var(--text-muted)">No bookmarks yet</div>`;
      return;
    }
    const folderSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/></svg>`;
    container.innerHTML = "";
    bookmarks.forEach((path) => {
      const name = path.split("/").pop() || path;
      const item = document.createElement("div");
      item.className = "sidebar-folder-item";
      item.innerHTML = `${folderSvg}<span class="folder-name" title="${escapeHtml(path)}">${escapeHtml(name)}</span>
                <button class="folder-remove" title="Remove bookmark">✕</button>`;
      item.addEventListener("click", (e) => {
        if (!e.target.classList.contains("folder-remove")) navigate(path);
      });
      item
        .querySelector(".folder-remove")
        .addEventListener("click", async (e) => {
          e.stopPropagation();
          await apiFetch(`/api/bookmarks?path=${encodeURIComponent(path)}`, {
            method: "DELETE",
          });
          await loadBookmarks();
        });
      container.appendChild(item);
    });
  }

  async function loadRecentFolders() {
    try {
      const recent = await apiFetch("/api/recent-folders");
      const container = el("recentFolders");
      if (recent.length === 0) {
        container.innerHTML = `<div style="padding:6px 14px;font-size:0.75rem;color:var(--text-muted)">No recent folders</div>`;
        return;
      }
      const folderSvg = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`;
      container.innerHTML = "";
      recent.slice(0, 8).forEach((path) => {
        const name = path.split("/").pop() || path;
        const item = document.createElement("div");
        item.className = "sidebar-folder-item";
        item.innerHTML = `${folderSvg}<span class="folder-name" title="${escapeHtml(path)}">${escapeHtml(name)}</span>`;
        item.addEventListener("click", () => navigate(path));
        container.appendChild(item);
      });
    } catch {}
  }

  async function recordRecent(path) {
    try {
      await apiFetch(`/api/recent-folders?path=${encodeURIComponent(path)}`, {
        method: "POST",
      });
    } catch {}
  }

  async function toggleBookmark() {
    if (!currentPath) return;
    const isBookmarked = bookmarks.includes(currentPath);
    if (isBookmarked) {
      await apiFetch(`/api/bookmarks?path=${encodeURIComponent(currentPath)}`, {
        method: "DELETE",
      });
    } else {
      await apiFetch(`/api/bookmarks?path=${encodeURIComponent(currentPath)}`, {
        method: "POST",
      });
    }
    await loadBookmarks();
    updateBookmarkBtn();
  }

  function updateBookmarkBtn() {
    const btn = el("explorerBookmark");
    const isBookmarked = bookmarks.includes(currentPath);
    btn.classList.toggle("active-btn", isBookmarked);
    btn.title = isBookmarked ? "Remove bookmark" : "Bookmark this folder";
  }

  function highlightActiveSidebarItem(path) {
    document.querySelectorAll(".sidebar-folder-item").forEach((item) => {
      item.classList.toggle("active-folder", item.dataset.path === path);
    });
    updateBookmarkBtn();
  }

  // ─── Search ─────────────────────────────────
  async function runSearch() {
    const query = el("explorerSearchInput").value.trim();
    const searchMode = el("filterSearchMode").value;

    if (!query && searchMode !== "filename") {
      showError("Please enter a search query");
      return;
    }

    showLoading();
    isSearchMode = true;

    try {
      let data;
      const basePath = currentPath || "~";

      switch (searchMode) {
        case "documents":
          data = await apiFetch("/api/search/documents", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              path: basePath,
              query,
              extensions: el("filterExt").value,
              case_sensitive: false,
              max_files: 50,
              max_results: 30,
              recursive: true,
            }),
          });
          data.results = data.results || [];
          break;

        case "semantic":
          data = await apiFetch("/api/search/semantic", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              path: basePath,
              query,
              extensions: el("filterExt").value,
              max_files: 50,
              max_results: 30,
              recursive: true,
            }),
          });
          data.results = data.results || [];
          break;

        case "code":
          data = await apiFetch("/api/search/code", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              path: basePath,
              query,
              language: el("filterLang").value,
              search_in: "all",
              max_results: 30,
              recursive: true,
              include_tests: true,
            }),
          });
          data.results = data.results || [];
          break;

        default: // filename
          data = await apiFetch("/api/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              path: basePath,
              query,
              fuzzy: el("filterFuzzy").checked,
              regex: el("filterRegex").checked,
              extensions: el("filterExt").value,
              min_size: el("filterMinSize").value,
              max_size: el("filterMaxSize").value,
              modified_after: el("filterAfter").value,
              modified_before: el("filterBefore").value,
              created_after: el("filterCreatedAfter").value,
              created_before: el("filterCreatedBefore").value,
              owner: el("filterOwner").value,
              include_hidden: el("filterHidden").checked,
              include_dirs: el("filterDirs").checked,
              recursive: true,
            }),
          });
          data.results = data.results || [];
          break;
      }

      // Show banner
      const existingBanner = document.querySelector(".search-results-banner");
      if (existingBanner) existingBanner.remove();
      const banner = document.createElement("div");
      banner.className = "search-results-banner";
      const resultCount = data.total != null ? data.total : data.results.length;
      banner.innerHTML = `🔍 Found <strong>${resultCount}</strong> result${resultCount !== 1 ? "s" : ""} for "${escapeHtml(query || "(filters)")}${data.truncated ? " (truncated)" : ""}"
                <button onclick="Explorer.clearSearch()">✕ Clear</button>`;
      el("explorerMain")?.insertBefore(banner, el("explorerFiles")) ||
        el("explorerFiles").parentNode.insertBefore(
          banner,
          el("explorerFiles"),
        );

      renderEntries(data.results, { path: currentPath });
      el("explorerStatusText").textContent =
        `${data.results.length} results · ${searchMode} search in ${currentPath}`;
    } catch (err) {
      showError(`Search failed: ${err.message}`);
    }
  }

  function clearSearch() {
    el("explorerSearchInput").value = "";
    el("explorerSearchClear").style.display = "none";
    isSearchMode = false;
    const banner = document.querySelector(".search-results-banner");
    if (banner) banner.remove();
    browseDirectory(currentPath);
  }

  // ─── View mode ──────────────────────────────
  function setViewMode(mode) {
    viewMode = mode;
    el("viewGrid").classList.toggle("active", mode === "grid");
    el("viewList").classList.toggle("active", mode === "list");
    if (!isSearchMode) browseDirectory(currentPath);
  }

  // ─── Helpers ────────────────────────────────
  function showLoading() {
    el("explorerFiles").innerHTML =
      `<div class="explorer-loading"><div class="loading-spinner"></div><span>Loading...</span></div>`;
  }

  function showError(msg) {
    el("explorerFiles").innerHTML =
      `<div class="explorer-empty"><p>⚠️ ${escapeHtml(msg)}</p></div>`;
    el("explorerStatusText").textContent = "Error";
  }

  async function apiFetch(url, opts = {}) {
    const res = await fetch(`${API_BASE}${url}`, opts);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }

  // ─── Public API ─────────────────────────────
  function navigateTo(path) {
    navigate(path);
  }

  function sendToChat(text) {
    document
      .querySelectorAll(".nav-item")
      .forEach((b) => b.classList.remove("active"));
    document
      .querySelectorAll(".page")
      .forEach((p) => p.classList.remove("active"));
    document.getElementById("nav-chat").classList.add("active");
    document.getElementById("page-chat").classList.add("active");
    chatInput.value = text;
    chatInput.focus();
  }

  // ─── Wire up events ─────────────────────────
  function wireEvents() {
    el("explorerBack").addEventListener("click", goBack);
    el("explorerForward").addEventListener("click", goForward);
    el("explorerUp").addEventListener("click", goUp);
    el("explorerRefresh").addEventListener("click", () =>
      browseDirectory(currentPath),
    );
    el("explorerBookmark").addEventListener("click", toggleBookmark);
    el("explorerShowHidden").addEventListener("change", () =>
      browseDirectory(currentPath),
    );
    el("explorerSort").addEventListener("change", () =>
      browseDirectory(currentPath),
    );

    el("viewGrid").addEventListener("click", () => setViewMode("grid"));
    el("viewList").addEventListener("click", () => setViewMode("list"));

    el("explorerSearchToggleFilters").addEventListener("click", () => {
      const f = el("explorerFilters");
      f.style.display = f.style.display === "none" ? "block" : "none";
    });

    el("explorerSearchInput").addEventListener("input", (e) => {
      el("explorerSearchClear").style.display = e.target.value
        ? "flex"
        : "none";
    });

    el("explorerSearchInput").addEventListener("keydown", (e) => {
      if (e.key === "Enter") runSearch();
      if (e.key === "Escape") clearSearch();
    });

    el("explorerSearchClear").addEventListener("click", clearSearch);
    el("runSearch").addEventListener("click", runSearch);
    el("clearFilters").addEventListener("click", () => {
      [
        "filterExt",
        "filterMinSize",
        "filterMaxSize",
        "filterAfter",
        "filterBefore",
        "filterCreatedAfter",
        "filterCreatedBefore",
        "filterOwner",
      ].forEach((id) => (el(id).value = ""));
      [
        "filterFuzzy",
        "filterRegex",
        "filterHidden",
        "filterDirs",
        "filterContent",
      ].forEach((id) => (el(id).checked = false));
      el("filterSearchMode").value = "filename";
      el("filterLang").value = "";
      updateFilterVisibility();
    });

    // Search mode toggle — show/hide relevant filters
    function updateFilterVisibility() {
      const mode = el("filterSearchMode").value;
      const isFilename = mode === "filename";
      const isCode = mode === "code";
      // Show filename/metadata filters only in filename mode
      [
        "filterFuzzyWrap",
        "filterRegexWrap",
        "filterHiddenWrap",
        "filterDirsWrap",
      ].forEach((id) => {
        el(id).style.display = isFilename ? "" : "none";
      });
      el("filterContentWrap").style.display = "none";
      // Show language filter only in code mode
      el("filterLangGroup").style.display = isCode ? "" : "none";
      // Show extension filter in filename and documents mode
      el("filterExt").closest(".filter-group").style.display =
        isFilename || mode === "documents" ? "" : "none";
      // Placeholder
      el("explorerSearchInput").placeholder = isCode
        ? "Search code (function, class, variable)..."
        : mode === "semantic"
          ? "Describe what you're looking for..."
          : mode === "documents"
            ? "Search inside documents..."
            : "Search files... (press / to focus)";
    }
    el("filterSearchMode").addEventListener("change", updateFilterVisibility);
    updateFilterVisibility();

    // Keyboard shortcut: / to focus search
    document.addEventListener("keydown", (e) => {
      if (
        e.key === "/" &&
        document.getElementById("page-explorer").classList.contains("active") &&
        document.activeElement.tagName !== "INPUT" &&
        document.activeElement.tagName !== "TEXTAREA"
      ) {
        e.preventDefault();
        el("explorerSearchInput").focus();
      }
    });

    // Init when explorer page is opened
    document.getElementById("nav-explorer").addEventListener("click", () => {
      if (!currentPath) init();
    });
  }

  wireEvents();

  // ─── Open file with system app ──────────────
  async function openFile(path) {
    try {
      const res = await fetch(
        `${API_BASE}/api/open?path=${encodeURIComponent(path)}`,
        {
          method: "POST",
        },
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || "Failed to open file", "error");
      } else {
        showToast(`Opened: ${path.split("/").pop()}`);
      }
    } catch (err) {
      showToast("Cannot connect to backend", "error");
    }
  }

  // ─── Preview file content inline ────────────
  async function previewFile(path) {
    const area = document.getElementById("filePreviewArea");
    if (!area) return;

    area.innerHTML = `<div class="file-preview-loading"><div class="loading-spinner" style="width:20px;height:20px;border-width:2px"></div> Loading preview...</div>`;

    try {
      const res = await fetch(
        `${API_BASE}/api/preview?path=${encodeURIComponent(path)}`,
      );
      const data = await res.json();

      if (!data.success) {
        // Binary or too large — show appropriate message
        if (data.data?.binary) {
          area.innerHTML = `<div class="file-preview-msg">
                        <p>🔒 Binary file (${escapeHtml(data.data.extension || "")})</p>
                        <button class="info-action-btn" onclick="Explorer.openFile('${path.replace(/'/g, "\\'")}')">🚀 Open with system app</button>
                    </div>`;
        } else if (data.data?.too_large) {
          area.innerHTML = `<div class="file-preview-msg">
                        <p>📦 File too large for preview (${formatSize(data.data.size)})</p>
                        <button class="info-action-btn" onclick="Explorer.openFile('${path.replace(/'/g, "\\'")}')">🚀 Open with system app</button>
                    </div>`;
        } else {
          area.innerHTML = `<div class="file-preview-msg"><p>⚠️ ${escapeHtml(data.message)}</p></div>`;
        }
        return;
      }

      const d = data.data;
      const ext = d.extension || "";
      const lang =
        {
          ".py": "python",
          ".js": "javascript",
          ".ts": "typescript",
          ".html": "html",
          ".css": "css",
          ".json": "json",
          ".yaml": "yaml",
          ".yml": "yaml",
          ".md": "markdown",
          ".sh": "bash",
          ".rs": "rust",
          ".go": "go",
          ".c": "c",
          ".cpp": "cpp",
          ".java": "java",
          ".rb": "ruby",
          ".xml": "xml",
          ".sql": "sql",
          ".toml": "toml",
        }[ext] || "";

      area.innerHTML = `
                <div class="file-preview-header">
                    <span>📄 Preview · ${d.lines} lines${d.truncated ? " (truncated)" : ""} · ${formatSize(d.size)}</span>
                    <button class="explorer-btn" onclick="Explorer.openFile('${path.replace(/'/g, "\\'")}')">🚀 Open</button>
                </div>
                <pre class="file-preview-code" data-lang="${lang}"><code>${escapeHtml(d.content)}</code></pre>`;
    } catch (err) {
      area.innerHTML = `<div class="file-preview-msg"><p>⚠️ ${escapeHtml(err.message)}</p></div>`;
    }
  }

  return { init, navigateTo, sendToChat, clearSearch, openFile, previewFile };
})();
