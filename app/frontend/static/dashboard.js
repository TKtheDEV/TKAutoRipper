//dashboard.js
import { fetchJSON, showToast, on } from './ui.js';

// ====== System Info ======
function bytesToHuman(n) {
  if (n == null) return 'n/a';
  const units = ['B','KB','MB','GB','TB'];
  let i=0, v=Number(n);
  while (v>=1024 && i<units.length-1){ v/=1024; i++; }
  return `${v.toFixed(v>=100?0:v>=10?1:2)} ${units[i]}`;
}

function pct(x, d=1){ return (x==null || isNaN(x)) ? 'n/a' : `${Number(x).toFixed(d)}%`; }
async function fetchSystemInfo() {
  const res = await fetch('/api/system-info');
  if (!res.ok) throw new Error('system info unavailable');
  return res.json();
}

function setText(id, val){ const el=document.getElementById(id); if(el) el.textContent = val ?? 'n/a'; }
function setHTML(id, html){ const el=document.getElementById(id); if(el) el.innerHTML = html ?? 'n/a'; }
function renderHWEnc(v){ if(!v||typeof v!=='object') return 'n/a'; return v.available ? `✓${(v.codecs?.length?` (${v.codecs.join(', ')})`:'')}` : '✗'; }

function updateSystemInfo(){
  fetchSystemInfo().then(data=>{
    const os = data.os_info || {};
    setText('os', os.os || 'n/a');
    setText('os_version', os.os_version || 'n/a');
    setText('kernel', os.kernel || 'n/a');
    setText('uptime', os.uptime || 'n/a');

    const mem = data.memory_info || data.ram_info || {};
    const memUsed = mem.used ?? (mem.total!=null && mem.available!=null ? (mem.total-mem.available) : null);
    setText('ram_total', bytesToHuman(mem.total));
    setText('ram_used', bytesToHuman(memUsed));
    setText('ram_usage', pct(mem.percent));

    const st = data.storage_info || {};
    setText('disk_total', bytesToHuman(st.total));
    setText('disk_used', bytesToHuman(st.used));
    setText('disk_usage', pct(st.percent));

    const cpu = data.cpu_info || {};
    setText('cpu_model', cpu.model || 'n/a');
    setText('cpu_cores_threads', (cpu.cores!=null && cpu.threads!=null) ? `${cpu.cores} / ${cpu.threads}` : 'n/a');
    setText('cpu_clock', cpu.frequency!=null ? `${cpu.frequency} MHz` : 'n/a');
    setText('cpu_usage', pct(cpu.usage));
    setText('cpu_temp', cpu.temperature!=null ? `${cpu.temperature}°C` : 'n/a');

    const vendors = data.hwenc_info?.vendors || {};
    setHTML('amd_vce', renderHWEnc(vendors.vce));
    setHTML('apple_vt', renderHWEnc(vendors.vt));
    setHTML('intel_qsv', renderHWEnc(vendors.qsv));
    setHTML('nvidia_nvenc', renderHWEnc(vendors.nvenc));

    const row = document.getElementById('system-info');
    Array.from(row.querySelectorAll('.gpu-tile')).forEach(t=>t.remove());
    (data.gpu_info||[]).forEach(gpu=>{
      const div = document.createElement('div');
      div.className = 'card gpu-tile';
      div.innerHTML = `
        <h3>GPU Info</h3>
        <div class="entry"><strong>${gpu.model||'GPU'}</strong></div>
        <div class="entry"><strong>Usage:</strong> ${pct(gpu.usage,0)}</div>
        <div class="entry"><strong>Temp:</strong> ${gpu.temperature!=null?gpu.temperature+'°C':'n/a'}</div>
        <div class="entry"><strong>VRAM:</strong> ${bytesToHuman(gpu.used_memory)} / ${bytesToHuman(gpu.total_memory)} (${pct(gpu.percent_memory)})</div>`;
      row.appendChild(div);
    });
  }).catch(()=>{});
}

// ====== Drives ======
async function updateDrives(){
  const drives = await fetchJSON('/api/drives');
  const container = document.getElementById('drives');
  container.classList.add('drives-grid');
  container.innerHTML = '';

  // --- Drive overview (counts + quick-eject buttons) ---
  const caps = { CD: { total: 0, available: 0 }, DVD: { total: 0, available: 0 }, BLURAY: { total: 0, available: 0 } };
  const capInheritance = { CD: ['CD', 'DVD', 'BLURAY'], DVD: ['DVD', 'BLURAY'], BLURAY: ['BLURAY'] };
  const blacklisted = [];

  for (const drive of drives) {
    if (drive.blacklisted) blacklisted.push(drive);
    for (const level of ['CD', 'DVD', 'BLURAY']) {
      if (drive.capability.some(cap => capInheritance[level].includes(cap))) {
        caps[level].total += 1;
        if (!drive.job_id && !drive.blacklisted) caps[level].available += 1;
      }
    }
  }

  const overview = document.createElement('div');
  overview.className = 'card card--drive-overview';
  overview.innerHTML = `
    <h3>Drive Overview</h3>
    <div class="counts">
      <div class="count-row"><span>CD</span><strong class="${caps.CD.available ? 'ok' : 'bad'}">${caps.CD.available}</strong><span>/ ${caps.CD.total}</span></div>
      <div class="count-row"><span>DVD</span><strong class="${caps.DVD.available ? 'ok' : 'bad'}">${caps.DVD.available}</strong><span>/ ${caps.DVD.total}</span></div>
      <div class="count-row"><span>BD</span><strong class="${caps.BLURAY.available ? 'ok' : 'bad'}">${caps.BLURAY.available}</strong><span>/ ${caps.BLURAY.total}</span></div>
    </div>
    ${blacklisted.length ? `<div class="muted">Blacklisted: ${blacklisted.map(d => d.model).join(', ')}</div>` : ''}
    <div class="btn-col">
      <button class="btn btn--ghost" data-eject-type="CD" ${caps.CD.available === 0 ? 'disabled' : ''}>Rip CD</button>
      <button class="btn btn--ghost" data-eject-type="DVD" ${caps.DVD.available === 0 ? 'disabled' : ''}>Rip DVD</button>
      <button class="btn btn--ghost" data-eject-type="BLURAY" ${caps.BLURAY.available === 0 ? 'disabled' : ''}>Rip BD</button>
    </div>
  `;
  container.appendChild(overview);

  for (const d of drives){
    const div = document.createElement('div');
    div.className = 'card card--drive';
    div.innerHTML = `
      <h3>${d.model}</h3>
      <div><strong>Path:</strong> <code>${d.path}</code></div>
      <div><strong>Type:</strong> ${d.capability.join(', ')}</div>
      <div><strong>Status:</strong> ${d.job_id ? 'Ripping' : (d.blacklisted ? 'Blacklisted' : 'Idle')}</div>
      ${d.disc_label ? `<div><strong>Disc Label:</strong> ${d.disc_label}</div>` : ''}
      ${d.job_id ? `<div><strong>Job ID:</strong> <a href="/jobs/${d.job_id}">${d.job_id}</a></div>` : ''}

      <!-- pinned to bottom-left -->
      <div class="btn-row eject-row">
        <button class="btn btn--danger eject-btn"
                data-path="${encodeURIComponent(d.path)}"
                data-hasjob="${d.job_id ? 'true' : 'false'}">Eject</button>
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
on(document,'button.eject-btn','click',(e,btn)=>{
  const path = decodeURIComponent(btn.dataset.path); const hasJob = btn.dataset.hasjob==='true';
  ejectDrive(path, hasJob);
});

async function ejectForType(type){
  try{
    const drives = await fetchJSON('/api/drives');
    const capOrder = { CD: 0, DVD: 1, BLURAY: 2 };
    const capInheritance = { CD: ['CD', 'DVD', 'BLURAY'], DVD: ['DVD', 'BLURAY'], BLURAY: ['BLURAY'] };
    const match = drives
      .filter(d => !d.job_id && !d.blacklisted && d.capability.some(c => capInheritance[type].includes(c)))
      .sort((a, b) => {
        const aCap = Math.min(...a.capability.map(c => capOrder[c] ?? 99));
        const bCap = Math.min(...b.capability.map(c => capOrder[c] ?? 99));
        return aCap - bCap;
      })[0];
    if (!match){
      showToast(`No available drive can handle ${type}`, 'error');
      return;
    }
    await ejectDrive(match.path, false);
  }catch(err){
    showToast(`No available drive can handle ${type}`, 'error');
  }
}
on(document, 'button[data-eject-type]', 'click', (_e, btn)=> {
  const type = btn.dataset.ejectType;
  if (type) ejectForType(type);
});

// ====== Jobs (Cancel/Delete in the same spot; Retry when step >= 2) ======
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
    if (s==='running'||s==='ripping'||s==='queued') return '<span class="badge badge--running">Running</span>';
    return '<span class="badge badge--queued">Queued</span>';
  };

  jobs.forEach(job=>{
    const s = (job.status || '').toLowerCase();
    const running = /running|ripping|queued/.test(s);
    const prog = Number.isFinite(job.progress) ? job.progress : 0;
    const drive = job.drive_path || job.drive || job.driveDevice || job.drive_path_raw || '';
    const showRetry = !running && Number(job.step) >= 2;

    const primaryAttr = running ? 'data-cancel' : 'data-delete';
    const primaryText = running ? '⛔ Cancel' : '🗑 Delete';

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
        ${showRetry ? `<button class="btn btn--primary" data-retry="${job.job_id}">↻ Retry</button>` : ''}
        <button class="btn btn--danger" ${primaryAttr}="${job.job_id}">${primaryText}</button>
      </div>`;
    row.appendChild(card);
  });

  container.appendChild(row);
}

// Actions
on(document,'button[data-retry]','click', async (_e,btn)=>{
  const id = btn.dataset.retry;
  try{
    await fetchJSON(`/api/jobs/${id}/retry`, { method:'POST' });
    showToast('Retry queued');
    updateJobs();
  }catch(err){ showToast(`Retry failed: ${err.message||err}`, 'error'); }
});

on(document,'button[data-cancel]','click', async (_e,btn)=>{
  const id = btn.dataset.cancel;
  if (!confirm('Cancel this job?')) return;
  try{
    await fetchJSON(`/api/jobs/${id}/cancel`, { method:'POST' });
    showToast('Job cancelled');
    updateJobs();
  }catch(err){ showToast('Cancel failed', 'error'); }
});

on(document,'button[data-delete]','click', async (_e,btn)=>{
  const id = btn.dataset.delete;
  if (!confirm('Delete this job? This removes temporary files and state.')) return;
  try{
    await fetchJSON(`/api/jobs/${id}`, { method:'DELETE' });
    showToast('Job deleted');
    updateJobs();
  }catch(err){ showToast(`Delete failed: ${err.message||err}`, 'error'); }
});

// Boot
document.addEventListener('DOMContentLoaded', ()=>{
  updateSystemInfo(); updateDrives(); updateJobs();
  setInterval(updateSystemInfo, 5000);
  setInterval(updateDrives, 4000);
  setInterval(updateJobs,   5000);
});
