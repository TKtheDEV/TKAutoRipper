/* global showToast, toggleTheme */
document.addEventListener("DOMContentLoaded", () => {
  // theme init (re-use helpers from settings/dashboard)
  const mode = getCookie("theme") ??
               (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  applyTheme(mode);

  const jobId = document.body.dataset.jobId;
  openWebSocket(jobId);
});

// ---------- helpers ---------- //
function openWebSocket(jobId) {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/jobs/${jobId}`);
  const logBox   = document.getElementById("log-window");
  const pctBar   = document.getElementById("overall-pct");
  const statusEl = document.getElementById("job-status");
  const stepEl   = document.getElementById("job-step");

  ws.onmessage = ({ data }) => {
    const msg = JSON.parse(data);

    if (msg.line) {
      logBox.textContent += msg.line + "\n";
      logBox.scrollTop = logBox.scrollHeight;          // auto-scroll
    }
    if (msg.progress !== undefined) pctBar.value = msg.progress;
    if (msg.status)   statusEl.textContent = msg.status;
    if (msg.step)     stepEl.textContent   = msg.step;
  };

  ws.onclose = () => showToast("WebSocket closed", "error");
}

async function resumeJob() {
  const jobId = document.body.dataset.jobId;
  const res = await fetch(`/jobs/${jobId}/resume`, { method: "PUT" });
  if (!res.ok) return showToast("Resume failed!", "error");
  showToast("Job resumed"); location.reload();
}

async function deleteJob() {
  if (!confirm("Delete this job and its temp files?")) return;
  const jobId = document.body.dataset.jobId;
  const res = await fetch(`/jobs/${jobId}`, { method: "DELETE" });
  if (!res.ok) return showToast("Delete failed!", "error");
  showToast("Job deleted"); window.location = "/";
}

// ---------- minimal cookie/theme helpers (mirrors settings.html) ---------- //
function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : null;
}

function setCookie(name, value, days = 365) {
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/`;
}

function applyTheme(mode) {
  const icon = document.getElementById("theme-icon");
  document.documentElement.classList.remove("dark-mode", "light-mode");
  document.documentElement.classList.add(`${mode}-mode`);
  if (icon) icon.textContent = mode === "dark" ? "🌙" : "☀️";
}

function toggleTheme() {
  const current = getCookie("theme") || "light";
  const next = current === "light" ? "dark" : "light";
  applyTheme(next);
  setCookie("theme", next);
}

function showToast(message, type = "success") {
  const toast = document.getElementById("toast");
  const wrapper = document.createElement("div");
  wrapper.classList.add("toast-msg");
  if (type === "error") wrapper.style.borderLeft = "5px solid red";
  wrapper.textContent = message;
  toast.appendChild(wrapper);
  setTimeout(() => wrapper.classList.add("fade-out"), 3000);
  setTimeout(() => wrapper.remove(), 4000);
}
