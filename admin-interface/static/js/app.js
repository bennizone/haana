// app.js – Tab-Wechsel, Init, globaler State, WebSocket, SSE-Reconnect
// Globals: currentInstance, currentLogCat, currentMdInst, sse, cfg
// INSTANCES is set in index.html from Jinja2

let currentInstance = INSTANCES[0];
let currentLogCat   = 'memory-ops';
let currentMdInst   = INSTANCES[0];
let sse             = null;
let cfg             = null;

// ── Tabs ───────────────────────────────────────────────────────────────────
function showTab(name, e) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
  if (e && e.target) e.target.classList.add('active');
  else document.querySelector(`.tab-btn[onclick*="'${name}'"]`)?.classList.add('active');

  if (name === 'chat')   { loadConversations(currentInstance); }
  if (name === 'logs')   { loadLogs(currentLogCat); loadLogFiles(currentInstance); }
  if (name === 'config') { loadConfig(); loadMemoryStats(); }
  if (name === 'users')  loadUsers();
  if (name === 'status') loadStatus();
}

function showCfgTab(name) {
  document.querySelectorAll('.cfg-tab-panel').forEach(p => { p.style.display = 'none'; });
  document.querySelectorAll('.cfg-tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('cfgpanel-' + name).style.display = 'block';
  document.getElementById('cfgtab-' + name).classList.add('active');
  if (name === 'memory') loadMemoryStats();
}

// ── Instanz-Auswahl (Chat) ─────────────────────────────────────────────────
function selectInstance(inst) {
  currentInstance = inst;
  document.querySelectorAll('.inst-btn[id^="btn-"]').forEach(b => b.classList.remove('active'));
  document.getElementById('btn-' + inst)?.classList.add('active');
  startSSE(inst);
  loadConversations(inst);
  checkAgentHealth(inst);
}

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadConversations(currentInstance);
  startSSE(currentInstance);
  checkAgentHealth(currentInstance);
  loadStatus();
  loadClaudeMd(currentMdInst);
  refreshWaStatus();
});
