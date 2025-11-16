// job_details.js
// Handles: theme init, prefill output path, OMDb helpers, live log (fetch + WS),
// and action buttons (Retry/Cancel/Delete).

// ————— tiny utilities —————
function $(sel){ return document.querySelector(sel); }
function text(el, v){ if (el) el.textContent = v; }
function showToast(msg, type='info'){
  const host = document.getElementById('toast');
  if (!host) return;
  const t = document.createElement('div');
  t.className = 'toast-msg';
  if (type==='error') t.style.borderLeftColor = '#e53935';
  if (type==='success') t.style.borderLeftColor = '#4caf50';
  t.textContent = msg;
  host.appendChild(t);
  setTimeout(()=>{ t.classList.add('fade-out'); setTimeout(()=>t.remove(), 400); }, 1800);
}
async function fetchJSON(url, opts){
  const r = await fetch(url, opts);
  if (!r.ok){
    const txt = await r.text().catch(()=>String(r.status));
    throw new Error(txt || `HTTP ${r.status}`);
  }
  return r.json();
}
function autoScrollLog(){
  const box = $('#log-window');
  const auto = $('#autoscroll');
  if (box && auto && auto.checked) box.scrollTop = box.scrollHeight;
}

// ————— page boot —————
document.addEventListener('DOMContentLoaded', async () => {
  const jobId    = document.body.dataset.jobId;
  const discType = (document.body.dataset.discType || '').toLowerCase();
  const discLabel= document.body.dataset.discLabel || '';
  const drive    = document.body.dataset.drivePath || '';

async function detectLinux() {
  try {
    const r = await fetch('/api/system-info');
    const j = await r.json();
    const osName = (j?.os_info?.os || '').toLowerCase();
    return osName.includes('linux');
  } catch { return false; }
}

  // Hide Output card for Linux + cd_audio
  if (discType === 'cd_audio' && await detectLinux()) {
    const wrap = document.getElementById('output-wrap');
    if (wrap) {
      // Remove the card to avoid empty space
      wrap.remove();
    }
  }

  // drive line (if any)
  if (drive) {
    const jobMeta = document.getElementById('job-meta');
    if (jobMeta) {
      const p = document.createElement('p');
      p.className = 'entry';
      p.innerHTML = `<strong>Drive:</strong> <code>${drive}</code>`;
      jobMeta.insertBefore(p, jobMeta.children[2] || null);
    }
  }

  // Prefill OMDb title with disc label (only for video discs)
  const isVideo = ['dvd_video','bluray_video'].includes(discType);
  if (isVideo) {
    const q = document.getElementById('omdb-query');
    if (q && discLabel) q.value = discLabel;
  }

  // Load initial output info and fill path
  await prefillOutput(jobId, discType);

  // Load full log text now, then keep appending via WS
  await primeLog(jobId);
  wireButtons(jobId);
  openWS(jobId);

  // OMDb helpers (search + apply)
  if (isVideo) {
    initOMDb(jobId);
  }
});

// ————— Output path prefill —————
async function prefillOutput(jobId, discType){
  const input = $('#output-path');
  const save  = $('#output-save');
  if (!input) return;

  try{
    const j = await fetchJSON(`/api/jobs/${jobId}/output`);
    // For ROM/OTHER we get a proposed full file path. If not a duplicate, lock it.
    const isRom = ['cd_rom','dvd_rom','bluray_rom','other_disc'].includes(discType);
    if (isRom && j.proposed_path){
      input.value = j.proposed_path;
      if (j.duplicate === false){
        input.disabled = true;
        if (save) save.disabled = true;
      } else if (j.duplicate === true){
        showToast('A file with this name exists. Please choose another output path.', 'error');
        input.disabled = false;
        if (save) save.disabled = false;
      }
    } else {
      // Videos / Audio / generic: use output_path directly
      input.value = j.output_path || '';
      input.disabled = !!j.locked;
      if (save) save.disabled = !!j.locked;
    }

    const hint = $('#output-lock-hint');
    if (hint) hint.style.display = j.locked ? '' : 'none';
  }catch(err){
    // Non-fatal
  }

  // Save handler
  $('#output-form')?.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const v = input.value.trim();
    if (!v) { showToast('Enter a path', 'error'); return; }

    // quick client-side validation
    if (['dvd_video','bluray_video','cd_audio'].includes(discType)){
      const leaf = v.split('/').pop() || '';
      if (/\.[a-z0-9]{2,5}$/i.test(leaf)){
        showToast('For video/audio discs, choose a folder (no filename).', 'error');
        return;
      }
    }else{
      const leaf = v.split('/').pop() || '';
      if (!/\.[a-z0-9]{2,5}$/i.test(leaf)){
        showToast('For ROM/other discs, provide the final file path (e.g., .iso or .iso.zst).', 'error');
        return;
      }
    }

    try{
      const resp = await fetchJSON(`/api/jobs/${jobId}/output`, {
        method:'PUT', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ path: v })
      });
      input.value = resp.output_path || '';
      showToast('Output updated', 'success');
    }catch(err){ showToast(`Save failed: ${err.message||err}`, 'error'); }
  });
}

// ————— Live log: prime + WS —————
async function primeLog(jobId){
  const box = $('#log-window');
  const link = $('#download-log');
  if (link) link.href = `/jobs/${jobId}/log`;
  if (!box) return;
  try{
    const txt = await fetch(`/jobs/${jobId}/log`).then(r=>r.text());
    box.textContent = txt || '';
    autoScrollLog();
  }catch{}
}

function openWS(jobId, attempt=0){
  const proto = location.protocol==='https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/jobs/${jobId}`);

  const logBox   = $('#log-window');
  const statusEl = $('#job-status');
  const stepEl   = $('#job-step');

  const overallBar = $('#overall-pct');
  const overallLbl = $('#overall-pct-label');
  const stepLbl    = $('#step-pct-label');
  const stepBar    = $('#step-pct');
  const titleLbl   = $('#title-pct-label');
  const titleBar   = $('#title-pct');

  function show(el, on){ if (el) el.style.display = on ? '' : 'none'; }

  ws.onmessage = ({data})=>{
    const msg = JSON.parse(data);

    if (msg.line && logBox){
      logBox.textContent += msg.line + '\n';
      autoScrollLog();
    }
    if (typeof msg.progress === 'number'){
      if (overallBar) overallBar.value = msg.progress;
      if (overallLbl) overallLbl.textContent = `${msg.progress}%`;
    }
    if (typeof msg.step_progress === 'number'){
      show(stepBar, true); show(stepLbl?.parentElement, true);
      if (stepBar) stepBar.value = msg.step_progress;
      if (stepLbl) stepLbl.textContent = `${msg.step_progress}%`;
    }
    if (typeof msg.title_progress === 'number'){
      const vis = msg.title_progress > 0;
      show(titleBar, vis); show(titleLbl?.parentElement, vis);
      if (titleBar) titleBar.value = msg.title_progress;
      if (titleLbl) titleLbl.textContent = `${msg.title_progress}%`;
    }
    if (typeof msg.output_locked === 'boolean'){
      const input = $('#output-path'), btn = $('#output-save'), hint = $('#output-lock-hint');
      if (input) input.disabled = msg.output_locked;
      if (btn)   btn.disabled   = msg.output_locked;
      if (hint)  hint.style.display = msg.output_locked ? '' : 'none';
    }
    if (msg.status && statusEl) text(statusEl, msg.status);
    if (msg.step && stepEl)     text(stepEl, msg.step);
    syncActions();
  };

  ws.onclose = ()=>{
    const s = ($('#job-status')?.textContent || '').toLowerCase();
    // reconnect unless terminal
    if (!/finished|failed|cancelled/.test(s)){
      const backoff = Math.min(1000*Math.pow(2,attempt), 10000);
      setTimeout(()=>openWS(jobId, attempt+1), backoff);
    }
  };
}

// ————— Buttons (Retry/Cancel/Delete) —————
function syncActions(){
  const s = ($('#job-status')?.textContent || '').toLowerCase();
  const running = /running|ripping|queued/.test(s);
  const retryBtn  = $('#retry-btn');
  const cancelBtn = $('#cancel-btn');
  const deleteBtn = $('#delete-btn');

  const jobId = document.body.dataset.jobId;
  fetchJSON(`/api/jobs/${jobId}`).then(j=>{
    const stepIndex = Number(j.step || j.step_index || 1);
    const canRetry = !running && stepIndex >= 2;
    if (retryBtn)  retryBtn.style.display  = canRetry ? '' : 'none';
    if (cancelBtn) cancelBtn.style.display = running ? '' : 'none';
    if (deleteBtn) deleteBtn.style.display = running ? 'none' : '';
  }).catch(()=>{});
}

function wireButtons(jobId){
  $('#retry-btn')?.addEventListener('click', async ()=>{
    try{ await fetchJSON(`/api/jobs/${jobId}/retry`, {method:'POST'}); showToast('Retry queued','success'); }
    catch(err){ showToast(`Retry failed: ${err.message||err}`,'error'); }
  });
  $('#cancel-btn')?.addEventListener('click', async ()=>{
    if (!confirm('Cancel this job?')) return;
    try{ await fetchJSON(`/api/jobs/${jobId}/cancel`, {method:'POST'}); showToast('Cancelled','success'); }
    catch(err){ showToast('Cancel failed','error'); }
  });
  $('#delete-btn')?.addEventListener('click', async ()=>{
    if (!confirm('Delete this job? This removes temporary files and state.')) return;
    try{ await fetchJSON(`/api/jobs/${jobId}`, {method:'DELETE'}); location.href='/'; }
    catch(err){ showToast('Delete failed','error'); }
  });
  syncActions();
}

// ————— OMDb search/apply —————
function initOMDb(jobId){
  const q     = $('#omdb-query');
  const pop   = $('#omdb-results');
  const imdb  = $('#omdb-imdbid');
  const season= $('#omdb-season');
  const apply = $('#omdb-apply');

  function hide(){ if (pop) pop.style.display='none'; }
  function show(){ if (pop) pop.style.display=''; }

  function imdbOk(v){ return /^tt\d{7,}$/.test((v||'').trim()); }
  function setSeries(on){
    if (!season) return;
    season.disabled = !on;
    season.placeholder = on ? 'e.g. 5' : '—';
    if (!on) season.value = '';
  }
  if (q) q.addEventListener('input', ()=>{
    const v = q.value.trim();
    if (v.length < 2) { hide(); return; }
    clearTimeout(q._t);
    q._t = setTimeout(async ()=>{
      try{
        const j = await fetchJSON(`/api/omdb/search?q=${encodeURIComponent(v)}`);
        pop.innerHTML = '';
        (j.results||[]).forEach(it=>{
          const li = document.createElement('li');
          li.textContent = `${it.Title} (${it.Year}) [${it.Type}]`;
          li.addEventListener('click', ()=>{
            q.value = it.Title;
            if (imdb) imdb.value = it.imdbID || '';
            setSeries((it.Type||'').toLowerCase()==='series');
            apply.disabled = !(imdb && imdbOk(imdb.value));
            hide();
          });
          pop.appendChild(li);
        });
        if ((j.results||[]).length) show(); else hide();
      }catch{ hide(); }
    }, 250);
  });

  imdb?.addEventListener('input', ()=>{
    apply.disabled = !imdbOk(imdb.value);
  });

  $('#omdb-form')?.addEventListener('submit', async (e)=>{
    e.preventDefault();
    if (!imdbOk(imdb.value)){ showToast('Enter a valid IMDb ID', 'error'); return; }
    const params = new URLSearchParams({ imdbID: imdb.value });
    if (season && !season.disabled && season.value) params.set('season', season.value);
    try{
      const j = await fetchJSON(`/api/jobs/${jobId}/imdb?${params.toString()}`, { method:'PUT' });
      showToast('Metadata applied; output updated.', 'success');
      const out = $('#output-path');
      if (out) out.value = j.output_path || out.value;
    }catch(err){ showToast('Could not apply metadata', 'error'); }
  });

  document.addEventListener('click', (e)=>{
    if (!pop) return;
    if (e.target!==q && !pop.contains(e.target)) hide();
  });
}
