// logs.js – Logs laden/rendern, Log-Dateien, Log-Editor

function selectLogCat(cat) {
  currentLogCat = cat;
  document.querySelectorAll('[id^="logbtn-"]').forEach(b => b.classList.remove('active'));
  document.getElementById('logbtn-' + cat)?.classList.add('active');
  loadLogs(cat);
}

async function loadLogs(cat) {
  const list = document.getElementById('log-list');
  list.innerHTML = '<div class="empty-state"><div class="icon">...</div><div>' + t('common.loading') + '</div></div>';
  try {
    const r = await fetch(`/api/logs/${cat}?limit=100`);
    const data = await r.json();
    if (!data.length) {
      list.innerHTML = '<div class="empty-state"><div class="icon">--</div><div>' + t('logs.no_entries') + '</div></div>';
      return;
    }
    list.innerHTML = data.map(rec => {
      const ts = rec.ts ? new Date(rec.ts).toLocaleString('de-DE') : '–';
      const badge = rec.success !== false
        ? '<span style="color:var(--green);font-size:11px;">✓</span>'
        : '<span style="color:var(--red);font-size:11px;">✗</span>';
      let detail = '';
      if (cat === 'memory-ops') {
        detail = `<span class="tag">${rec.op||'?'}</span> <span class="tag">${rec.scope||'?'}</span>`;
        if (rec.results_count !== null && rec.results_count !== undefined) detail += ' \u2192 ' + rec.results_count + ' ' + t('logs.hits');
        if (rec.query) detail += `<br><span style="color:var(--muted);font-size:11px;">${escHtml(rec.query.substring(0,80))}</span>`;
      } else if (cat === 'tool-calls') {
        detail = `<span class="tool-chip">${escHtml(rec.tool||'?')}</span>`;
        if (rec.latency_s) detail += ` <span class="latency">${rec.latency_s}s</span>`;
        if (rec.input) detail += `<br><span style="color:var(--muted);font-size:11px;">${escHtml(rec.input.substring(0,100))}</span>`;
      } else if (cat === 'llm-calls') {
        detail = `<span class="tag">${escHtml(rec.model||'?')}</span>`;
        if (rec.use_case) detail += ` <span class="tag">${escHtml(rec.use_case)}</span>`;
        if (rec.latency_s !== null && rec.latency_s !== undefined) detail += ` <span class="latency">${rec.latency_s}s</span>`;
        const tokIn  = rec.prompt_tokens     != null ? `${rec.prompt_tokens}` : '?';
        const tokOut = rec.completion_tokens != null ? `${rec.completion_tokens}` : '?';
        detail += `<span style="color:var(--muted);font-size:11px;margin-left:8px;">↑${tokIn} ↓${tokOut} tok</span>`;
      }
      return `
      <div class="conv-card" style="margin-bottom:8px;">
        <div class="conv-header" style="cursor:default;">
          <span style="color:var(--muted);font-size:12px;font-family:var(--mono);white-space:nowrap;">${ts}</span>
          <span class="tag">${rec.instance||'?'}</span>
          ${badge}
          <span style="flex:1;">${detail}</span>
          ${rec.error ? `<span style="color:var(--red);font-size:11px;">${escHtml(rec.error.substring(0,60))}</span>` : ''}
        </div>
      </div>`;
    }).join('');
  } catch(e) {
    list.innerHTML = `<div class="empty-state"><div class="icon">!</div><div>${e.message}</div></div>`;
  }
}

// ── Download / Löschen ──────────────────────────────────────────────────────

function downloadLogs(scope) {
  window.location.href = `/api/logs-download?scope=${encodeURIComponent(scope)}`;
}

async function confirmDeleteLogs(scope) {
  const labels = {
    all: t('logs.scope_all'),
    system: t('logs.scope_system'),
    conversations: t('logs.scope_conversations'),
  };
  const label = labels[scope] || scope;
  if (!confirm(t('logs.delete_confirm').replace('{scope}', label))) return;
  try {
    const r = await fetch('/api/logs-delete', {
      method: 'DELETE',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ scope }),
    });
    const d = await r.json();
    if (d.ok) {
      toast(t('logs.deleted_success').replace('{count}', d.deleted), 'ok');
      loadLogs(currentLogCat);
      loadLogFiles(currentInstance);
    } else {
      toast(d.error || t('logs.error'), 'error');
    }
  } catch(e) {
    toast(e.message, 'error');
  }
}

// ── Log-Dateien ─────────────────────────────────────────────────────────────
function selectLogFileInstance(inst) {
  currentInstance = inst;
  document.querySelectorAll('.inst-btn[id^="logfilebtn-"]').forEach(b => b.classList.remove('active'));
  document.getElementById('logfilebtn-' + inst)?.classList.add('active');
  loadLogFiles(inst);
}

async function loadLogFiles(inst) {
  const el = document.getElementById('log-files-list');
  if (!el) return;
  try {
    const r = await fetch(`/api/conversations/${inst}/files`);
    const files = await r.json();
    if (!files.length) {
      el.innerHTML = '<span style="font-size:12px;color:var(--muted);">' + t('logs.no_files') + '</span>';
      return;
    }
    el.innerHTML = files.map(f => `
      <button class="btn btn-secondary" style="font-size:11px;padding:3px 10px;"
        onclick="openLogEditor('${escAttr(inst)}', '${escAttr(f.date)}')" title="${f.entries} ${t('logs.entries')}, ${f.size_kb} KB">
        ${escHtml(f.date)} <span style="color:var(--muted);">(${f.entries})</span>
      </button>`).join('');
  } catch(e) {
    el.innerHTML = `<span style="font-size:12px;color:var(--red);">${e.message}</span>`;
  }
}

// ── Konversations-Log Editor ────────────────────────────────────────────────
let _logEditorInst = null;
let _logEditorDate = null;

async function openLogEditor(inst, date) {
  _logEditorInst = inst;
  _logEditorDate = date;
  const modal = document.getElementById('log-editor-modal');
  const title = document.getElementById('log-editor-title');
  const area  = document.getElementById('log-editor-area');
  const info  = document.getElementById('log-editor-info');
  title.textContent = `${inst} / ${date}.jsonl`;
  area.value = ''; info.textContent = t('common.loading');
  modal.classList.add('active');
  try {
    const r = await fetch(`/api/conversations/${inst}/raw/${date}`);
    const d = await r.json();
    area.value = d.content;
    info.textContent = d.entries + ' ' + t('logs.entries');
  } catch(e) { area.value = ''; info.textContent = '❌ ' + e.message; }
}

function closeLogEditor() {
  document.getElementById('log-editor-modal').classList.remove('active');
}

async function saveLogEditor() {
  const area = document.getElementById('log-editor-area');
  const info = document.getElementById('log-editor-info');
  try {
    const r = await fetch(`/api/conversations/${_logEditorInst}/raw/${_logEditorDate}`, {
      method: 'PUT', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ content: area.value }),
    });
    const d = await r.json();
    if (d.ok) {
      info.textContent = '\u2713 ' + d.entries + ' ' + t('logs.entries_saved');
      toast(t('logs.log_saved'), 'ok');
      closeLogEditor();
      loadConversations(currentInstance);
    } else {
      info.textContent = '\u274c ' + t('logs.error');
    }
  } catch(e) { info.textContent = '\u274c ' + e.message; }
}
