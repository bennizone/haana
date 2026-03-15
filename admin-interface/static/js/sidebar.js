// sidebar.js – Sidebar Navigation, Dashboard, Status Dots (Phase 1 Redesign)
// Requires: app.js (showCfgTab, loadConfig, loadMemoryStats, loadGitStatus,
//           loadUsers, loadStatus, loadSkillsTab, initConversationsView,
//           loadDevProvider), utils.js (escHtml, escAttr, t)

// Page → { panel, cfgTab } Mapping
const _PAGE_MAP = {
  'dashboard':    { panel: 'dashboard' },
  'agents':       { panel: 'status' },
  'memory':       { panel: 'config', cfgTab: 'memory' },
  'providers':    { panel: 'config', cfgTab: 'providers' },
  'ha':           { panel: 'config', cfgTab: 'providers' },
  'ch-whatsapp':  { panel: 'ch-whatsapp',  channelId: 'whatsapp' },
  'ch-ha_voice':  { panel: 'ch-ha_voice',  channelId: 'ha_voice' },
  'ch-telegram':  { panel: 'ch-telegram',  channelId: 'telegram' },
  'sk-kalender':  { panel: 'sk-kalender',  channelId: 'kalender' },
  'users':        { panel: 'users' },
  'conversations':{ panel: 'conversations' },
  'logs':         { panel: 'conversations' },
  'settings':     { panel: 'terminal' },
};

let _currentPage = 'dashboard';

function navigateTo(page) {
  _currentPage = page;

  // Update active state in sidebar
  document.querySelectorAll('.sidebar-item, .sidebar-subitem').forEach(function(el) {
    el.classList.remove('active');
  });
  var navEl = document.getElementById('nav-' + page);
  if (navEl) navEl.classList.add('active');

  // Update URL hash
  history.replaceState(null, '', '#' + page);

  // Hide all panels
  document.querySelectorAll('.panel').forEach(function(p) { p.classList.remove('active'); });

  var map = _PAGE_MAP[page];
  if (!map) return;

  // Show target panel
  var panel = document.getElementById('panel-' + map.panel);
  if (panel) panel.classList.add('active');

  // Load panel data
  if (map.panel === 'dashboard')     loadDashboard();
  if (map.panel === 'config')        { loadConfig(); loadMemoryStats(); loadGitStatus(); }
  if (map.panel === 'users')         loadUsers();
  if (map.panel === 'status')        loadStatus();
  if (map.panel === 'skills')        loadSkillsTab();
  if (map.panel === 'conversations') initConversationsView();
  if (map.panel === 'terminal')      loadDevProvider();
  if (map.channelId)                 loadChannelPage(map.channelId);

  // Switch config sub-tab if needed
  if (map.cfgTab) {
    setTimeout(function() { showCfgTab(map.cfgTab); }, 0);
  }

  // Close mobile sidebar
  closeSidebar();
}

// ── Sidebar Group Toggle ────────────────────────────────────────────────────
function toggleSidebarGroup(groupId) {
  var grp = document.getElementById(groupId);
  if (!grp) return;
  grp.classList.toggle('open');
  try {
    localStorage.setItem('haana_sidebar_' + groupId, grp.classList.contains('open') ? '1' : '0');
  } catch(e) {}
}

function _restoreSidebarGroups() {
  document.querySelectorAll('.sidebar-group[id]').forEach(function(grp) {
    try {
      var stored = localStorage.getItem('haana_sidebar_' + grp.id);
      if (stored === '0') grp.classList.remove('open');
      else if (stored === '1') grp.classList.add('open');
    } catch(e) {}
  });
}

// ── Mobile Sidebar ──────────────────────────────────────────────────────────
function toggleSidebar() {
  var sb = document.getElementById('sidebar');
  var ov = document.getElementById('sidebar-overlay');
  if (!sb) return;
  var isOpen = sb.classList.toggle('open');
  if (ov) ov.classList.toggle('active', isOpen);
}

function closeSidebar() {
  var sb = document.getElementById('sidebar');
  var ov = document.getElementById('sidebar-overlay');
  if (sb) sb.classList.remove('open');
  if (ov) ov.classList.remove('active');
}

// ── Dashboard ───────────────────────────────────────────────────────────────
async function loadDashboard() {
  var grid = document.getElementById('dashboard-tiles');
  if (!grid) return;

  try {
    var r = await fetch('/api/modules/status');
    if (!r.ok) throw new Error('status ' + r.status);
    var data = await r.json();

    var statusClass = function(s) {
      if (s === 'connected') return 'connected';
      if (s === 'degraded')  return 'degraded';
      if (s === 'error')     return 'error';
      return 'unconfigured';
    };
    var statusLabel = function(s) {
      if (s === 'connected') return t('status.connected') || 'Aktiv';
      if (s === 'degraded')  return t('status.degraded')  || 'Warnung';
      if (s === 'error')     return t('status.error')     || 'Fehler';
      return t('status.unconfigured') || 'Inaktiv';
    };

    var channelIds = (data.channels || []).map(function(c) { return c.id; });

    var renderTile = function(m) {
      var sc = statusClass(m.status);
      var metrics = (m.metrics || []).slice(0, 3).map(function(x) {
        return '<div class="tile-metric-row">' +
          '<span>' + escHtml(x.label) + '</span>' +
          '<span class="tile-metric-value">' + escHtml(x.value) + '</span>' +
          '</div>';
      }).join('');
      var tileNav = channelIds.indexOf(m.id) >= 0 ? 'ch-' + m.id : 'sk-' + m.id;
      return '<div class="tile">' +
        '<div class="tile-header">' +
          '<span class="tile-title">' + escHtml(m.display_name) + '</span>' +
          '<span class="tile-status ' + sc + '">' + statusLabel(m.status) + '</span>' +
        '</div>' +
        (metrics ? '<div class="tile-metrics">' + metrics + '</div>' : '') +
        '<button class="tile-action" onclick="navigateTo(\'' + escAttr(tileNav) + '\')"' +
          ' title="' + escAttr(t('status.configure') || 'Konfigurieren') + '">&#9881;</button>' +
        '</div>';
    };

    var allModules = (data.channels || []).concat(data.skills || []);
    if (allModules.length === 0) {
      grid.innerHTML = '<div class="tile"><div class="tile-title"' +
        ' data-i18n="dashboard.no_modules">Keine Module konfiguriert</div></div>';
    } else {
      grid.innerHTML = allModules.map(renderTile).join('');
      loadCoreTiles().then(function(coreHtml) {
        if (coreHtml) grid.innerHTML = coreHtml + grid.innerHTML;
      });
    }

    _updateSidebarDots(data);

  } catch(e) {
    if (grid) grid.innerHTML =
      '<div class="tile"><div style="color:var(--muted);">Dashboard konnte nicht geladen werden.</div></div>';
  }
}

// ── Sidebar Status Dots ─────────────────────────────────────────────────────
function _updateSidebarDots(data) {
  var dotMap = {
    'whatsapp': 'sdot-whatsapp',
    'ha_voice': 'sdot-ha_voice',
    'telegram': 'sdot-telegram',
    'kalender': 'sdot-kalender',
  };
  var allModules = (data.channels || []).concat(data.skills || []);
  allModules.forEach(function(m) {
    var dotId = dotMap[m.id];
    if (!dotId) return;
    var el = document.getElementById(dotId);
    if (!el) return;
    el.className = 'sidebar-dot ' + (
      m.status === 'connected' ? 'active'   :
      m.status === 'degraded'  ? 'warning'  :
      m.status === 'error'     ? 'error'    : 'inactive'
    );
  });
}

// ── Sidebar Init (called from _appInit in app.js) ───────────────────────────
function _sidebarInit() {
  _restoreSidebarGroups();
  var hash = location.hash.replace('#', '') || 'dashboard';
  setTimeout(function() { navigateTo(hash); }, 50);
}
