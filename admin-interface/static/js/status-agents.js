// status-agents.js – Agent-Instanz Status und Steuerung

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

async function loadAgentStatus(allInsts, memMap) {
  const agentHealth = await Promise.all(
    allInsts.map(async inst => {
      try {
        const r = await fetch(`/api/agent-health/${inst}`);
        return { inst, ...(await r.json()) };
      } catch { return { inst, ok: false }; }
    })
  );

  return agentHealth.map(a => {
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
        <button class="btn btn-sm btn-secondary" onclick="instanceControl('${escAttr(a.inst)}','restart')">↺ Restart</button>
        <button class="btn btn-sm btn-secondary" onclick="instanceControl('${escAttr(a.inst)}','stop')">Stop</button>
        <button class="btn btn-sm btn-danger"    onclick="instanceForceStop('${escAttr(a.inst)}')">Kill</button>
      </div>`;
    return `<div class="status-row" style="flex-direction:column;align-items:flex-start;gap:2px;">
      <div style="display:flex;justify-content:space-between;width:100%;align-items:center;">
        <span style="font-weight:500;">${dot} ${escHtml(a.inst)}</span>
        <div style="display:flex;gap:8px;">${queueInfo}${memInfo}</div>
      </div>
      ${controls}
    </div>`;
  }).join('');
}
