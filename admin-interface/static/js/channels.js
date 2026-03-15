// channels.js – Dedizierte Channel/Skill Seiten (Phase 2 Redesign)
// Requires: modules.js (_loadModules, _renderModuleConfigFields, saveModuleConfig),
//           utils.js (escHtml, escAttr, t)

// ── Channel/Skill-Seite laden ───────────────────────────────────────────────

async function loadChannelPage(moduleId) {
  var panelId = moduleId === 'kalender'
    ? 'panel-sk-kalender'
    : 'panel-ch-' + moduleId;

  var panel = document.getElementById(panelId);
  if (!panel) return;

  panel.innerHTML = '<div class="empty-state"><div class="icon">&#8230;</div><div>Wird geladen\u2026</div></div>';

  try {
    var results = await Promise.all([
      fetch('/api/modules').then(function(r) { return r.json(); }),
      fetch('/api/modules/status').then(function(r) { return r.json(); }),
      fetch('/api/modules/config').then(function(r) { return r.json(); })
    ]);
    var modulesData = results[0];
    var statusData  = results[1];
    var configData  = results[2];

    var allMods = (modulesData.channels || []).concat(modulesData.skills || []);
    var mod = allMods.find(function(m) { return m.id === moduleId; });
    if (!mod) {
      panel.innerHTML = '<div class="empty-state"><div style="color:var(--muted);">Modul nicht gefunden: '
        + escHtml(moduleId) + '</div></div>';
      return;
    }

    var allStatus = (statusData.channels || []).concat(statusData.skills || []);
    var statusInfo = allStatus.find(function(m) { return m.id === moduleId; })
      || { status: 'unconfigured', label: 'Unbekannt' };

    var headerHtml = _renderChannelHeader(mod, statusInfo);

    var vals = configData[moduleId] || {};
    var isSkill = (modulesData.skills || []).some(function(s) { return s.id === moduleId; });
    var formHtml = '';
    if (mod.config_schema && mod.config_schema.length > 0) {
      formHtml = '<div class="config-section" style="margin-top:var(--sp-4);">'
        + '<div class="config-section-header">'
        + escHtml(t('channel_page.config_title'))
        + '</div>'
        + '<div class="config-section-body">'
        + _renderModuleConfigFields(moduleId, mod.display_name, mod.config_schema, vals, isSkill)
        + '</div></div>';
    } else {
      formHtml = '<div class="config-section" style="margin-top:var(--sp-4);">'
        + '<div class="config-section-body">'
        + '<p class="form-hint">'
        + escHtml(t('channel_page.no_config'))
        + '</p>'
        + '</div></div>';
    }

    panel.innerHTML = '<div style="padding:var(--sp-6);">' + headerHtml + formHtml + '</div>';

  } catch(e) {
    panel.innerHTML = '<div style="padding:var(--sp-6);color:var(--muted);">Fehler: '
      + escHtml(e.message) + '</div>';
  }
}


// ── Channel Header Block ────────────────────────────────────────────────────

function _renderChannelHeader(mod, statusInfo) {
  var sc = _chStatusClass(statusInfo.status);
  var label = escHtml(statusInfo.label || statusInfo.status);

  var metricsHtml = '';
  if ((statusInfo.metrics || []).length) {
    metricsHtml = '<div class="channel-header-metrics">'
      + (statusInfo.metrics || []).map(function(x) {
          return '<span class="channel-metric">'
            + escHtml(x.label) + ': <strong>' + escHtml(x.value) + '</strong>'
            + '</span>';
        }).join('')
      + '</div>';
  }

  var actionsHtml = '';
  var actions = (statusInfo.actions || []).filter(function(a) { return a.id !== 'open_config'; });
  if (actions.length) {
    actionsHtml = '<div class="channel-header-actions">'
      + actions.map(function(a) {
          var cls = a.style === 'primary'
            ? 'btn-primary'
            : (a.style === 'danger' ? 'btn-danger' : 'btn-secondary');
          var onclick = a.id === 'open_config'
            ? 'navigateTo(\'providers\')'
            : 'moduleAction(\'' + escAttr(mod.id) + '\',\'' + escAttr(a.id) + '\')';
          return '<button class="btn btn-sm ' + cls + '" onclick="' + onclick + '">'
            + escHtml(a.label) + '</button>';
        }).join('')
      + '</div>';
  }

  return '<div class="channel-header">'
    + '<div class="channel-header-title">'
      + '<span class="channel-header-name">' + escHtml(mod.display_name) + '</span>'
      + '<span class="channel-header-status ' + sc + '">'
        + '<span class="channel-header-dot"></span>'
        + label
      + '</span>'
    + '</div>'
    + (statusInfo.details
        ? '<div class="channel-header-detail">' + escHtml(statusInfo.details) + '</div>'
        : '')
    + metricsHtml
    + actionsHtml
    + '</div>';
}

function _chStatusClass(status) {
  if (status === 'connected') return 'status-connected';
  if (status === 'degraded')  return 'status-degraded';
  if (status === 'error')     return 'status-error';
  return 'status-unconfigured';
}


// ── Dashboard: Core-Tiles ───────────────────────────────────────────────────

async function loadCoreTiles() {
  try {
    var results = await Promise.all([
      fetch('/api/status').then(function(r) { return r.json(); }),
      fetch('/api/users').then(function(r) { return r.json(); })
    ]);
    var data = results[0];
    var users = Array.isArray(results[1]) ? results[1] : [];
    data.agents = users.map(function(u) {
      return { id: u.id, instance: u.id, status: u.container_status };
    });
    return _renderCoreTiles(data);
  } catch(e) {
    return '';
  }
}

function _renderCoreTiles(data) {
  var tiles = [];

  var agents = data.agents || [];
  var runningCount = agents.filter(function(a) { return a.status === 'running'; }).length;
  tiles.push('<div class="tile">'
    + '<div class="tile-header">'
      + '<span class="tile-title">' + escHtml(t('sidebar.agents')) + '</span>'
      + '<span class="tile-status ' + (runningCount > 0 ? 'connected' : 'unconfigured') + '">'
        + runningCount + ' aktiv'
      + '</span>'
    + '</div>'
    + '<div class="tile-metrics">'
      + agents.slice(0, 3).map(function(a) {
          return '<div class="tile-metric-row">'
            + '<span>' + escHtml(a.instance || a.id || '') + '</span>'
            + '<span class="tile-metric-value" style="color:'
              + (a.status === 'running' ? 'var(--green)' : 'var(--muted)') + ';">'
              + (a.status === 'running' ? 'online' : 'offline') + '</span>'
            + '</div>';
        }).join('')
    + '</div>'
    + '<button class="tile-action" onclick="navigateTo(\'agents\')"'
      + ' title="' + escAttr(t('status.configure')) + '">&#9881;</button>'
    + '</div>');

  var qdrant = data.qdrant || {};
  var qdrantStatus = qdrant.status === 'ok'
    ? 'connected'
    : (qdrant.status ? 'error' : 'unconfigured');
  tiles.push('<div class="tile">'
    + '<div class="tile-header">'
      + '<span class="tile-title">Memory</span>'
      + '<span class="tile-status ' + qdrantStatus + '">'
        + escHtml(qdrant.status || 'unbekannt')
      + '</span>'
    + '</div>'
    + '<div class="tile-metrics">'
      + (qdrant.collections != null
          ? '<div class="tile-metric-row"><span>Collections</span>'
            + '<span class="tile-metric-value">' + escHtml(String(qdrant.collections)) + '</span></div>'
          : '')
      + (qdrant.vectors != null
          ? '<div class="tile-metric-row"><span>Vektoren</span>'
            + '<span class="tile-metric-value">' + escHtml(String(qdrant.vectors)) + '</span></div>'
          : '')
    + '</div>'
    + '<button class="tile-action" onclick="navigateTo(\'memory\')" title="Details">&#9881;</button>'
    + '</div>');

  return tiles.join('');
}
