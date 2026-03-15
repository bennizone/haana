// status-dream.js – Dream Process Status und Steuerung

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
    if (!r.ok) {
      toast((d.error || '?').substring(0, 80), 'err');
      if (btn) btn.disabled = false;
      return;
    }
    toast(t('config_memory.dream_run_now') + ' \u2013 ' + inst, 'ok');
    loadDreamStatus();
    // Alle 3s pollen bis Dream fertig, max 10 Versuche (30s)
    let attempts = 0;
    const poll = setInterval(async () => {
      attempts++;
      try {
        const sr = await fetch(`/api/dream/status/${encodeURIComponent(inst)}`);
        const sd = await sr.json();
        if (sd.status !== 'running' || attempts >= 10) {
          clearInterval(poll);
          if (btn) btn.disabled = false;
          loadDreamStatus();
        }
      } catch {
        clearInterval(poll);
        if (btn) btn.disabled = false;
      }
    }, 3000);
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

  // Deduplizieren: pro Datum nur neuesten Eintrag behalten (API liefert absteigend)
  const byDate = new Map();
  for (const e of entries) {
    if (!byDate.has(e.date || '')) byDate.set(e.date || '', e);
  }
  entries = Array.from(byDate.values());

  if (!entries || entries.length === 0) {
    Modal.showAlert(t('config_memory.dream_diary_empty'));
    return;
  }

  const bodyHtml = `<div style="display:flex;flex-direction:column;gap:12px;max-height:420px;overflow-y:auto;padding-right:4px;">` +
    entries.map(e => `<div style="border-bottom:1px solid var(--border);padding-bottom:8px;">
      <div style="font-size:11px;color:var(--muted);margin-bottom:4px;">${escHtml(e.date||'')}</div>
      <div style="font-size:13px;">${escHtml(e.summary||'')}</div>
    </div>`).join('') + `</div>`;

  Modal.show({
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
        if (d.report?.consolidated != null) parts.push(`${d.report.consolidated} ${t('config_memory.dream_consolidated')}`);
        if (d.report?.contradictions != null) parts.push(`${d.report.contradictions} ${t('config_memory.dream_contradictions')}`);
        const detail = parts.length ? ' \u2014 ' + parts.join(', ') : '';
        const ago = d.last_run ? _dreamTimeAgo(d.last_run) : '';
        const dur = d.report?.duration_s != null ? `, ${d.report.duration_s}s` : '';
        info = `<span style="color:var(--green);">${t('config_memory.dream_status_done')}: ${escHtml(ago)}${escHtml(detail)}${escHtml(dur)}</span>`;
      } else if (d.status === 'error') {
        info = `<span style="color:var(--red);">\u274c ${t('config_memory.dream_status_error')}: ${escHtml(d.error || '')}</span>`;
      } else {
        const nextRun = d.next_run || cfg?.dream?.schedule || '02:00';
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
