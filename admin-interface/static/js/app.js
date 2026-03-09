// app.js – Tab-Wechsel, Init, globaler State, SSE-Reconnect (v8)
// Globals: currentInstance, currentViewMode, sse, cfg
// INSTANCES is set in index.html from Jinja2

let currentInstance = '__all__';     // unified instance (chat + logs)
let currentViewMode = 'live';        // 'live' | 'archiv'
let currentLogCat   = 'memory-ops';  // kept for legacy compat
let sse             = null;
let cfg             = null;

// ── Tabs ───────────────────────────────────────────────────────────────────
function showTab(name, e) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
  if (e && e.target) e.target.classList.add('active');
  else document.querySelector(`.tab-btn[onclick*="'${name}'"]`)?.classList.add('active');

  if (name === 'conversations') { initConversationsView(); }
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
  if (name === 'whatsapp') refreshWaStatus();
}

// ── Unified Instance Selection ─────────────────────────────────────────────
function selectInstance(inst) {
  currentInstance = inst;

  // Update unified tab buttons
  document.querySelectorAll('.conv-inst-tab').forEach(b => {
    b.classList.toggle('active', b.dataset.inst === inst);
  });

  _updateConvUI();
}

// ── View Mode Toggle ───────────────────────────────────────────────────────
function switchViewMode(mode) {
  currentViewMode = mode;
  document.querySelectorAll('.view-toggle-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === mode);
  });
  _updateConvUI();
}

// ── Conversations View Init ────────────────────────────────────────────────
function initConversationsView() {
  // Sync instance tabs
  document.querySelectorAll('.conv-inst-tab').forEach(b => {
    b.classList.toggle('active', b.dataset.inst === currentInstance);
  });
  // Sync view mode buttons
  document.querySelectorAll('.view-toggle-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === currentViewMode);
  });
  _updateConvUI();
}

// ── Internal: update panel based on current state ─────────────────────────
function _updateConvUI() {
  const isAll  = currentInstance === '__all__';
  const isLive = currentViewMode === 'live';

  // Chat input: hidden for "Alle" or Archiv mode
  const chatBox = document.querySelector('#panel-conversations .chat-box');
  if (chatBox) {
    chatBox.style.display = (isAll) ? 'none' : '';
  }

  // Show "select instance" hint when "Alle" is active in live mode
  const selectHint = document.getElementById('conv-select-hint');
  if (selectHint) {
    selectHint.style.display = (isAll && isLive) ? '' : 'none';
  }

  // Limit selector: only in live mode
  const limitSel = document.querySelector('.conv-limit-wrap');
  if (limitSel) limitSel.style.display = isLive ? '' : 'none';

  // Live status bar: only in live mode
  const liveBar = document.querySelector('#panel-conversations .live-bar');
  if (liveBar) liveBar.style.display = isLive ? '' : 'none';

  // Archiv toolbar + filter: only in archiv mode, and only for specific instance
  const archivToolbar = document.getElementById('conv-archiv-toolbar');
  if (archivToolbar) {
    archivToolbar.style.display = isLive ? 'none' : '';
    // Export/Delete buttons: only for specific instance
    const actions = document.getElementById('log-toolbar-actions');
    if (actions) {
      actions.style.display = (!isAll) ? 'flex' : 'none';
    }
  }

  // Content areas
  const liveContent   = document.getElementById('conv-list');
  const archivContent = document.getElementById('log-day-list');
  if (liveContent)   liveContent.style.display   = isLive ? '' : 'none';
  if (archivContent) archivContent.style.display = isLive ? 'none' : '';

  // Load data
  if (isLive) {
    // Close SSE if switching away from a specific instance
    if (isAll) {
      if (sse) { sse.close(); sse = null; }
      const dot   = document.getElementById('live-dot');
      const label = document.getElementById('live-label');
      if (dot)   dot.classList.add('offline');
      if (label) label.textContent = t('chat.sse_offline');
      if (liveContent) liveContent.innerHTML =
        `<div class="empty-state"><div class="icon">&#8594;</div><div>${t('chat.select_instance')}</div></div>`;
    } else {
      loadConversations(currentInstance);
      startSSE(currentInstance);
      checkAgentHealth(currentInstance);
    }
  } else {
    // Archiv mode: use logs functions with unified instance
    _logCurrentInst = currentInstance;
    // Reset check-result banner
    const banner = document.getElementById('log-check-result');
    if (banner) { banner.style.display = 'none'; banner.innerHTML = ''; }
    loadLogDays();
  }
}

// ── Rebuild banner shortcut ────────────────────────────────────────────────
function scrollToRebuild() {
  showCfgTab('memory');
  setTimeout(() => {
    document.getElementById('rebuild-section')?.scrollIntoView({ behavior: 'smooth' });
  }, 100);
}

// ── HA Ingress Detection ────────────────────────────────────────────────────
(function() {
  const isHaIngress = window.location.pathname.includes('/api/hassio_ingress/')
    || window.parent !== window;
  if (isHaIngress) {
    document.documentElement.classList.add('ha-theme');
    // Try to read HA theme (light/dark) from parent frame
    try {
      const haTheme = window.parent?.document?.documentElement?.getAttribute('data-theme');
      if (haTheme === 'light') document.documentElement.classList.add('ha-theme-light');
    } catch(_) { /* cross-origin, ignore */ }
  }
})();

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Auto-detect browser language as default if no preference stored
  const storedLang  = localStorage.getItem('haana_lang');
  const browserLang = navigator.language?.startsWith('de') ? 'de' : 'en';
  const initLang    = storedLang || browserLang;

  I18n.load(initLang).then(() => {
    const sel = document.getElementById('lang-selector');
    if (sel) sel.value = I18n.getLang();

    // Check if setup is needed
    fetch('/api/setup-status')
      .then(r => r.ok ? r.json() : { needs_setup: false })
      .then(d => {
        if (d && d.needs_setup) {
          // Hide normal UI
          document.querySelector('header').style.display = 'none';
          document.querySelector('.tabs').style.display = 'none';
          document.querySelectorAll('.panel').forEach(p => p.style.display = 'none');
          // Show wizard
          wizardInit();
        } else {
          _appInit();
        }
      })
      .catch(() => _appInit());
  });
});

function _appInit() {
  // Default: first instance, live mode
  currentInstance = INSTANCES.length > 0 ? INSTANCES[0] : '__all__';
  currentViewMode = 'live';

  initConversationsView();
  loadStatus();
  refreshWaStatus();
}
