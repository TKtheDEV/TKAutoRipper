/* global showToast, toggleTheme */

document.addEventListener("DOMContentLoaded", async () => {
  // Theme
  const mode = getCookie("theme") ??
               (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  applyTheme(mode);

  const jobId    = document.body.dataset.jobId;
  const discType = (document.body.dataset.discType || "").toLowerCase();

  // preload log
  fetch(`/jobs/${jobId}/log`)
    .then(res => res.text())
    .then(text => {
      const logBox = document.getElementById("log-window");
      if (logBox) {
        logBox.textContent = text || "";
        autoScrollLog();
      }
    }).catch(()=>{});

  // download link
  const downloadLink = document.getElementById("download-log");
  if (downloadLink) downloadLink.href = `/jobs/${jobId}/log`;

  // Output path hints
  const outputInput = document.getElementById("output-path");
  if (["dvd_video","bluray_video","cd_audio"].includes(discType)) {
    outputInput.placeholder = "/media/Library/Movies   (folder only)";
    outputInput.title = "For video/audio discs, choose a folder (no filename).";
  } else if (["cd_rom","dvd_rom","bluray_rom"].includes(discType)) {
    outputInput.placeholder = "/media/ISOs/MyDisc.iso.zst   (final file path)";
    outputInput.title = "For ROM discs, enter the final file path (e.g., .../MyDisc.iso or .iso.zst).";
  }

  // Prefill output + lock state
  try {
    const r = await fetch(`/api/jobs/${jobId}/output`);
    if (r.ok) {
      const j = await r.json();
      outputInput.value = j.override_filename ? `${j.output_path}/${j.override_filename}` : j.output_path;
      outputInput.disabled = !!j.locked;
      const btn  = document.getElementById("output-save");
      const hint = document.getElementById("output-lock-hint");
      if (btn)  btn.disabled  = !!j.locked;
      if (hint) hint.style.display = j.locked ? "" : "none";
    }
  } catch {}

  // OMDb search
  const q           = document.getElementById("omdb-query");
  const pop         = document.getElementById("omdb-results");
  const seasonInput = document.getElementById("omdb-season");
  const imdbInput   = document.getElementById("omdb-imdbid");
  const applyBtn    = document.getElementById("omdb-apply");
  const pickedBox   = document.getElementById("omdb-picked");
  let picked = null, debounceT = null;

  function hidePop(){ if (pop) pop.style.display="none"; }
  function showPop(){ if (pop) pop.style.display=""; }
  function imdbOk(v){ return /^tt\d{7,}$/.test(v.trim()); }

  function renderResults(items){
    if (!pop) return;
    pop.innerHTML = "";
    items.forEach(it => {
      const li = document.createElement("li");
      li.textContent = `${it.Title} (${it.Year}) [${it.Type}]`;
      li.addEventListener("click", () => {
        picked = it;
        q.value = it.Title;
        imdbInput.value = it.imdbID || "";
        const isSeries = (it.Type || "").toLowerCase() === "series";
        seasonInput.disabled = !isSeries;
        seasonInput.placeholder = isSeries ? "e.g. 5" : "—";
        if (!isSeries) seasonInput.value = "";
        pickedBox.style.display = "";
        pickedBox.textContent = `Selected: ${it.Title} (${it.Year}) – ${it.imdbID}`;
        applyBtn.disabled = !(imdbInput.value && imdbOk(imdbInput.value));
        hidePop();
      });
      pop.appendChild(li);
    });
    showPop();
  }

  async function searchNow(){
    const v = (q?.value || "").trim();
    if (v.length < 2){ hidePop(); return; }
    try{
      const r = await fetch(`/api/omdb/search?q=${encodeURIComponent(v)}`);
      const j = await r.json();
      renderResults(j.results || []);
    }catch{}
  }

  q?.addEventListener("input", ()=>{
    clearTimeout(debounceT); debounceT = setTimeout(searchNow, 250);
  });
  q?.addEventListener("focus", ()=>{ if ((q.value || "").trim().length >= 2) searchNow(); });
  document.addEventListener("click", (e)=>{ if (e.target !== q && !pop.contains(e.target)) hidePop(); });

  imdbInput.addEventListener("input", ()=>{
    applyBtn.disabled = !imdbOk(imdbInput.value);
  });

  // WebSocket for progress/log
  openWebSocket(jobId);
});

// Save output (form submit)
window.saveOutput = async function saveOutput(e) {
  if (e?.preventDefault) e.preventDefault();
  const jobId    = document.body.dataset.jobId;
  const discType = (document.body.dataset.discType || "").toLowerCase();
  const input = document.getElementById("output-path");
  if (!input || !input.value.trim()) { showToast("Enter a path", "error"); return false; }
  const v = input.value.trim();

  if (["dvd_video","bluray_video","cd_audio"].includes(discType)) {
    const leaf = v.split("/").pop() || "";
    if (/\.[a-z0-9]{2,5}$/i.test(leaf)) { showToast("Provide a folder (no filename).", "error"); return false; }
  } else if (["cd_rom","dvd_rom","bluray_rom"].includes(discType)) {
    const leaf = v.split("/").pop() || "";
    if (!/\.[a-z0-9]{2,5}$/i.test(leaf)) { showToast("Provide the final file path (e.g., MyDisc.iso or .iso.zst).", "error"); return false; }
  }

  try {
    const res = await fetch(`/api/jobs/${jobId}/output`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: v })
    });
    if (!res.ok) { showToast(`Failed: ${await res.text()}`, "error"); return false; }
    const j = await res.json();
    input.value = j.override_filename ? `${j.output_path}/${j.override_filename}` : j.output_path;
    showToast("Output updated");
    return true;
  } catch { showToast("Save failed!", "error"); return false; }
};

// Apply metadata (form submit)
window.applyMetadata = async function applyMetadata(e){
  if (e?.preventDefault) e.preventDefault();
  const jobId      = document.body.dataset.jobId;
  const imdbInput  = document.getElementById("omdb-imdbid");
  const seasonInput= document.getElementById("omdb-season");
  const output     = document.getElementById("output-path");
  const imdbID = (imdbInput.value || "").trim();
  if (!/^tt\d{7,}$/.test(imdbID)) { showToast("Enter a valid IMDb ID (e.g., tt1234567) or pick a result.", "error"); return false; }
  const season = seasonInput.disabled || !seasonInput.value ? undefined : parseInt(seasonInput.value, 10);

  try{
    const url = `/api/jobs/${jobId}/imdb?imdbID=${encodeURIComponent(imdbID)}${season ? `&season=${season}` : ""}`;
    const res = await fetch(url, { method: "PUT" });
    if (!res.ok) throw new Error(await res.text());
    const j = await res.json();
    if (output) output.value = j.output_path;
    showToast("Metadata applied; output folder updated.");
    return true;
  }catch(err){ showToast("Could not apply metadata", "error"); return false; }
};

window.deleteJob = async function deleteJob() {
  const jobId = document.body.dataset.jobId;
  if (!confirm("Delete this job? If running, it will be cancelled.")) return;
  try { await fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" }); } catch {}
  location.href = "/";
};

function openWebSocket(jobId, attempt = 0) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/jobs/${jobId}`);

  const logBox     = document.getElementById("log-window");
  const overallBar = document.getElementById("overall-pct");
  const overallLbl = document.getElementById("overall-pct-label");
  const stepWrap   = document.getElementById("step-wrap");
  const stepBar    = document.getElementById("step-pct");
  const stepLbl    = document.getElementById("step-pct-label");
  const titleWrap  = document.getElementById("title-wrap");
  const titleBar   = document.getElementById("title-pct");
  const titleLbl   = document.getElementById("title-pct-label");
  const statusEl   = document.getElementById("job-status");
  const stepEl     = document.getElementById("job-step");

  function applyProgress(msg) {
    if (typeof msg.progress === "number") {
      overallBar.value = msg.progress; overallLbl.textContent = `${msg.progress}%`;
    }
    if (typeof msg.step_progress === "number") {
      const showStep = msg.step_progress > 0;
      stepWrap.style.display = showStep ? "" : "none";
      stepBar.value = msg.step_progress; stepLbl.textContent = `${msg.step_progress}%`;
    }
    if (typeof msg.title_progress === "number") {
      const showTitle = msg.title_progress > 0;
      titleWrap.style.display = showTitle ? "" : "none";
      titleBar.value = msg.title_progress; titleLbl.textContent = `${msg.title_progress}%`;
    }
    if (typeof msg.output_locked === "boolean") {
      document.getElementById("output-path").disabled = msg.output_locked;
      document.getElementById("output-save").disabled = msg.output_locked;
      document.getElementById("output-lock-hint").style.display = msg.output_locked ? "" : "none";
    }
    if (msg.status) statusEl.textContent = msg.status;
    if (msg.step)   stepEl.textContent   = msg.step;
  }

  ws.onmessage = ({ data }) => {
    const msg = JSON.parse(data);
    if (msg.line && logBox) { logBox.textContent += msg.line + "\n"; autoScrollLog(); }
    applyProgress(msg);
  };
  ws.onclose = () => {
    const status = (document.getElementById("job-status")?.textContent || "").toLowerCase();
    if (!/finished|failed|cancelled/.test(status)) {
      const backoff = Math.min(1000 * Math.pow(2, attempt), 10000);
      setTimeout(() => openWebSocket(jobId, attempt + 1), backoff);
    }
  };
}

function autoScrollLog() {
  const logBox = document.getElementById("log-window");
  const auto   = document.getElementById("autoscroll");
  if (logBox && auto && auto.checked) logBox.scrollTop = logBox.scrollHeight;
}

/* basic theme helpers (mirrors other pages) */
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
  setCookie("theme", mode);
}
function toggleTheme() {
  const current = getCookie("theme") || "light";
  const next = current === "light" ? "dark" : "light";
  applyTheme(next);
}
