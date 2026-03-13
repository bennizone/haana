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

    // Agent-Status + Health parallel
    const allInsts = INSTANCES;
    const agentHealth = await Promise.all(
      allInsts.map(async inst => {
        try {
          const r = await fetch(`/api/agent-health/${inst}`);
          return { inst, ...(await r.json()) };
        } catch { return { inst, ok: false }; }
      })
    );

    // Memory-Stats-Map für schnellen Lookup
    const memMap = {};
    (memStats || []).forEach(m => memMap[m.instance] = m);

    const agentRows = agentHealth.map(a => {
      const dot = `<span class="status-dot-sm ${a.ok ? 'ok' : 'err'}"></span>`;
      const mem = memMap[a.inst];
      const queueInfo = a.ok
        ? `<span style="font-size:11px;color:var(--muted);">Win: ${a.window_size??'?'} | Queue: ${a.pending_extractions??'?'}</span>`
        : `<span style="font-size:11px;color:var(--muted);">${t('status.offline')}</span>`;
      const memInfo = mem
        ? `<span style="font-size:11px;color:${mem.total_vectors===0&&mem.log_entries>0?'var(--yellow)':'var(--muted)'};">${mem.total_vectors} ${t('status.vectors')}</span>`
        : '';
      const controls = `
        <div style="display:flex;gap:4px;margin-top:6px;">
          <button class="btn btn-sm btn-secondary" onclick="instanceControl('${a.inst}','restart')">↺ Restart</button>
          <button class="btn btn-sm btn-secondary" onclick="instanceControl('${a.inst}','stop')">Stop</button>
          <button class="btn btn-sm btn-danger"    onclick="instanceForceStop('${a.inst}')">Kill</button>
        </div>`;
      return `<div class="status-row" style="flex-direction:column;align-items:flex-start;gap:2px;">
        <div style="display:flex;justify-content:space-between;width:100%;align-items:center;">
          <span style="font-weight:500;">${dot} ${a.inst}</span>
          <div style="display:flex;gap:8px;">${queueInfo}${memInfo}</div>
        </div>
        ${controls}
      </div>`;
    }).join('');

    const logRows = Object.entries(logs).map(([inst, info]) =>
      `<div class="status-row"><span>${inst}</span><span>${info.days} ${t('status.days_last')} ${info.latest||'–'}</span></div>`
    ).join('');

    grid.innerHTML = `
      <div class="status-card">
        <h3 style="display:flex;justify-content:space-between;align-items:center;">
          Qdrant
          <button class="btn btn-sm btn-secondary" onclick="qdrantRestart()">\u21ba Restart</button>
        </h3>
        <div class="status-row">
          <span>Status</span>
          <span class="${qdrant.ok ? 'status-ok' : 'status-err'}">${qdrant.ok ? '\u2713 ' + t('status.online') : '\u2717 ' + (qdrant.error||t('status.error'))}</span>
        </div>
        ${qdrant.ok ? `<div class="status-row"><span>Collections</span><div style="display:flex;flex-wrap:wrap;gap:4px;justify-content:flex-end;">
          ${(qdrant.collections||[]).map(c => `<span class="tag" style="display:inline-flex;align-items:center;gap:4px;">${escHtml(c)}<button onclick="deleteQdrantCollection('${escAttr(c)}')" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:11px;padding:0;" title="${t('status.delete_label')}">\u2715</button></span>`).join('')||t('status.no_collections')}
        </div></div>` : ''}
      </div>
      <div class="status-card">
        <h3>Ollama</h3>
        <div class="status-row">
          <span>Status</span>
          <span class="${ollama.ok ? 'status-ok' : 'status-warn'}">${ollama.ok ? '\u2713 ' + t('status.online') : '\u26a0 ' + (ollama.error||t('status.not_reachable'))}</span>
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
    grid.innerHTML = `<div class="status-card"><div class="empty-state"><div class="icon">!</div><div>${e.message}</div></div></div>`;
  }
}

// ── Instanz-Steuerung ───────────────────────────────────────────────────────
async function instanceControl(inst, action) {
  const r = await fetch(`/api/instances/${inst}/${action}`, { method: 'POST' });
  const d = await r.json();
  if (d.ok) { toast(inst + ': ' + action + ' \u2713', 'ok'); loadStatus(); }
  else       { toast(inst + ' ' + action + ' ' + t('status.action_failed') + ': ' + (d.error||'?').substring(0,60), 'err'); }
}

async function instanceForceStop(inst) {
  Modal.showDangerConfirm(t('status.force_stop_confirm', {instance: inst}), async () => {
    const r = await fetch(`/api/instances/${inst}/force-stop`, { method: 'POST' });
    const d = await r.json();
    if (d.ok) { toast(t('status.force_stop_done', {instance: inst}), 'ok'); loadStatus(); }
    else       { toast(t('status.force_stop_failed') + ': ' + (d.error||'?').substring(0,60), 'err'); }
  });
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
        <a href="${c.link}" onclick="_checklistNav(event, '${c.link}')">${c.label}</a>
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

async function restartAllAgentsStatus() {
  const r = await fetch('/api/instances/restart-all', { method: 'POST' });
  const d = await r.json();
  if (d.failed && Object.keys(d.failed).length > 0) {
    const fails = Object.entries(d.failed).map(([k,v]) => `${k}: ${v}`).join(', ');
    toast(t('config.restart_partial') + ': ' + fails.substring(0, 80), 'warn');
  } else {
    toast(t('config.restart_success'), 'ok');
  }
  setTimeout(loadStatus, 2000);
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

// ── Dream Process ─────────────────────────────────────────────────────────────

function _dreamTimeAgo(isoStr) {
  try {
    const diff = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000);
    if (diff < 60)   return diff + 's';
    if (diff < 3600) return Math.floor(diff/60) + 'min';
    if (diff < 86400) return Math.floor(diff/3600) + 'h';
    return Math.floor(diff/86400) + 'd';
  } catch { return ''; }
}

async function runDreamNow(inst, btn) {
  if (btn) btn.disabled = true;
  try {
    const r = await fetch(`/api/dream/run/${encodeURIComponent(inst)}`, { method: 'POST' });
    const d = await r.json();
    if (r.ok) {
      toast(t('config_memory.dream_run_now') + ' \u2013 ' + inst, 'ok');
      setTimeout(loadDreamStatus, 3000);
    } else {
      toast((d.error || '?').substring(0, 80), 'err');
      if (btn) btn.disabled = false;
    }
  } catch(e) {
    toast(e.message, 'err');
    if (btn) btn.disabled = false;
  }
}

async function openDreamDiary(inst) {
  let entries = [];
  try {
    const r = await fetch(`/api/dream/logs/${encodeURIComponent(inst)}?limit=14`);
    if (r.ok) entries = await r.json();
  } catch(e) { /* still show modal */ }

  let bodyHtml;
  if (!entries || entries.length === 0) {
    bodyHtml = `<p style="color:var(--muted);text-align:center;padding:20px 0;">${t('config_memory.dream_diary_empty')}</p>`;
  } else {
    bodyHtml = `<div style="display:flex;flex-direction:column;gap:12px;max-height:420px;overflow-y:auto;padding-right:4px;">` +
      entries.map(e => `<div style="border-bottom:1px solid var(--border);padding-bottom:8px;">
        <div style="font-size:11px;color:var(--muted);margin-bottom:4px;">${escHtml(e.date||'')}</div>
        <div style="font-size:13px;">${escHtml(e.summary||'')}</div>
      </div>`).join('') + `</div>`;
  }

  showModal({
    title: t('config_memory.dream_diary') + ' \u2013 ' + escHtml(inst),
    body: bodyHtml,
    confirmText: null,
    cancelText: t('common.close') || 'Schlie\u00dfen',
  });
}

async function loadDreamStatus() {
  const grid = document.getElementById('status-dream-grid');
  if (!grid) return;
  const insts = (typeof INSTANCES !== 'undefined' && INSTANCES.length) ? INSTANCES : [];
  if (!insts.length) {
    grid.innerHTML = `<div class="status-card"><div style="color:var(--muted);">–</div></div>`;
    return;
  }

  const dotClass = s => {
    if (s === 'running') return 'status-dot-degraded';
    if (s === 'done')    return 'status-dot-connected';
    if (s === 'error')   return 'status-dot-error';
    return 'status-dot-unconfigured';
  };

  const results = await Promise.all(insts.map(async inst => {
    try {
      const r = await fetch(`/api/dream/status/${encodeURIComponent(inst)}`);
      if (!r.ok) return { inst, status: 'idle' };
      return { inst, ...(await r.json()) };
    } catch { return { inst, status: 'idle' }; }
  }));

  grid.innerHTML = `<div class="status-card" style="grid-column:1/-1;">
    <h3 style="margin-bottom:8px;" data-i18n="config_memory.dream_title">${t('config_memory.dream_title')}</h3>
    ${results.map(d => {
      const dot = `<span class="status-dot-sm ${dotClass(d.status)}"></span>`;
      let info = '';
      if (d.status === 'running') {
        info = `<span style="color:var(--yellow);">\u23f3 ${t('config_memory.dream_status_running')}</span>`;
      } else if (d.status === 'done') {
        const parts = [];
        if (d.consolidated != null) parts.push(`${d.consolidated} ${t('config_memory.dream_consolidated')}`);
        if (d.contradictions != null) parts.push(`${d.contradictions} ${t('config_memory.dream_contradictions')}`);
        const detail = parts.length ? ' \u2014 ' + parts.join(', ') : '';
        const ago = d.last_run ? _dreamTimeAgo(d.last_run) : '';
        const dur = d.duration_seconds != null ? `, ${d.duration_seconds}s` : '';
        info = `<span style="color:var(--green);">${t('config_memory.dream_status_done')}: ${escHtml(ago)}${escHtml(detail)}${escHtml(dur)}</span>`;
      } else if (d.status === 'error') {
        info = `<span style="color:var(--red);">\u274c ${t('config_memory.dream_status_error')}: ${escHtml(d.error || '')}</span>`;
      } else {
        const nextRun = d.next_run || (typeof cfg !== 'undefined' && cfg.dream?.schedule) || '02:00';
        info = `<span style="color:var(--muted);">${t('config_memory.dream_status_idle')}: ${escHtml(nextRun)}</span>`;
      }
      return `<div class="status-row" style="flex-direction:column;align-items:flex-start;gap:4px;padding:6px 0;border-bottom:1px solid var(--border);">
        <div style="display:flex;align-items:center;gap:8px;width:100%;">
          ${dot}
          <span style="font-weight:500;">${escHtml(d.inst)}</span>
          <span style="font-size:12px;margin-left:auto;">${info}</span>
        </div>
        <div style="display:flex;gap:4px;margin-top:2px;">
          <button class="btn btn-sm btn-secondary" onclick="runDreamNow('${escAttr(d.inst)}', this)">${t('config_memory.dream_run_now')}</button>
          <button class="btn btn-sm btn-secondary" onclick="openDreamDiary('${escAttr(d.inst)}')">${t('config_memory.dream_diary')}</button>
        </div>
      </div>`;
    }).join('')}
  </div>`;
}
