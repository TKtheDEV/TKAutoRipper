function safeUpdate(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value ?? "loading...";
}

function updateSystemInfo() {
  fetch("/api/system-info")
    .then(res => res.json())
    .then(data => {
      if (!data) return;

      safeUpdate('os', data.os_info.os);
      safeUpdate('os_version', data.os_info.os_version);
      safeUpdate('kernel', data.os_info.kernel);
      safeUpdate('uptime', data.os_info.uptime);

      safeUpdate('ram_total', Math.round(data.memory_info.total / 1048576) + " MB");
      safeUpdate('ram_used', Math.round(data.memory_info.used / 1048576) + " MB");
      safeUpdate('ram_usage', data.memory_info.percent + "%");

      safeUpdate('disk_total', (data.storage_info.total / 1073741824).toFixed(1) + " GB");
      safeUpdate('disk_used', (data.storage_info.used / 1073741824).toFixed(1) + " GB");
      safeUpdate('disk_usage', data.storage_info.percent + "%");

      safeUpdate('cpu_model', data.cpu_info.model);
      safeUpdate('cpu_cores_threads', `${data.cpu_info.cores}C / ${data.cpu_info.threads}T`);
      safeUpdate('cpu_clock', data.cpu_info.frequency + " MHz");
      safeUpdate('cpu_usage', data.cpu_info.usage + "%");
      safeUpdate('cpu_temp', data.cpu_info.temperature + "°C");

      const hwencoders = [
        { id: 'amd_vce', vendor: 'vce' },
        { id: 'intel_qsv', vendor: 'qsv' },
        { id: 'nvidia_nvenc', vendor: 'nvenc' },
      ];

      hwencoders.forEach(enc => {
        const vendorInfo = data.hwenc_info?.vendors?.[enc.vendor];
        const el = document.getElementById(enc.id);
        if (vendorInfo?.available) {
          el.innerHTML = "✓<br>(" + vendorInfo.codecs.join(", ") + ")";
        } else {
          el.textContent = "✗";
        }
      });

      const systemInfoRow = document.getElementById('system-info');
      systemInfoRow.querySelectorAll('.gpu-tile').forEach(tile => tile.remove());

      if (data.gpu_info.length > 0) {
        data.gpu_info.forEach(gpu => {
          const gpuTile = document.createElement('div');
          gpuTile.classList.add('tile', 'gpu-tile');
          gpuTile.innerHTML = `
            <h3>GPU Info</h3>
            <div class="entry"><strong>${gpu.model}</strong></div>
            <div class="entry"><strong>Usage:</strong> ${gpu.usage}%</div>
            <div class="entry"><strong>Temp:</strong> ${gpu.temperature}°C</div>
            <div class="entry"><strong>VRAM:</strong> ${Math.round(gpu.used_memory/1048576)}MB / ${Math.round(gpu.total_memory/1048576)}MB (${gpu.percent_memory}%)</div>
          `;
          systemInfoRow.appendChild(gpuTile);
        });
      }
    });
}

function updateDrives() {
  fetch("/api/drives")
    .then(res => res.json())
    .then((drives) => {
      const caps = { CD: { total: 0, available: 0 }, DVD: { total: 0, available: 0 }, BLURAY: { total: 0, available: 0 } };
      const capInheritance = { CD: ["CD", "DVD", "BLURAY"], DVD: ["DVD", "BLURAY"], BLURAY: ["BLURAY"] };
      const blacklistedDrives = [];

      for (const drive of drives) {
        if (drive.blacklisted) blacklistedDrives.push(drive);
        for (const level of ["CD", "DVD", "BLURAY"]) {
          if (drive.capability.some(cap => capInheritance[level].includes(cap))) {
            caps[level].total += 1;
            if (!drive.job_id && !drive.blacklisted) caps[level].available += 1;
          }
        }
      }

      const container = document.getElementById("drives");
      container.innerHTML = "";

      const overview = document.createElement("div");
      overview.className = "tile";
      overview.innerHTML = `
        <h3>Drive Overview</h3>
        <div><strong>CD:</strong> <span style="color: ${caps.CD.available > 0 ? 'green' : 'red'};">${caps.CD.available}</span> / ${caps.CD.total}</div>
        <div><strong>DVD:</strong> <span style="color: ${caps.DVD.available > 0 ? 'green' : 'red'};">${caps.DVD.available}</span> / ${caps.DVD.total}</div>
        <div><strong>BD:</strong> <span style="color: ${caps.BLURAY.available > 0 ? 'green' : 'red'};">${caps.BLURAY.available}</span> / ${caps.BLURAY.total}</div>
        ${blacklistedDrives.length > 0 ? `<div style="color: red;"><strong>Blacklisted Drives:</strong> ${blacklistedDrives.map(d => d.model).join(", ")}</div>` : ""}
        <div style="margin-top: 10px;">
          <button onclick="ejectForType('CD')" ${caps.CD.available === 0 ? "disabled" : ""}>Rip CD</button>
          <button onclick="ejectForType('DVD')" ${caps.DVD.available === 0 ? "disabled" : ""}>Rip DVD</button>
          <button onclick="ejectForType('BLURAY')" ${caps.BLURAY.available === 0 ? "disabled" : ""}>Rip BLURAY</button>
        </div>
      `;
      container.appendChild(overview);

      for (const d of drives) {
        const tile = document.createElement("div");
        tile.className = "tile";
        tile.innerHTML = `
          <h3>${d.model}</h3>
          <div><strong>Path:</strong> <code>${d.path}</code></div>
          <div><strong>Type:</strong> ${d.capability.join(", ")}</div>
          <div><strong>Status:</strong> ${d.job_id ? "Ripping" : d.blacklisted ? "Blacklisted" : "Idle"}</div>
          ${d.disc_label ? `<div><strong>Disc Label:</strong> ${d.disc_label}</div>` : ""}
          ${d.job_id ? `<div><strong>Job ID:</strong> <a href="/jobs/${d.job_id}">${d.job_id}</a></div>` : ""}
          <div style="margin-top: 10px;">
            <button onclick="ejectDrive('${d.path}', ${!!d.job_id})">Eject</button>
          </div>
        `;
        container.appendChild(tile);
      }
    });
}

function ejectDrive(path, confirmCancel = false) {
  if (confirmCancel && !confirm("Are you sure you want to eject the drive? This will cancel the job!")) return;

  fetch("/api/drives/eject", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  })
    .then(res => {
        if (!res.ok) throw new Error("Failed to eject");
        return res.json();
    })
    .then(() => {
    showToast("Drive ejected successfully.");
    updateDrives();
    updateJobs();
    })
    .catch(err => {
    console.error("Eject failed:", err);
    showToast("Eject failed!", "error");
    });
}

function ejectForType(type) {
  fetch("/api/drives")
    .then(res => res.json())
    .then(drives => {
      const capOrder = { CD: 0, DVD: 1, BLURAY: 2 };

      const matchingDrive = drives
        .filter(d => !d.job_id && !d.blacklisted && d.capability.includes(type))
        .sort((a, b) => {
          const aCap = Math.min(...a.capability.map(c => capOrder[c]));
          const bCap = Math.min(...b.capability.map(c => capOrder[c]));
          return aCap - bCap;
        })[0];

    if (!matchingDrive) {
    showToast(`No available drive can handle ${type}`, "error");
    return;
    }

      ejectDrive(matchingDrive.path, false);
    });
}

/* ── Job handling ───────────────────────────────────────── */
function cancelJob(jobId) {
  if (!confirm("Cancel this job?")) return;

  fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" })
    .then(r => { if (!r.ok) throw new Error(); })
    .then(() => {
      showToast("Job cancelled");
      updateJobs();
      updateDrives();
    })
    .catch(() => showToast("Cancel failed!", "error"));
}

function updateJobs() {
  fetch("/api/jobs")
    .then(res => res.json())
    .then(jobs => {
      const container = document.getElementById("jobs");
      container.innerHTML = "";

      if (!jobs.length) {
        container.innerHTML = `
          <div class="tile">
            <h2>No jobs running</h2>
            <small>Everything's idle.</small>
          </div>`;
        return;
      }

      const row = document.createElement("div");
      row.className = "tile-row";

      jobs.forEach(job => {
        const tile = document.createElement("div");
        tile.className = `tile job-card ${job.status.toLowerCase()}`;
        tile.innerHTML = `
          <h2>${job.disc_label}</h2>
          <strong>Status:</strong> ${job.status}<br>
          <strong>Type:</strong> ${job.disc_type}<br>
          <strong>Progress:</strong> ${job.progress}%<br>
          <strong>Drive:</strong> ${job.drive}<br>
          <a href="/jobs/${job.job_id}">🔍 View</a>
          ${["Running", "Queued"].includes(job.status)
              ? ` &nbsp;|&nbsp; <a href="#" onclick="cancelJob('${job.job_id}')" style="color:red;">⛔ Cancel</a>`
              : ""}
        `;
        row.appendChild(tile);
      });

      container.appendChild(row);
    });
}

function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : null;
}

function setCookie(name, value, days = 365) {
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/`;
}

function toggleTheme() {
  const current = getCookie('theme') || 'light';
  const next = current === 'light' ? 'dark' : 'light';
  applyTheme(next);
}

function applyTheme(mode) {
  const icon = document.getElementById('theme-icon');
  document.documentElement.classList.remove('dark-mode', 'light-mode');
  document.documentElement.classList.add(`${mode}-mode`);
  icon.textContent = mode === 'dark' ? '🌙' : '☀️';
  setCookie('theme', mode);
}

document.addEventListener('DOMContentLoaded', () => {
  let mode = getCookie('theme');
  if (!mode) {
    mode = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  applyTheme(mode);
  updateSystemInfo();
  updateDrives();
  updateJobs();
  setInterval(updateSystemInfo, 5000);
  setInterval(updateDrives, 5000);
  setInterval(updateJobs, 5000);
});
