/* global showToast, toggleTheme */
document.addEventListener("DOMContentLoaded", async () => {
  const mode = getCookie("theme") ??
               (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  applyTheme(mode);

  const jobId = document.body.dataset.jobId;
  const discType = (document.body.dataset.discType || "").toLowerCase();

  // Prefill full log for scrollback
  fetch(`/jobs/${jobId}/log`)
    .then(res => res.text())
    .then(text => {
      const logBox = document.getElementById("log-window");
      if (logBox) {
        logBox.textContent = text || "";
        autoScrollLog();
      }
    })
    .catch(() => {});

  // Download link
  const downloadLink = document.getElementById("download-log");
  if (downloadLink) downloadLink.href = `/jobs/${jobId}/log`;

  // Output path UI: adaptive placeholder
  const outputInput = document.getElementById("output-path");
  if (outputInput) {
    if (["dvd_video","bluray_video","cd_audio"].includes(discType)) {
      outputInput.placeholder = "/media/Library/Movies   (folder only)";
      outputInput.title = "For video/audio discs, choose a folder (no filename).";
    } else if (["cd_rom","dvd_rom","bluray_rom"].includes(discType)) {
      outputInput.placeholder = "/media/ISOs/MyDisc.iso.zst   (final file path)";
      outputInput.title = "For ROM discs, enter the final file path (e.g., .../MyDisc.iso or .iso.zst).";
    }
  }

  // prefill output + lock state
  try {
    const r = await fetch(`/api/jobs/${jobId}/output`);
    if (r.ok) {
      const j = await r.json();
      if (outputInput) {
        outputInput.value = j.override_filename ? `${j.output_path}/${j.override_filename}` : j.output_path;
        outputInput.disabled = !!j.locked;
      }
      const btn = document.getElementById("output-save");
      const lock = document.getElementById("output-lock-hint");
      if (btn) btn.disabled = !!j.locked;
      if (lock) lock.style.display = j.locked ? "" : "none";
    }
  } catch {}

  document.getElementById("output-save")?.addEventListener("click", async () => {
    const inp = outputInput;
    if (!inp || !inp.value.trim()) return showToast("Enter a path", "error");
    const v = inp.value.trim();

    if (["dvd_video","bluray_video","cd_audio"].includes(discType)) {
      // must be a folder → reject if it looks like a file
      const leaf = v.split("/").pop() || "";
      if (/\.[a-z0-9]{2,5}$/i.test(leaf)) {
        return showToast("For video/audio discs, provide a folder (no filename).", "error");
      }
    } else if (["cd_rom","dvd_rom","bluray_rom"].includes(discType)) {
      const leaf = v.split("/").pop() || "";
      if (!/\.[a-z0-9]{2,5}$/i.test(leaf)) {
        return showToast("For ROM discs, provide the final file path (e.g., MyDisc.iso or MyDisc.iso.zst).", "error");
      }
    }

    const res = await fetch(`/api/jobs/${jobId}/output`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: v })
    });
    if (!res.ok) {
      const txt = await res.text();
      return showToast(`Failed: ${txt}`, "error");
    }
    const j = await res.json();
    if (outputInput) outputInput.value = j.override_filename ? `${j.output_path}/${j.override_filename}` : j.output_path;
    showToast("Output updated");
  });

  // OMDb search-as-you-type
  const q = document.getElementById("omdb-query");
  const pop = document.getElementById("omdb-results");
  const applyBtn = document.getElementById("omdb-apply");
  const pickedBox = document.getElementById("omdb-picked");
  const seasonInput = document.getElementById("omdb-season");
  let picked = null;
  let debounceT = null;

  function hidePop(){ if(pop) pop.style.display="none"; }
  function showPop(){ if(pop) pop.style.display=""; }

  function renderResults(items){
    if(!pop) return;
    pop.innerHTML = "";
    items.forEach(it=>{
      const li = document.createElement("li");
      li.textContent = `${it.Title} (${it.Year}) [${it.Type}]`;
      li.addEventListener("click", ()=>{
        picked = it;
        if (q) q.value = it.Title;
        const isSeries = (it.Type || "").toLowerCase() === "series";
        if (seasonInput) {
          seasonInput.disabled = !isSeries;
          seasonInput.placeholder = isSeries ? "e.g. 5" : "—";
          if (!isSeries) seasonInput.value = "";
        }
        if (pickedBox) {
          pickedBox.style.display = "";
          pickedBox.textContent = `Selected: ${it.Title} (${it.Year}) – ${it.imdbID}`;
        }
        if (applyBtn) applyBtn.disabled = false;
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
    clearTimeout(debounceT);
    debounceT = setTimeout(searchNow, 250);
  });
  q?.addEventListener("focus", ()=>{
    if ((q.value || "").trim().length >= 2) searchNow();
  });
  document.addEventListener("click", (e)=>{
    if (!pop) return;
    if (e.target !== q && !pop.contains(e.target)) hidePop();
  });

  // Apply selection → set IMDb, rewrite output path, write NFO
  document.getElementById("omdb-apply")?.addEventListener("click", async ()=>{
    if (!picked) return showToast("Pick a title first", "error");
    const isSeries = (picked?.Type || "").toLowerCase() === "series";
    const season = (isSeries && seasonInput?.value) ? parseInt(seasonInput.value, 10) : undefined;

    try{
      const url = `/api/jobs/${jobId}/imdb?imdbID=${encodeURIComponent(picked.imdbID)}${season ? `&season=${season}` : ""}`;
      const res = await fetch(url, { method: "PUT" });
      if (!res.ok) throw new Error(await res.text());
      const j = await res.json();
      // reflect new output path
      if (outputInput) outputInput.value = j.output_path;
      showToast("Metadata applied; output folder updated.");
    }catch(e){
      showToast("Could not apply metadata", "error");
    }
  });

  // Track manual edits to rename-field UI from earlier (if present)
  document.addEventListener("input", (e) => {
    if (e.target && e.target.id === "rename-path") {
      e.target.dataset.touched = "1";
    }
  });

  // finally, open the WebSocket for live updates
  openWebSocket(jobId);
});

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
      overallBar.value = msg.progress;
      if (overallLbl) overallLbl.textContent = `${msg.progress}%`;
    }
    if (typeof msg.step_progress === "number") {
      const isAudio = /cd_audio/i.test((statusEl?.textContent || "") + " " + (stepEl?.textContent || ""));
      const showStep = !isAudio || msg.step_progress > 0;
      if (stepWrap) stepWrap.style.display = showStep ? "" : "none";
      if (stepBar) stepBar.value = msg.step_progress;
      if (stepLbl) stepLbl.textContent = `${msg.step_progress}%`;
    }
    if (typeof msg.title_progress === "number") {
      const showTitle = msg.title_progress > 0;
      if (titleWrap) titleWrap.style.display = showTitle ? "" : "none";
      if (titleBar) titleBar.value = msg.title_progress;
      if (titleLbl) titleLbl.textContent = `${msg.title_progress}%`;
    }

    // reflect lock live (disables output UI)
    if (typeof msg.output_locked === "boolean") {
      const inp = document.getElementById("output-path");
      const btn = document.getElementById("output-save");
      const hint = document.getElementById("output-lock-hint");
      if (inp) inp.disabled = msg.output_locked;
      if (btn) btn.disabled = msg.output_locked;
      if (hint) hint.style.display = msg.output_locked ? "" : "none";
    }

    if (msg.status && statusEl) statusEl.textContent = msg.status;
    if (msg.step && stepEl)     stepEl.textContent   = msg.step;
  }

  ws.onmessage = ({ data }) => {
    const msg = JSON.parse(data);
    if (msg.line && logBox) {
      logBox.textContent += msg.line + "\n";
      autoScrollLog();
    }
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

// Auto-scroll toggle
function autoScrollLog() {
  const logBox = document.getElementById("log-window");
  const auto = document.getElementById("autoscroll");
  if (logBox && auto && auto.checked) {
    logBox.scrollTop = logBox.scrollHeight;
  }
}

// ------ helpers ------
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
  if (!toast) return;
  const wrapper = document.createElement("div");
  wrapper.classList.add("toast-msg");
  if (type === "error") wrapper.style.borderLeft = "5px solid red";
  wrapper.textContent = message;
  toast.appendChild(wrapper);
  setTimeout(() => wrapper.classList.add("fade-out"), 3000);
  setTimeout(() => wrapper.remove(), 4000);
}
