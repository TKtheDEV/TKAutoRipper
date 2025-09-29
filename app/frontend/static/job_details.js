import { initTheme, toggleTheme, fetchJSON, showToast } from './ui.js';
window.toggleTheme = toggleTheme;

document.addEventListener('DOMContentLoaded', async ()=>{
  initTheme();

  const jobId     = document.body.dataset.jobId;
  const discType  = (document.body.dataset.discType||'').toLowerCase();
  const discLabel = document.body.dataset.discLabel || '';
  const drivePath = document.body.dataset.drivePath || '';

  // Drive line
  if (drivePath){ document.getElementById('drive-path').textContent = drivePath; document.getElementById('drive-line').style.display=''; }

  // Prefill OMDb title
  const q = document.getElementById('omdb-query');
  if (q && discLabel) q.value = discLabel;

  // Load full log
  try{
    const text = await fetch('/jobs/'+jobId+'/log').then(r=>r.text());
    const log  = document.getElementById('log-window'); log.textContent = text || '';
    autoScroll();
  }catch{}

  const downloadLink = document.getElementById('download-log');
  if (downloadLink) downloadLink.href = `/jobs/${jobId}/log`;

  // Output prefill + ROM proposal
  const outputInput = document.getElementById('output-path');
  try{
    const j = await fetchJSON(`/api/jobs/${jobId}/output`);
    const isRom = ['cd_rom','dvd_rom','bluray_rom','other_disc'].includes(discType);

    if (isRom && j.proposed_path){
      outputInput.value = j.proposed_path;
      if (j.duplicate === false){ outputInput.disabled = true; document.getElementById('output-save').disabled = true; }
      if (j.duplicate === true){ showToast('A file with this name exists. Please choose another output path.','error'); }
    }else{
      outputInput.value = j.override_filename ? `${j.output_path}/${j.override_filename}` : j.output_path;
      outputInput.disabled = !!j.locked;
      document.getElementById('output-save').disabled = !!j.locked;
    }
    document.getElementById('output-lock-hint').style.display = j.locked ? '' : 'none';
  }catch{}

  // Save output
  document.getElementById('output-form')?.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const v = outputInput.value.trim(); if (!v) return showToast('Enter a path','error');

    if (['dvd_video','bluray_video','cd_audio'].includes(discType)){
      const leaf = v.split('/').pop()||''; if (/\.[a-z0-9]{2,5}$/i.test(leaf)) return showToast('Provide a folder (no filename).','error');
    }else if (['cd_rom','dvd_rom','bluray_rom','other_disc'].includes(discType)){
      const leaf = v.split('/').pop()||''; if (!/\.[a-z0-9]{2,5}$/i.test(leaf)) return showToast('Provide the final file path (e.g., .iso or .iso.zst).','error');
    }

    try{
      const res = await fetchJSON(`/api/jobs/${jobId}/output`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:v})});
      outputInput.value = res.override_filename ? `${res.output_path}/${res.override_filename}` : res.output_path;
      showToast('Output updated');
    }catch(err){ showToast(`Failed: ${err.message||err}`,'error'); }
  });

  // OMDb (only present for DVD/BD)
  const pop = document.getElementById('omdb-results');
  const seasonInput = document.getElementById('omdb-season');
  const imdbInput = document.getElementById('omdb-imdbid');
  const applyBtn = document.getElementById('omdb-apply');
  const pickedBox = document.getElementById('omdb-picked');
  let picked=null, t=null;

  function imdbOk(v){ return /^tt\d{7,}$/.test((v||'').trim()); }
  function hidePop(){ if (pop) pop.style.display='none'; }
  function showPop(){ if (pop) pop.style.display=''; }
  function updateApply(){ if (applyBtn) applyBtn.disabled = !(imdbOk(imdbInput?.value) || (picked&&picked.imdbID)); }

  function renderResults(items){
    if (!pop) return;
    pop.innerHTML = '';
    items.forEach(it=>{
      const li=document.createElement('li');
      li.textContent = `${it.Title} (${it.Year}) [${it.Type}]`;
      li.addEventListener('click',()=>{
        picked = it;
        if (q) q.value = it.Title;
        if (imdbInput) imdbInput.value = it.imdbID || '';
        const isSeries = (it.Type||'').toLowerCase()==='series';
        if (seasonInput){ seasonInput.disabled = !isSeries; seasonInput.placeholder = isSeries?'e.g. 5':'—'; if(!isSeries) seasonInput.value=''; }
        pickedBox.style.display='';
        pickedBox.textContent = `Selected: ${it.Title} (${it.Year}) – ${it.imdbID}`;
        updateApply(); hidePop();
      });
      pop.appendChild(li);
    }); showPop();
  }
  async function searchOMDb(){
    const v = (q?.value||'').trim();
    if (v.length<2){ hidePop(); return; }
    try{ const j = await fetchJSON(`/api/omdb/search?q=${encodeURIComponent(v)}`); renderResults(j.results||[]); }catch{}
  }
  q?.addEventListener('input',()=>{ picked=null; pickedBox.style.display='none'; clearTimeout(t); t=setTimeout(searchOMDb,250); updateApply(); });
  q?.addEventListener('focus',()=>{ if ((q.value||'').trim().length>=2) searchOMDb(); });
  document.addEventListener('click',(e)=>{ if (q && e.target!==q && !pop?.contains(e.target)) hidePop(); });
  imdbInput?.addEventListener('input', updateApply);

  document.getElementById('omdb-form')?.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const imdbID = (imdbInput?.value||'').trim(); if (!imdbOk(imdbID)) return showToast('Enter a valid IMDb ID or pick a result.','error');
    const season = seasonInput && !seasonInput.disabled && seasonInput.value ? parseInt(seasonInput.value,10) : undefined;
    try{
      const u = `/api/jobs/${jobId}/imdb?imdbID=${encodeURIComponent(imdbID)}${season?`&season=${season}`:''}`;
      const j = await fetchJSON(u,{method:'PUT'});
      if (document.getElementById('output-path')) document.getElementById('output-path').value = j.output_path;
      showToast('Metadata applied');
    }catch{ showToast('Could not apply metadata','error'); }
  });

  // Buttons
  document.getElementById('cancel-btn')?.addEventListener('click', async ()=>{
    if (!confirm('Cancel this job?')) return;
    try{ await fetchJSON(`/api/jobs/${jobId}/cancel`,{method:'POST'}); showToast('Job cancelled'); } catch{ showToast('Cancel failed','error'); }
  });
  document.getElementById('resume-btn')?.addEventListener('click', async ()=>{
    try{ await fetchJSON(`/api/jobs/${jobId}/resume`,{method:'POST'}); showToast('Job resumed'); } catch{}
  });
  document.getElementById('delete-btn')?.addEventListener('click', async ()=>{
    if (!confirm('Delete this job? If running, it will be cancelled.')) return;
    try{ await fetchJSON(`/api/jobs/${jobId}/cancel`,{method:'POST'}); location.href='/'; } catch{}
  });

  // WebSocket
  openWS(jobId);
});

function openWS(jobId, attempt=0){
  const proto = location.protocol==='https:'?'wss':'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/jobs/${jobId}`);

  const log  = document.getElementById('log-window');
  const overallBar = document.getElementById('overall-pct');
  const overallLbl = document.getElementById('overall-pct-label');
  const stepLabel  = document.getElementById('step-label');
  const stepIndex  = document.getElementById('step-index');
  const stepBar    = document.getElementById('step-pct');
  const stepPctLbl = document.getElementById('step-pct-label');
  const titleLabel = document.getElementById('title-label');
  const titleBar   = document.getElementById('title-pct');
  const titleLbl   = document.getElementById('title-pct-label');
  const statusEl   = document.getElementById('job-status');
  const stepEl     = document.getElementById('job-step');

  const show = (el,on)=>{ if (el) el.style.display = on?'':'none'; };

  function applyProgress(msg){
    if (typeof msg.progress==='number'){ overallBar.value = msg.progress; overallLbl.textContent = `${msg.progress}%`; }
    if (typeof msg.step_progress==='number'){ show(stepLabel,true); show(stepBar,true); stepBar.value = msg.step_progress; stepPctLbl.textContent = `${msg.step_progress}%`; }
    if (typeof msg.title_progress==='number'){ const on=msg.title_progress>0; show(titleLabel,on); show(titleBar,on); titleBar.value = msg.title_progress; titleLbl.textContent = `${msg.title_progress}%`; }
    if (typeof msg.step_index==='number' && typeof msg.step_total==='number'){ stepIndex.textContent = `(${msg.step_index}/${msg.step_total})`; }
    if (typeof msg.output_locked==='boolean'){
      const inp=document.getElementById('output-path'), btn=document.getElementById('output-save'), hint=document.getElementById('output-lock-hint');
      if (inp)  inp.disabled = msg.output_locked; if (btn) btn.disabled = msg.output_locked; if (hint) hint.style.display = msg.output_locked?'':'none';
    }
    if (msg.status && statusEl){ statusEl.textContent = msg.status; }
    if (msg.step && stepEl){ stepEl.textContent = msg.step; }
  }

  ws.onmessage = ({data})=>{
    const msg = JSON.parse(data);
    if (msg.line && log){ log.textContent += msg.line + '\n'; autoScroll(); }
    applyProgress(msg);
  };
  ws.onclose = ()=>{
    const status = (document.getElementById('job-status')?.textContent||'').toLowerCase();
    if (!/finished|failed|cancelled/.test(status)){
      const backoff = Math.min(1000*Math.pow(2,attempt), 10000);
      setTimeout(()=>openWS(jobId, attempt+1), backoff);
    }
  };
}

function autoScroll(){
  const log = document.getElementById('log-window');
  const auto = document.getElementById('autoscroll');
  if (log && auto && auto.checked) log.scrollTop = log.scrollHeight;
}
