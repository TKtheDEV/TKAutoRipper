import { fetchJSON, showToast, on } from './ui.js';

// ====== System Info ======
function bytesToHuman(n) {
  if (n == null) return 'n/a';
  const units = ['B','KB','MB','GB','TB','PB'];
  let i = 0, v = Number(n);
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2)} ${units[i]}`;
}
function pct(x, digits = 1) {
  if (x == null || isNaN(x)) return 'n/a';
  return `${Number(x).toFixed(digits)}%`;
}
async function fetchSystemInfo() {
  // try the new path first, fall back to old one
  const try1 = await fetch('/api/system-info').catch(() => null);
  if (try1 && try1.ok) return try1.json();
  const try2 = await fetch('/api/systeminfo').catch(() => null);
  if (try2 && try2.ok) return try2.json();
  throw new Error('system info unavailable');
}
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val ?? 'n/a';
}
function setHTML(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html ?? 'n/a';
}
function renderHWEnc(vendorObj) {
  if (!vendorObj || typeof vendorObj !== 'object') return 'n/a';
  const ok = !!vendorObj.available;
  const list = Array.isArray(vendorObj.codecs) && vendorObj.codecs.length
    ? ` (${vendorObj.codecs.join(', ')})` : '';
  return ok ? `✓${list}` : '✗';
}
function updateSystemInfo() {
  fetchSystemInfo().then(data => {
    // ---- OS ----
    const os = data.os_info || {};
    setText('os',          os.os || 'n/a');
    setText('os_version',  os.os_version || 'n/a');
    setText('kernel',      os.kernel || 'n/a');
    setText('uptime',      os.uptime || 'n/a');

    // ---- RAM ----
    const mem = data.memory_info || data.ram_info || {};
    const memUsed = mem.used ?? (mem.total != null && mem.available != null ? (mem.total - mem.available) : null);
    setText('ram_total', bytesToHuman(mem.total));
    setText('ram_used',  bytesToHuman(memUsed));
    setText('ram_usage', pct(mem.percent));

    // ---- Storage ----
    const st = data.storage_info || {};
    setText('disk_total', bytesToHuman(st.total));
    setText('disk_used',  bytesToHuman(st.used));
    setText('disk_usage', pct(st.percent));

    // ---- CPU ----
    const cpu = data.cpu_info || {};
    setText('cpu_model', cpu.model || 'n/a');
    setText('cpu_cores_threads', (cpu.cores != null && cpu.threads != null) ? `${cpu.cores} / ${cpu.threads}` : 'n/a');
    setText('cpu_clock', cpu.frequency != null ? `${cpu.frequency} MHz` : 'n/a');
    setText('cpu_usage', pct(cpu.usage));
    setText('cpu_temp',  cpu.temperature != null ? `${cpu.temperature}°C` : 'n/a');

    // ---- HW Encoders ----
    const vendors = (data.hwenc_info && data.hwenc_info.vendors) || {};
    setHTML('amd_vce',     renderHWEnc(vendors.vce));
    setHTML('intel_qsv',   renderHWEnc(vendors.qsv));
    setHTML('nvidia_nvenc',renderHWEnc(vendors.nvenc));

    // ---- GPUs ----
    const row = document.getElementById('system-info');
    // remove old gpu tiles
    Array.from(row.querySelectorAll('.gpu-tile')).forEach(t => t.remove());
    (data.gpu_info || []).forEach(gpu => {
      const div = document.createElement('div');
      div.className = 'card gpu-tile';
      div.innerHTML = `
        <h3>GPU Info</h3>
        <div class="entry"><strong>${gpu.model || 'GPU'}</strong></div>
        <div class="entry"><strong>Usage:</strong> ${pct(gpu.usage, 0)}</div>
        <div class="entry"><strong>Temp:</strong> ${gpu.temperature != null ? gpu.temperature + '°C' : 'n/a'}</div>
        <div class="entry"><strong>VRAM:</strong> ${bytesToHuman(gpu.used_memory)} / ${bytesToHuman(gpu.total_memory)} (${pct(gpu.percent_memory)})</div>`;
      row.appendChild(div);
    });
  }).catch(() => {
    // leave "loading…" text if fetch failed
  });
}

// ====== Drives ======
async function updateDrives(){
  const drives = await fetchJSON('/api/drives');
  const caps = { CD:{total:0,available:0}, DVD:{total:0,available:0}, BLURAY:{total:0,available:0} };
  const inh  = { CD:['CD','DVD','BLURAY'], DVD:['DVD','BLURAY'], BLURAY:['BLURAY'] };
  const blacklisted = [];

  for (const d of drives){
    if (d.blacklisted) blacklisted.push(d);
    for (const lvl of ['CD','DVD','BLURAY']){
      if (d.capability.some(c => inh[lvl].includes(c))){
        caps[lvl].total += 1;
        if (!d.job_id && !d.blacklisted) caps[lvl].available += 1;
      }
    }
  }

  const container = document.getElementById('drives');
  container.innerHTML = '';

  const overview = document.createElement('div');
  overview.className = 'card';
  overview.innerHTML = `
    <h3>Drive Overview</h3>
    <div><strong>CD:</strong> <span style="color:${caps.CD.available>0?'var(--green)':'var(--red)'}">${caps.CD.available}</span> / ${caps.CD.total}</div>
    <div><strong>DVD:</strong> <span style="color:${caps.DVD.available>0?'var(--green)':'var(--red)'}">${caps.DVD.available}</span> / ${caps.DVD.total}</div>
    <div><strong>BD:</strong> <span style="color:${caps.BLURAY.available>0?'var(--green)':'var(--red)'}">${caps.BLURAY.available}</span> / ${caps.BLURAY.total}</div>
    ${blacklisted.length?`<div style="color: var(--red)"><strong>Blacklisted:</strong> ${blacklisted.map(d=>d.model).join(', ')}</div>`:''}
    <div class="btn-row" style="margin-top:.6rem">
      <button class="btn btn--primary" data-riptype="CD" ${caps.CD.available===0?'disabled':''}>Rip CD</button>
      <button class="btn btn--primary" data-riptype="DVD" ${caps.DVD.available===0?'disabled':''}>Rip DVD</button>
      <button class="btn btn--primary" data-riptype="BLURAY" ${caps.BLURAY.available===0?'disabled':''}>Rip BLURAY</button>
    </div>`;
  container.appendChild(overview);

  for (const d of drives){
    const div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `
      <h3>${d.model}</h3>
      <div><strong>Path:</strong> <code>${d.path}</code></div>
      <div><strong>Type:</strong> ${d.capability.join(', ')}</div>
      <div><strong>Status:</strong> ${d.job_id?'Ripping':(d.blacklisted?'Blacklisted':'Idle')}</div>
      ${d.disc_label?`<div><strong>Disc Label:</strong> ${d.disc_label}</div>`:''}
      ${d.job_id?`<div><strong>Job ID:</strong> <a href="/jobs/${d.job_id}">${d.job_id}</a></div>`:''}
      <div class="btn-row" style="margin-top:.6rem">
        <button class="btn btn--danger eject-btn" data-path="${encodeURIComponent(d.path)}" data-hasjob="${!!d.job_id}">Eject</button>
      </div>`;
    container.appendChild(div);
  }
}

async function ejectDrive(path, confirmCancel=false){
  if (confirmCancel && !confirm('Ejecting will cancel the job. Continue?')) return;
  try{
    await fetchJSON('/api/drives/eject',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path})});
    showToast('Drive ejected');
    updateDrives(); updateJobs();
  }catch(err){ showToast(`Eject failed: ${err.message||err}`,'error'); }
}
function ejectForType(type){
  fetchJSON('/api/drives').then(drives=>{
    const order={CD:0,DVD:1,BLURAY:2};
    const match = drives
      .filter(d=>!d.job_id && !d.blacklisted && d.capability.includes(type))
      .sort((a,b)=> Math.min(...a.capability.map(c=>order[c])) - Math.min(...b.capability.map(c=>order[c])) )[0];
    if(!match) return showToast(`No available drive for ${type}`,'error');
    ejectDrive(match.path,false);
  });
}

// Event delegation
on(document,'button.eject-btn','click',(e,btn)=>{
  const path = decodeURIComponent(btn.dataset.path); const hasJob = btn.dataset.hasjob==='true';
  ejectDrive(path, hasJob);
});
on(document,'button[data-riptype]','click',(e,btn)=> ejectForType(btn.dataset.riptype));

// ====== Jobs ======
function badge(status){
  const s=(status||'').toLowerCase();
  if (s==='finished') return '<span class="badge badge--finished">Finished</span>';
  if (s==='failed'||s==='cancelled') return '<span class="badge badge--failed">Failed</span>';
  if (s==='running'||s==='ripping') return '<span class="badge badge--running">Running</span>';
  return '<span class="badge badge--queued">Queued</span>';
}
async function updateJobs(){
  const jobs = await fetchJSON('/api/jobs');
  const container = document.getElementById('jobs');
  container.innerHTML = '';
  if (!jobs.length){
    container.innerHTML = `<div class="card"><h2>No jobs running</h2><small>Everything's idle.</small></div>`;
    return;
  }

  const row = document.createElement('div');
  row.className = 'grid grid--auto';

  const badge = (status)=>{
    const s=(status||'').toLowerCase();
    if (s==='finished') return '<span class="badge badge--finished">Finished</span>';
    if (s==='failed'||s==='cancelled') return '<span class="badge badge--failed">Failed</span>';
    if (s==='running'||s==='ripping') return '<span class="badge badge--running">Running</span>';
    return '<span class="badge badge--queued">Queued</span>';
  };

  jobs.forEach(job=>{
    // progress fallback
    const prog = typeof job.progress === 'number' ? job.progress : 0;

    // drive, allowing for various key names
    const drive =
      job.drive_path || job.drive || job.driveDevice || job.drive_path_raw || '';

    // decide which controls make sense
    const s = (job.status || '').toLowerCase();
    const canCancel = /running|ripping|queued/.test(s);
    const canResume = /paused/.test(s); // adjust if your backend uses different word
    // we still show Delete for everything; it will cancel if needed then remove

    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <h3>${job.disc_label || 'unknown'}</h3>
      <div><strong>Status:</strong> ${badge(job.status)}</div>
      <div><strong>Type:</strong> ${job.disc_type || 'n/a'}</div>
      ${drive ? `<div><strong>Drive:</strong> <code>${drive}</code></div>` : ''}
      <div class="progress-label"><strong>Total</strong> <span>${prog}%</span></div>
      <progress class="progress" max="100" value="${prog}"></progress>
      <div class="btn-row" style="margin-top:.5rem">
        <a class="btn btn--ghost" href="/jobs/${job.job_id}">🔍 View</a>
        <button class="btn btn--primary" data-resume="${job.job_id}" ${canResume?'':'disabled'}>▶️ Resume</button>
        <button class="btn btn--danger"  data-cancel="${job.job_id}" ${canCancel?'':'disabled'}>⛔ Cancel</button>
        <button class="btn btn--danger"  data-delete="${job.job_id}">🗑 Delete</button>
      </div>`;
    row.appendChild(card);
  });

  container.appendChild(row);
}

// ====== Boot ======
document.addEventListener('DOMContentLoaded', ()=>{
  updateSystemInfo(); updateDrives(); updateJobs();
  setInterval(updateSystemInfo, 5000);
  setInterval(updateDrives, 4000);
  setInterval(updateJobs,   5000);
});
