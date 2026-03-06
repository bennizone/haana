// status.js – Systemstatus laden/rendern (Qdrant, Ollama, Instanzen)

async function loadStatus() {
  const grid = document.getElementById('status-grid');
  grid.innerHTML = '<div class="status-card"><div class="empty-state"><div class="icon">...</div><div>Wird geprüft...</div></div></div>';
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
      const dot = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${a.ok?'var(--green)':'var(--red)'};"></span>`;
      const mem = memMap[a.inst];
      const queueInfo = a.ok
        ? `<span style="font-size:11px;color:var(--muted);">Win: ${a.window_size??'?'} | Queue: ${a.pending_extractions??'?'}</span>`
        : `<span style="font-size:11px;color:var(--muted);">offline</span>`;
      const memInfo = mem
        ? `<span style="font-size:11px;color:${mem.total_vectors===0&&mem.log_entries>0?'var(--yellow)':'var(--muted)'};">${mem.total_vectors} Vektoren</span>`
        : '';
      const controls = `
        <div style="display:flex;gap:4px;margin-top:6px;">
          <button class="btn btn-secondary" style="font-size:10px;padding:2px 8px;" onclick="instanceControl('${a.inst}','restart')">↺ Restart</button>
          <button class="btn btn-secondary" style="font-size:10px;padding:2px 8px;" onclick="instanceControl('${a.inst}','stop')">Stop</button>
          <button class="btn btn-danger"    style="font-size:10px;padding:2px 8px;" onclick="instanceForceStop('${a.inst}')">Kill</button>
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
      `<div class="status-row"><span>${inst}</span><span>${info.days} Tag(e), zuletzt ${info.latest||'–'}</span></div>`
    ).join('');

    grid.innerHTML = `
      <div class="status-card">
        <h3 style="display:flex;justify-content:space-between;align-items:center;">
          Qdrant
          <button class="btn btn-secondary" style="font-size:10px;padding:2px 8px;" onclick="qdrantRestart()">↺ Restart</button>
        </h3>
        <div class="status-row">
          <span>Status</span>
          <span class="${qdrant.ok ? 'status-ok' : 'status-err'}">${qdrant.ok ? '✓ Online' : '✗ ' + (qdrant.error||'Fehler')}</span>
        </div>
        ${qdrant.ok ? `<div class="status-row"><span>Collections</span><div style="display:flex;flex-wrap:wrap;gap:4px;justify-content:flex-end;">
          ${(qdrant.collections||[]).map(c => `<span class="tag" style="display:inline-flex;align-items:center;gap:4px;">${escHtml(c)}<button onclick="deleteQdrantCollection('${escAttr(c)}')" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:11px;padding:0;" title="Löschen">✕</button></span>`).join('')||'keine'}
        </div></div>` : ''}
      </div>
      <div class="status-card">
        <h3>Ollama</h3>
        <div class="status-row">
          <span>Status</span>
          <span class="${ollama.ok ? 'status-ok' : 'status-warn'}">${ollama.ok ? '✓ Online' : '⚠ ' + (ollama.error||'nicht erreichbar')}</span>
        </div>
        ${ollama.ok ? `<div class="status-row"><span>Modelle</span><div style="text-align:right;">${models||'keine'}</div></div>` : ''}
      </div>
      <div class="status-card" style="grid-column:1/-1;">
        <h3>Agent-Instanzen</h3>
        ${agentRows || '<div style="color:var(--muted)">Keine Instanzen</div>'}
      </div>
      <div class="status-card">
        <h3>Konversations-Logs</h3>
        ${logRows || '<div style="color:var(--muted)">Noch keine Logs</div>'}
      </div>
    `;

    // Rebuild-Banner
    const banner = document.getElementById('rebuild-banner');
    if (banner) banner.classList.toggle('active', !!qdrant.rebuild_suggested);

    const allOk = qdrant.ok;
    document.getElementById('header-dot').style.background = allOk ? 'var(--green)' : 'var(--red)';
    document.getElementById('header-status').textContent = allOk ? 'System OK' : 'Fehler – Details im Status-Tab';
  } catch(e) {
    grid.innerHTML = `<div class="status-card"><div class="empty-state"><div class="icon">!</div><div>${e.message}</div></div></div>`;
  }
}

// ── Instanz-Steuerung ───────────────────────────────────────────────────────
async function instanceControl(inst, action) {
  const r = await fetch(`/api/instances/${inst}/${action}`, { method: 'POST' });
  const d = await r.json();
  if (d.ok) { toast(`${inst}: ${action} ✓`, 'ok'); loadStatus(); }
  else       { toast(`${inst} ${action} fehlgeschlagen: ${(d.error||'?').substring(0,60)}`, 'err'); }
}

async function instanceForceStop(inst) {
  Modal.showDangerConfirm(`${inst} sofort beenden (SIGKILL)?\n\nACHTUNG: Laufende Memory-Extraktion geht verloren – Konversations-Logs bleiben erhalten.`, async () => {
    const r = await fetch(`/api/instances/${inst}/force-stop`, { method: 'POST' });
    const d = await r.json();
    if (d.ok) { toast(`${inst} beendet ✓`, 'ok'); loadStatus(); }
    else       { toast(`Kill fehlgeschlagen: ${(d.error||'?').substring(0,60)}`, 'err'); }
  });
}

async function qdrantRestart() {
  Modal.showConfirm('Qdrant neu starten? Laufende Vorgänge werden unterbrochen.', async () => {
    const r = await fetch('/api/qdrant/restart', { method: 'POST' });
    const d = await r.json();
    if (d.ok) { toast('Qdrant wird neu gestartet ✓', 'ok'); setTimeout(loadStatus, 3000); }
    else       { toast(`Qdrant Restart fehlgeschlagen: ${(d.error||'?').substring(0,60)}`, 'err'); }
  });
}

async function deleteQdrantCollection(name) {
  Modal.showDangerConfirm(`Collection "${name}" endgültig löschen?\n\nDanach Memory-Rebuild für betroffene Instanzen erforderlich.`, async () => {
    const r = await fetch(`/api/qdrant/collections/${encodeURIComponent(name)}`, { method: 'DELETE' });
    const d = await r.json();
    toast(d.result === true ? `"${name}" gelöscht ✓` : `Fehler: ${JSON.stringify(d).substring(0,60)}`, d.result === true ? 'ok' : 'err');
    loadStatus();
    loadMemoryStats();
  });
}
