// status.js – Systemstatus laden/rendern (Qdrant, Ollama, Instanzen)

// loadOllamaCompatStatus() — integriert in Agenten-Karten via loadStatus()
async function loadOllamaCompatStatus() { /* no-op, integriert in Agent-Karten */ }

async function loadModuleStatus() {
  const channelsGrid = document.getElementById('status-channels-grid');
  const skillsGrid = document.getElementById('status-skills-grid');
  if (!channelsGrid && !skillsGrid) return;
  try {
    const r = await fetch('/api/modules/status');
    if (!r.ok) return;
    const data = await r.json();

    const dotClass = s => {
      if (s === 'connected') return 'status-dot-connected';
      if (s === 'degraded')  return 'status-dot-degraded';
      if (s === 'error')     return 'status-dot-error';
      return 'status-dot-unconfigured';
    };

    const renderCard = m => {
      const dot = `<span class="status-dot-sm ${dotClass(m.status)}"></span>`;
      const details = m.details ? `<div style="font-size:12px;color:var(--muted);margin-top:2px;">${escHtml(m.details)}</div>` : '';
      const metrics = (m.metrics || []).length
        ? `<div class="module-metrics">${(m.metrics || []).map(x =>
            `<span class="module-metric">${escHtml(x.label)}: ${escHtml(x.value)}</span>`
          ).join('')}</div>`
        : '';
      const actions = (m.actions || []).length
        ? `<div style="display:flex;gap:4px;margin-top:6px;">${(m.actions || []).map(a => {
            const cls = a.style === 'primary' ? 'btn-primary' : a.style === 'danger' ? 'btn-danger' : 'btn-secondary';
            const onclick = a.id === 'open_config'
              ? `onclick="showTab('config')"`
              : `onclick="moduleAction('${escAttr(m.id)}','${escAttr(a.id)}')"`;
            return `<button class="btn btn-sm ${cls}" ${onclick}>${escHtml(a.label)}</button>`;
          }).join('')}</div>`
        : '';
      return `<div class="status-card">
        <h3 style="display:flex;align-items:center;gap:6px;">${dot} ${escHtml(m.display_name)}</h3>
        <div class="status-row">
          <span>${escHtml(m.label)}</span>
        </div>
        ${details}${metrics}${actions}
      </div>`;
    };

    if (channelsGrid) {
      const channels = data.channels || [];
      channelsGrid.innerHTML = channels.length
        ? channels.map(renderCard).join('')
        : `<div class="status-card"><div style="color:var(--muted);">–</div></div>`;
    }
    if (skillsGrid) {
      const skills = data.skills || [];
      skillsGrid.innerHTML = skills.length
        ? skills.map(renderCard).join('')
        : `<div class="status-card"><div style="color:var(--muted);">–</div></div>`;
    }
  } catch(e) {
    console.warn('module status:', e);
  }
}

async function moduleAction(id, action) {
  // Placeholder für zukünftige Modul-Aktionen
  console.log('moduleAction:', id, action);
}

async function loadStatus() {
  _renderStatusChecklist();
  loadOllamaCompatStatus();
  loadModuleStatus();
  loadDreamStatus();
  const grid = document.getElementById('status-grid');
  grid.innerHTML = '<div class="status-card"><div class="empty-state"><div class="icon">...</div><div>' + t('status.checking') + '</div></div></div>';
  try {
    const [s, memStats] = await Promise.all([
      fetch('/api/status').then(r => r.json()),
      fetch('/api/memory-stats').then(r => r.json()).catch(() => []),
    ]);

    const qdrant = s.qdrant || {};
    const ollama = s.ollama || {};
    const logs   = s.logs   || {};

    const colls = (qdrant.collections || []).map(c => `<span class="tag">${escHtml(c)}</span>`).join(' ');
    const models = (ollama.models || []).map(m => `<span class="tag">${escHtml(m)}</span>`).join(' ');

    // Memory-Stats-Map für schnellen Lookup
    const memMap = {};
    (memStats || []).forEach(m => memMap[m.instance] = m);

    // Agent-Status + Health via status-agents.js
    const allInsts = INSTANCES;
    const agentRows = await loadAgentStatus(allInsts, memMap);

    const logRows = Object.entries(logs).map(([inst, info]) =>
      `<div class="status-row"><span>${escHtml(inst)}</span><span>${escHtml(String(info.days))} ${t('status.days_last')} ${escHtml(info.latest||'–')}</span></div>`
    ).join('');

    grid.innerHTML = `
      <div class="status-card">
        <h3 style="display:flex;justify-content:space-between;align-items:center;">
          Qdrant
          <button class="btn btn-sm btn-secondary" onclick="qdrantRestart()">\u21ba Restart</button>
        </h3>
        <div class="status-row">
          <span>Status</span>
          <span class="${qdrant.ok ? 'status-ok' : 'status-err'}">${qdrant.ok ? '\u2713 ' + t('status.online') : '\u2717 ' + escHtml(qdrant.error||t('status.error'))}</span>
        </div>
        ${qdrant.ok ? `<div class="status-row"><span>Collections</span><div style="display:flex;flex-wrap:wrap;gap:4px;justify-content:flex-end;">
          ${(qdrant.collections||[]).map(c => `<span class="tag" style="display:inline-flex;align-items:center;gap:4px;">${escHtml(c)}<button onclick="deleteQdrantCollection('${escAttr(c)}')" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:11px;padding:0;" title="${t('status.delete_label')}">\u2715</button></span>`).join('')||t('status.no_collections')}
        </div></div>` : ''}
      </div>
      <div class="status-card">
        <h3>Ollama</h3>
        <div class="status-row">
          <span>Status</span>
          <span class="${ollama.ok ? 'status-ok' : 'status-warn'}">${ollama.ok ? '\u2713 ' + t('status.online') : '\u26a0 ' + escHtml(ollama.error||t('status.not_reachable'))}</span>
        </div>
        ${ollama.ok ? `<div class="status-row"><span>${t('config_llm.model')}</span><div style="text-align:right;">${models||t('status.no_models')}</div></div>` : ''}
      </div>
      <div class="status-card" style="grid-column:1/-1;">
        <h3>${t('status.agent_instances')}</h3>
        ${agentRows || '<div style="color:var(--muted)">' + t('status.no_instances') + '</div>'}
      </div>
      <div class="status-card">
        <h3>${t('status.conversation_logs')}</h3>
        ${logRows || '<div style="color:var(--muted)">' + t('status.no_logs') + '</div>'}
      </div>
    `;

    // Rebuild-Banner (leer oder Dimensions-Mismatch)
    const banner = document.getElementById('rebuild-banner');
    if (banner) {
      const needsRebuild = !!qdrant.rebuild_suggested || !!qdrant.dims_mismatch;
      banner.classList.toggle('active', needsRebuild);
      const bannerText = banner.querySelector('.rebuild-banner-text');
      if (bannerText && qdrant.dims_mismatch) {
        bannerText.textContent = t('status.dims_mismatch');
      } else if (bannerText) {
        bannerText.textContent = t('status.rebuild_banner');
      }
    }

    const allOk = qdrant.ok;
    document.getElementById('header-dot').style.background = allOk ? 'var(--green)' : 'var(--red)';
    document.getElementById('header-status').textContent = allOk ? t('status.system_ok') : t('status.system_error');
  } catch(e) {
    grid.innerHTML = `<div class="status-card"><div class="empty-state"><div class="icon">!</div><div>${escHtml(e.message)}</div></div></div>`;
  }
}

async function qdrantRestart() {
  Modal.showConfirm(t('status.qdrant_restart_confirm'), async () => {
    const r = await fetch('/api/qdrant/restart', { method: 'POST' });
    const d = await r.json();
    if (d.ok) { toast(t('status.qdrant_restarting') + ' \u2713', 'ok'); setTimeout(loadStatus, 3000); }
    else       { toast(t('status.qdrant_restart_failed') + ': ' + (d.error||'?').substring(0,60), 'err'); }
  });
}

async function deleteQdrantCollection(name) {
  Modal.showDangerConfirm(t('status.delete_collection_confirm', {name: name}), async () => {
    const r = await fetch(`/api/qdrant/collections/${encodeURIComponent(name)}`, { method: 'DELETE' });
    const d = await r.json();
    toast(d.result === true ? t('status.collection_deleted', {name: name}) + ' \u2713' : t('common.error') + ': ' + JSON.stringify(d).substring(0,60), d.result === true ? 'ok' : 'err');
    loadStatus();
    loadMemoryStats();
  });
}

async function _renderStatusChecklist() {
  try {
    const r = await fetch('/api/system-status');
    if (!r.ok) return;
    const {checks} = await r.json();
    const el = document.getElementById('status-checklist');
    if (!el) return;
    el.innerHTML = checks.map(c => `
      <div class="checklist-item ${c.ok ? 'ok' : 'warn'}">
        <span class="check-icon">${c.ok ? '&#10003;' : '&#9888;'}</span>
        <a href="${escAttr(c.link)}" onclick="_checklistNav(event, '${escAttr(c.link)}')">${escHtml(c.label)}</a>
      </div>
    `).join('');
  } catch(_) {}
}

function _checklistNav(e, link) {
  if (!link.startsWith('#')) return;
  e.preventDefault();
  const tabName = link.slice(1);
  const tabBtn = document.querySelector(`.tab-btn[onclick*="'${tabName}'"]`);
  if (tabBtn) tabBtn.click();
}

async function systemUpdate() {
  toast(t('status.updating'), 'ok');
  try {
    const r = await fetch('/api/system/update', { method: 'POST' });
    const d = await r.json();
    if (d.ok) {
      toast(d.message || t('status.updating'), 'ok');
      // Seite nach 60s neu laden (Container-Neustart dauert ~30s)
      setTimeout(() => location.reload(), 60000);
    } else {
      toast((d.error || d.message || '?'), 'err');
    }
  } catch(e) {
    toast(e.message, 'err');
  }
}
