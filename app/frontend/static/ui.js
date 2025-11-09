//ui.js
// Theme + toasts + fetch util — shared across pages

export function getCookie(name){
  const m = document.cookie.match(new RegExp('(^| )'+name+'=([^;]+)'));
  return m ? decodeURIComponent(m[2]) : null;
}
export function setCookie(name,val,days=365){
  const e = new Date(Date.now()+days*864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(val)}; expires=${e}; path=/`;
}
export function applyTheme(mode){
  const icon = document.getElementById('theme-icon');
  document.documentElement.classList.remove('dark-mode','light-mode');
  document.documentElement.classList.add(`${mode}-mode`);
  if (icon) icon.textContent = mode==='dark' ? '🌙' : '☀️';
  setCookie('theme', mode);
}
export function initTheme(){
  let mode = getCookie('theme');
  if (!mode) mode = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  applyTheme(mode);
}
export function toggleTheme(){
  const current = getCookie('theme') || 'light';
  const next = current === 'light' ? 'dark' : 'light';
  applyTheme(next);
}


export function showToast(message, type = "success") {
  const toast = document.getElementById("toast");
  const wrapper = document.createElement("div");
  wrapper.classList.add("toast-msg");
  if (type === "error") wrapper.style.borderLeft = "5px solid red";
  wrapper.textContent = message;
  toast.appendChild(wrapper);
  
  setTimeout(() => wrapper.classList.add("fade-out"), 3000);
  setTimeout(() => wrapper.remove(), 4000);
}


// Toasts
/*export function showToast(message, type='success'){
  const toast = document.getElementById('toast');
  if (!toast) return;
  const el = document.createElement('div');
  el.className = `toast-msg ${type==='error'?'error':'success'}`;
  el.textContent = message;
  toast.appendChild(el);
  setTimeout(()=>el.classList.add('fade-out'), 3000);
  setTimeout(()=>el.remove(), 4000);
}*/

// Fetch JSON helper
export async function fetchJSON(url, options={}){
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(await res.text().catch(()=>res.statusText));
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) return res.json();
  return res.text();
}

// Simple event delegation helper
export function on(root, selector, event, handler){
  root.addEventListener(event, (e)=>{
    const target = e.target.closest(selector);
    if (target && root.contains(target)) handler(e, target);
  });
}
