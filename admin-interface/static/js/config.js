// config.js – Config laden/speichern, LLM-Slots, Memory-Rebuild, Restart-Detection, CLAUDE.md Editor

// ── Config ─────────────────────────────────────────────────────────────────
async function loadConfig() {
  try {
    const r = await fetch('/api/config');
    cfg = await r.json();
    renderConfig(cfg);
  } catch(e) { toast('Config-Laden fehlgeschlagen: ' + e.message, 'err'); }
}

function renderConfig(c) {
  // Provider Slots
  const slots = c.llm_providers || [];
  const slotNums = slots.map(s => s.slot);
  document.getElementById('provider-slots').innerHTML = slots.map((s, i) => `
    <div class="provider-slot" id="provslot-${i}" style="padding:0;overflow:hidden;">
      <!-- Collapsible header -->
      <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;cursor:pointer;background:rgba(255,255,255,.02);"
           onclick="toggleLlmSlot(${i})">
        <span id="prov-${i}-chevron" style="font-size:11px;color:var(--muted);transition:transform .2s;">▶</span>
        <span style="font-weight:600;color:var(--accent2);flex:1;">
          Slot ${s.slot} – <span id="prov-${i}-label">${escHtml(s.name||'Slot '+s.slot)}</span>
        </span>
        <span style="font-size:11px;color:var(--muted);" id="prov-${i}-summary">${escHtml(s.type)} · ${escHtml(s.model||'–')}</span>
        <button class="btn btn-danger" style="font-size:11px;padding:2px 8px;" onclick="event.stopPropagation();removeLlmSlot(${i})">✕</button>
      </div>
      <!-- Collapsible body -->
      <div id="prov-${i}-body" style="display:none;padding:12px 14px;border-top:1px solid var(--border);">
        <div class="form-row">
          <div class="form-group">
            <label>Name</label>
            <input type="text" id="prov-${i}-name" value="${escAttr(s.name||'')}"
              oninput="document.getElementById('prov-${i}-label').textContent=this.value||'Slot ${s.slot}';document.getElementById('prov-${i}-summary').textContent=(document.getElementById('prov-${i}-type').value||'?')+' · '+(document.getElementById('prov-${i}-model').value||'–')">
          </div>
          <div class="form-group">
            <label>Typ</label>
            <select id="prov-${i}-type" onchange="document.getElementById('prov-${i}-summary').textContent=this.value+' · '+(document.getElementById('prov-${i}-model').value||'–')">
              ${['anthropic','minimax','ollama','custom'].map(t => `<option value="${t}" ${s.type===t?'selected':''}>${t}</option>`).join('')}
            </select>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>URL <span style="font-size:11px;color:var(--muted);">(leer = Standard des Providers)</span></label>
            <input type="url" id="prov-${i}-url" value="${escAttr(s.url||'')}">
          </div>
          <div class="form-group">
            <label>API Key</label>
            <input type="password" id="prov-${i}-key" value="${escAttr(s.key||'')}">
          </div>
        </div>
        <div class="form-group" style="margin-bottom:10px;">
          <label>Modell</label>
          <div style="display:flex;gap:6px;">
            <input type="text" id="prov-${i}-model" value="${escAttr(s.model||'')}" list="models-${i}" style="flex:1;"
              oninput="document.getElementById('prov-${i}-summary').textContent=(document.getElementById('prov-${i}-type').value||'?')+' · '+(this.value||'–')">
            <datalist id="models-${i}"></datalist>
            <button class="btn btn-secondary" style="font-size:11px;padding:4px 10px;flex-shrink:0;"
              onclick="fetchModels(${i})">Modelle</button>
            <span id="prov-${i}-models-status" style="font-size:11px;color:var(--muted);align-self:center;"></span>
          </div>
        </div>
        <div style="display:flex;gap:10px;align-items:center;">
          <button class="btn btn-secondary" style="font-size:12px;padding:5px 12px;"
            onclick="testProviderConn(${i})">Verbindung testen</button>
          <span id="prov-${i}-test" style="font-size:12px;color:var(--muted);"></span>
        </div>
      </div>
    </div>
  `).join('') + `
    <div style="margin-top:12px;">
      <button class="btn btn-secondary" onclick="addLlmSlot()">+ Slot hinzufügen</button>
    </div>`;

  // Memory
  const m = c.memory || {};
  document.getElementById('mem-window-size').value    = m.window_size    ?? 20;
  document.getElementById('mem-window-minutes').value = m.window_minutes ?? 60;
  document.getElementById('mem-min-messages').value   = m.min_messages   ?? 5;

  // Embedding
  const em = c.embedding || {};
  document.getElementById('embed-model').value = em.model || 'bge-m3';
  document.getElementById('embed-dims').value  = em.dims  ?? 1024;
  document.getElementById('embed-provider').value = em.provider || 'ollama';

  // Log Retention
  const lr = c.log_retention || {};
  document.getElementById('ret-llm-calls').value    = lr['llm-calls']   ?? 30;
  document.getElementById('ret-tool-calls').value   = lr['tool-calls']  ?? 30;
  document.getElementById('ret-memory-ops').value   = lr['memory-ops']  ?? 30;

  // Services
  const sv = c.services || {};
  document.getElementById('svc-ha-url').value    = sv.ha_url    || '';
  document.getElementById('svc-ha-token').value  = sv.ha_token  || '';
  document.getElementById('svc-ollama-url').value = sv.ollama_url || '';
  document.getElementById('svc-qdrant-url').value = sv.qdrant_url || '';

  // MCP
  const mcpEnabled = !!sv.ha_mcp_enabled;
  const mcpEl = document.getElementById('svc-mcp-enabled');
  if (mcpEl) { mcpEl.checked = mcpEnabled; toggleMcpSection(mcpEnabled); }
  const mcpType = document.getElementById('svc-mcp-type');
  if (mcpType) { mcpType.value = sv.ha_mcp_type || 'extended'; updateMcpTypeHints(); }
  const mcpUrl = document.getElementById('svc-mcp-url');
  if (mcpUrl) mcpUrl.value = sv.ha_mcp_url || '';
  const mcpTok = document.getElementById('svc-mcp-token');
  if (mcpTok) mcpTok.value = sv.ha_mcp_token || '';

  // STT / TTS
  const sttEl = document.getElementById('svc-stt-entity');
  const ttsEl = document.getElementById('svc-tts-entity');
  const langEl = document.getElementById('svc-stt-language');
  if (sv.stt_entity && sttEl) {
    // Sicherstellen dass der gespeicherte Wert als Option existiert
    if (![...sttEl.options].some(o => o.value === sv.stt_entity)) {
      sttEl.add(new Option(sv.stt_entity, sv.stt_entity));
    }
    sttEl.value = sv.stt_entity;
  }
  if (sv.tts_entity && ttsEl) {
    if (![...ttsEl.options].some(o => o.value === sv.tts_entity)) {
      ttsEl.add(new Option(sv.tts_entity, sv.tts_entity));
    }
    ttsEl.value = sv.tts_entity;
  }
  if (sv.stt_language && langEl) langEl.value = sv.stt_language;
  const voiceEl = document.getElementById('svc-tts-voice');
  if (voiceEl && sv.tts_voice) voiceEl.value = sv.tts_voice;
  const alsoTextEl = document.getElementById('svc-tts-also-text');
  if (alsoTextEl) alsoTextEl.checked = !!sv.tts_also_text;
  // Entities automatisch laden wenn HA konfiguriert ist
  if (sv.ha_url && sv.ha_token) loadSttTtsEntities();

  // WhatsApp global
  const wa = c.whatsapp || {};
  const waMode = document.getElementById('svc-wa-mode');
  if (waMode) waMode.value = wa.mode || 'separate';
  const waPfx = document.getElementById('svc-wa-prefix');
  if (waPfx) waPfx.value = wa.self_prefix || '!h ';
  const waPfxGrp = document.getElementById('svc-wa-prefix-group');
  if (waPfxGrp) waPfxGrp.style.display = (wa.mode === 'self') ? '' : 'none';
}

// Felder, deren Änderung einen Container-Neustart erfordert
// (werden als Env-Vars beim Container-Start gesetzt)
const RESTART_FIELDS = {
  'services.ollama_url':     'Ollama URL',
  'services.qdrant_url':     'Qdrant URL',
  'services.ha_url':         'Home Assistant URL',
  'services.ha_token':       'Home Assistant Token',
  'services.ha_mcp_enabled': 'HA MCP aktiviert',
  'services.ha_mcp_type':    'HA MCP Typ',
  'services.ha_mcp_url':     'HA MCP URL',
  'services.ha_mcp_token':   'HA MCP Token',
  'memory.window_size':      'Window-Größe',
  'memory.window_minutes':   'Window-Alter (Minuten)',
  'embedding.model':         'Embedding-Modell',
  'embedding.dims':          'Embedding-Dimensionen',
};
// LLM-Slot-Felder (model/url/key) erfordern ebenfalls Neustart
const RESTART_LLM_FIELDS = ['model', 'url', 'key', 'type'];

function _getNestedValue(obj, path) {
  return path.split('.').reduce((o, k) => o && o[k], obj);
}

function _detectRestartChanges(oldCfg, newCfg) {
  const changes = [];

  // Dienste-Felder prüfen
  for (const [path, label] of Object.entries(RESTART_FIELDS)) {
    const oldVal = _getNestedValue(oldCfg, path) ?? '';
    const newVal = _getNestedValue(newCfg, path) ?? '';
    if (String(oldVal) !== String(newVal)) {
      changes.push(label);
    }
  }

  // LLM-Provider-Slots prüfen (Änderungen an model/url/key betreffen Container)
  const oldSlots = oldCfg.llm_providers || [];
  const newSlots = newCfg.llm_providers || [];
  for (let i = 0; i < Math.max(oldSlots.length, newSlots.length); i++) {
    const os = oldSlots[i] || {};
    const ns = newSlots[i] || {};
    for (const f of RESTART_LLM_FIELDS) {
      if ((os[f] ?? '') !== (ns[f] ?? '')) {
        changes.push(`LLM Slot ${ns.slot || os.slot || i+1}: ${f}`);
        break; // nur einmal pro Slot melden
      }
    }
  }

  return changes;
}

async function saveConfig() {
  if (!cfg) return;
  // Lese Slots dynamisch aus DOM (Anzahl kann sich geändert haben)
  const slots = cfg.llm_providers.map((s, i) => ({
    ...s,
    name:  document.getElementById(`prov-${i}-name`)?.value  ?? s.name,
    type:  document.getElementById(`prov-${i}-type`)?.value  ?? s.type,
    url:   document.getElementById(`prov-${i}-url`)?.value   ?? s.url,
    key:   document.getElementById(`prov-${i}-key`)?.value   ?? s.key,
    model: document.getElementById(`prov-${i}-model`)?.value ?? s.model,
  }));

  const uc = {};
  Object.entries(cfg.use_cases || {}).forEach(([key, val]) => {
    uc[key] = {
      ...val,
      primary:  parseInt(document.getElementById(`uc-${key}-primary`)?.value  ?? val.primary),
      fallback: parseInt(document.getElementById(`uc-${key}-fallback`)?.value ?? val.fallback),
    };
  });

  const retLlm   = parseInt(document.getElementById('ret-llm-calls').value)  || null;
  const retTool  = parseInt(document.getElementById('ret-tool-calls').value) || null;
  const retMem   = parseInt(document.getElementById('ret-memory-ops').value) || null;

  const newCfg = {
    ...cfg,
    llm_providers: slots,
    use_cases: uc,
    memory: {
      window_size:    parseInt(document.getElementById('mem-window-size').value),
      window_minutes: parseInt(document.getElementById('mem-window-minutes').value),
      min_messages:   parseInt(document.getElementById('mem-min-messages').value),
    },
    embedding: {
      provider: document.getElementById('embed-provider').value,
      model:    document.getElementById('embed-model').value,
      dims:     parseInt(document.getElementById('embed-dims').value) || 1024,
    },
    log_retention: {
      conversations: null,
      'llm-calls':   retLlm  || 30,
      'tool-calls':  retTool || 30,
      'memory-ops':  retMem  || 30,
    },
    services: {
      ha_url:          document.getElementById('svc-ha-url').value,
      ha_token:        document.getElementById('svc-ha-token').value,
      ha_mcp_enabled:  document.getElementById('svc-mcp-enabled')?.checked ?? false,
      ha_mcp_type:     document.getElementById('svc-mcp-type')?.value || 'extended',
      ha_mcp_url:      document.getElementById('svc-mcp-url')?.value || '',
      ha_mcp_token:    document.getElementById('svc-mcp-token')?.value || '',
      stt_entity:      document.getElementById('svc-stt-entity')?.value || '',
      tts_entity:      document.getElementById('svc-tts-entity')?.value || '',
      stt_language:    document.getElementById('svc-stt-language')?.value || 'de-DE',
      tts_voice:       document.getElementById('svc-tts-voice')?.value || '',
      tts_also_text:   document.getElementById('svc-tts-also-text')?.checked ?? false,
      ollama_url:      document.getElementById('svc-ollama-url').value,
      qdrant_url:      document.getElementById('svc-qdrant-url').value,
    },
    whatsapp: {
      mode:        document.getElementById('svc-wa-mode')?.value || 'separate',
      self_prefix: document.getElementById('svc-wa-prefix')?.value || '!h ',
    },
  };

  const statusEl = document.getElementById('config-save-status');
  try {
    const r = await fetch('/api/config', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(newCfg) });
    if (r.ok) {
      const restartChanges = _detectRestartChanges(cfg, newCfg);
      cfg = newCfg;
      toast('Konfiguration gespeichert', 'ok');
      if (statusEl) { statusEl.style.color = 'var(--green)'; statusEl.textContent = '✓ Gespeichert'; setTimeout(() => { statusEl.textContent = ''; }, 3000); }

      // Neustart anbieten wenn restart-relevante Felder geändert wurden
      if (restartChanges.length > 0) {
        const changedList = restartChanges.join('\n  - ');
        Modal.show({
          title: 'Neustart erforderlich',
          body: `<p class="modal-message">${escHtml('Folgende Änderungen erfordern einen Neustart:\n\n- ' + changedList + '\n\nBeim Neustart wird das Sliding Window ins Memory extrahiert. Der Konversationskontext geht verloren.').replace(/\n/g, '<br>')}</p>`,
          confirmText: 'Jetzt neu starten',
          onConfirm: async () => { await restartAllAgents(); },
          onCancel: () => { toast('Neustart ausstehend – Änderungen erst nach manuellem Neustart wirksam', 'warn'); },
        });
      }
    } else {
      toast('Fehler beim Speichern', 'err');
      if (statusEl) { statusEl.style.color = 'var(--red)'; statusEl.textContent = '✗ Fehler'; }
    }
  } catch(e) {
    toast(e.message, 'err');
    if (statusEl) { statusEl.style.color = 'var(--red)'; statusEl.textContent = '✗ ' + e.message; }
  }
}

async function restartAllAgents() {
  toast('Agenten werden neu gestartet...', 'ok');
  try {
    const r = await fetch('/api/instances/restart-all', { method: 'POST' });
    const data = await r.json();
    if (data.ok) {
      toast('Alle Agenten neu gestartet', 'ok');
    } else {
      const failed = Object.entries(data.results || {})
        .filter(([, v]) => !v.ok)
        .map(([k, v]) => `${k}: ${v.error || 'Fehler'}`)
        .join(', ');
      toast('Teilweise fehlgeschlagen: ' + (failed || 'Unbekannter Fehler'), 'err');
    }
  } catch(e) {
    toast('Neustart fehlgeschlagen: ' + e.message, 'err');
  }
}

// ── CLAUDE.md Editor ───────────────────────────────────────────────────────
function selectClaudeMd(inst) {
  currentMdInst = inst;
  document.querySelectorAll('[id^="mdbtn-"]').forEach(b => b.classList.remove('active'));
  document.getElementById('mdbtn-' + inst)?.classList.add('active');
  loadClaudeMd(inst);
}

async function loadClaudeMd(inst) {
  const ed = document.getElementById('claude-md-editor');
  const st = document.getElementById('claude-md-status');
  st.textContent = 'Wird geladen...';
  try {
    const r = await fetch(`/api/claude-md/${inst}`);
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    ed.value = data.content;
    st.textContent = `${inst}/CLAUDE.md geladen`;
  } catch(e) { st.textContent = '❌ ' + e.message; }
}

async function saveClaudeMd() {
  const content = document.getElementById('claude-md-editor').value;
  const st = document.getElementById('claude-md-status');
  try {
    const r = await fetch(`/api/claude-md/${currentMdInst}`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ content }),
    });
    if (r.ok) { st.textContent = '✓ Gespeichert – sofort aktiv'; toast('CLAUDE.md gespeichert ✓', 'ok'); }
    else       { st.textContent = '❌ Fehler beim Speichern'; toast('Fehler', 'err'); }
  } catch(e) { toast(e.message, 'err'); }
}

// ── Memory Rebuild ─────────────────────────────────────────────────────────
let _rebuildSSE = null;
let _memStats   = [];

function scrollToRebuild() {
  document.getElementById('rebuild-section')?.scrollIntoView({ behavior: 'smooth' });
}

async function loadMemoryStats() {
  const list = document.getElementById('rebuild-instance-list');
  if (!list) return;
  list.innerHTML = '<div style="color:var(--muted);font-size:12px;">Wird geladen…</div>';
  try {
    const r = await fetch('/api/memory-stats');
    _memStats = await r.json();
    list.innerHTML = _memStats.map(m => {
      const scopeStr = Object.entries(m.scopes).map(([k,v]) =>
        `<span class="tag" style="${v===0?'color:var(--red)':''}">${escHtml(k)}: ${v}</span>`
      ).join(' ');
      const logColor = m.log_entries > 0 ? 'var(--text)' : 'var(--muted)';
      const emptyWarn = m.rebuild_suggested
        ? `<span style="color:var(--yellow);font-size:11px;"> ⚠ leer</span>` : '';
      return `
      <label style="display:flex;align-items:flex-start;gap:10px;padding:8px 10px;background:var(--bg);border:1px solid var(--border);border-radius:6px;cursor:pointer;${m.rebuild_suggested?'border-color:var(--yellow);':''}">
        <input type="checkbox" class="rebuild-cb" data-inst="${escAttr(m.instance)}" ${m.rebuild_suggested?'checked':''} style="margin-top:2px;flex-shrink:0;">
        <div style="flex:1;min-width:0;">
          <div style="font-weight:500;font-size:13px;">${escHtml(m.instance)}${emptyWarn}</div>
          <div style="font-size:11px;color:${logColor};margin-top:2px;">
            ${m.log_entries} Log-Einträge (${m.log_days} Tage) · ${scopeStr}
          </div>
        </div>
      </label>`;
    }).join('');
  } catch(e) {
    list.innerHTML = `<div style="color:var(--red);font-size:12px;">Fehler: ${e.message}</div>`;
  }
}

function rebuildSelectEmpty() {
  document.querySelectorAll('.rebuild-cb').forEach(cb => {
    const inst = _memStats.find(m => m.instance === cb.dataset.inst);
    cb.checked = inst?.rebuild_suggested ?? false;
  });
}
function rebuildSelectAll()  { document.querySelectorAll('.rebuild-cb').forEach(cb => cb.checked = true); }
function rebuildSelectNone() { document.querySelectorAll('.rebuild-cb').forEach(cb => cb.checked = false); }

async function startRebuild() {
  const selected = [...document.querySelectorAll('.rebuild-cb:checked')].map(cb => cb.dataset.inst);
  if (!selected.length) { toast('Keine Instanz ausgewählt', 'err'); return; }

  const totalEntries = selected.reduce((sum, inst) => {
    const m = _memStats.find(x => x.instance === inst);
    return sum + (m?.log_entries || 0);
  }, 0);

  Modal.showConfirm(`Memory für ${selected.length} Instanz(en) neu aufbauen?\n${selected.join(', ')}\n\n${totalEntries} Einträge total – kann Minuten bis Stunden dauern.`, async () => {
    const btn    = document.getElementById('rebuild-btn');
    const cancel = document.getElementById('rebuild-cancel-btn');
    const overall = document.getElementById('rebuild-overall-status');
    btn.disabled = true;
    cancel.style.display = '';
    document.getElementById('rebuild-progress-wrap').style.display = '';
    overall.textContent = `0 / ${selected.length} Instanzen`;

    // Instanzen sequenziell abarbeiten
    for (let i = 0; i < selected.length; i++) {
      const inst = selected[i];
      overall.textContent = `${i+1} / ${selected.length}: ${inst}`;
      setRebuildProgress(0, 0, null, `Starte ${inst}…`);
      try {
        const r = await fetch(`/api/rebuild-memory/${inst}`, { method: 'POST' });
        const d = await r.json();
        if (!d.ok) {
          toast(`${inst}: ${d.error}`, 'err');
          continue;
        }
        await new Promise(resolve => startRebuildSSE(inst, resolve));
      } catch(e) {
        toast(`${inst}: ${e.message}`, 'err');
      }
    }

    overall.textContent = `✓ Fertig (${selected.length} Instanzen)`;
    btn.disabled = false;
    cancel.style.display = 'none';
    loadMemoryStats();
  });
}

async function cancelRebuild() {
  if (_rebuildSSE) { _rebuildSSE.close(); _rebuildSSE = null; }
  // Alle laufenden Rebuilds abbrechen
  const selected = [...document.querySelectorAll('.rebuild-cb:checked')].map(cb => cb.dataset.inst);
  for (const inst of selected) {
    await fetch(`/api/rebuild-cancel/${inst}`, { method: 'POST' }).catch(() => {});
  }
  setRebuildProgress(0, 0, null, '■ Abgebrochen');
  document.getElementById('rebuild-btn').disabled = false;
  document.getElementById('rebuild-cancel-btn').style.display = 'none';
}

function startRebuildSSE(inst, onDone) {
  if (_rebuildSSE) _rebuildSSE.close();
  _rebuildSSE = new EventSource(`/api/rebuild-progress/${inst}`);
  _rebuildSSE.onmessage = (e) => {
    const d = JSON.parse(e.data);
    const errSuffix = d.errors > 0 ? ` (${d.errors} Fehler)` : '';
    setRebuildProgress(d.done, d.total, d.eta_s, statusLabel(d.status, d.error) + errSuffix);
    if (['done','error','cancelled'].includes(d.status)) {
      _rebuildSSE.close(); _rebuildSSE = null;
      if (d.status === 'done') {
        const msg = d.errors > 0
          ? `${inst}: Rebuild abgeschlossen – ${d.errors} Einträge fehlgeschlagen (Agent erreichbar?)`
          : `${inst}: Rebuild abgeschlossen ✓`;
        toast(msg, d.errors > 0 ? 'warn' : 'ok');
      }
      if (d.status === 'error') toast(`${inst}: ${d.error}`, 'err');
      if (onDone) onDone();
    }
  };
  _rebuildSSE.onerror = () => { _rebuildSSE?.close(); _rebuildSSE = null; if (onDone) onDone(); };
}

function setRebuildProgress(done, total, eta_s, statusText) {
  const pct = total > 0 ? Math.round(done / total * 100) : 0;
  document.getElementById('rebuild-bar').style.width = pct + '%';
  document.getElementById('rebuild-progress-label').textContent = total > 0
    ? `${done} / ${total} Einträge (${pct}%)`
    : (statusText || '');
  document.getElementById('rebuild-eta').textContent = eta_s != null && eta_s > 0
    ? `noch ca. ${eta_s > 60 ? Math.round(eta_s/60) + ' min' : eta_s + ' s'}` : '';
  document.getElementById('rebuild-status-text').textContent = total > 0 ? statusText : '';
}

function statusLabel(status, error) {
  if (status === 'running')   return '⏳ Läuft…';
  if (status === 'done')      return '✓ Fertig';
  if (status === 'error')     return '❌ Fehler: ' + (error || '');
  if (status === 'cancelled') return '■ Abgebrochen';
  return '';
}

// ── Embedding-Modell Hilfe ─────────────────────────────────────────────────
function updateEmbedDims() {
  const sel = document.getElementById('embed-model');
  const dims = document.getElementById('embed-dims');
  const customRow = document.getElementById('embed-custom-row');
  const presets = { 'bge-m3': 1024, 'nomic-embed-text': 768, 'bge-small-en-v1.5': 384 };
  if (sel.value === '__custom__') {
    customRow.style.display = '';
  } else {
    customRow.style.display = 'none';
    if (presets[sel.value]) dims.value = presets[sel.value];
  }
}

// ── LLM Slot Management ────────────────────────────────────────────────────
function addLlmSlot() {
  if (!cfg) return;
  const maxSlot = cfg.llm_providers.reduce((m, s) => Math.max(m, s.slot), 0);
  cfg.llm_providers.push({ slot: maxSlot + 1, name: `Slot ${maxSlot + 1}`, type: 'custom', url: '', key: '', model: '' });
  renderConfig(cfg);
}

function removeLlmSlot(i) {
  if (!cfg) return;
  if (cfg.llm_providers.length <= 1) { toast('Mindestens ein Slot muss vorhanden sein', 'err'); return; }
  cfg.llm_providers.splice(i, 1);
  // Slot-Nummern neu vergeben
  cfg.llm_providers.forEach((s, idx) => s.slot = idx + 1);
  renderConfig(cfg);
}

async function fetchModels(i) {
  const type = document.getElementById(`prov-${i}-type`)?.value;
  const url  = document.getElementById(`prov-${i}-url`)?.value?.trim();
  const key  = document.getElementById(`prov-${i}-key`)?.value?.trim();
  const st   = document.getElementById(`prov-${i}-models-status`);
  st.textContent = '…';
  try {
    const r = await fetch('/api/fetch-models', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ type, url, key }),
    });
    const d = await r.json();
    if (d.manual || !d.models?.length) {
      st.textContent = d.error ? `⚠ ${d.error.substring(0,60)}` : '⚠ Keine Modelle – manuell eingeben';
      st.style.color = 'var(--yellow)';
      return;
    }
    const datalist = document.getElementById(`models-${i}`);
    datalist.innerHTML = d.models.map(m => `<option value="${escAttr(m)}">`).join('');
    st.textContent = d.fallback ? `✓ ${d.models.length} bekannte Modelle` : `✓ ${d.models.length} Modelle`;
    st.style.color = d.fallback ? 'var(--yellow)' : 'var(--green)';
  } catch(e) {
    st.textContent = '✗ ' + e.message.substring(0,40);
    st.style.color = 'var(--red)';
  }
}

// ── Verbindungstest ────────────────────────────────────────────────────────
async function testSvcConn(type, url, resultId) {
  const el = document.getElementById(resultId);
  if (!url) { el.textContent = '⚠ URL fehlt'; el.style.color = 'var(--yellow)'; return; }
  el.textContent = '…'; el.style.color = 'var(--muted)';
  try {
    const r = await fetch('/api/test-connection', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ type, url }),
    });
    const d = await r.json();
    el.textContent = d.ok ? `✓ ${d.detail}` : `✗ ${d.detail}`;
    el.style.color = d.ok ? 'var(--green)' : 'var(--red)';
  } catch(e) { el.textContent = '✗ ' + e.message; el.style.color = 'var(--red)'; }
}

async function loadSttTtsEntities() {
  const statusEl = document.getElementById('stt-tts-load-status');
  statusEl.textContent = 'Lade...';
  statusEl.style.color = 'var(--muted)';
  try {
    const r = await fetch('/api/ha-stt-tts');
    const d = await r.json();
    if (!d.ok) {
      statusEl.textContent = '✗ ' + (d.error || 'Fehler');
      statusEl.style.color = 'var(--red)';
      return;
    }
    const sttEl = document.getElementById('svc-stt-entity');
    const ttsEl = document.getElementById('svc-tts-entity');
    const prevStt = sttEl.value;
    const prevTts = ttsEl.value;

    // STT Dropdown befüllen
    sttEl.innerHTML = '<option value="">– nicht konfiguriert –</option>';
    d.stt.forEach(e => {
      sttEl.add(new Option(`${e.name} (${e.id})`, e.id));
    });
    if (prevStt) sttEl.value = prevStt;

    // TTS Dropdown befüllen
    ttsEl.innerHTML = '<option value="">– nicht konfiguriert –</option>';
    d.tts.forEach(e => {
      ttsEl.add(new Option(`${e.name} (${e.id})`, e.id));
    });
    if (prevTts) ttsEl.value = prevTts;

    statusEl.textContent = `✓ ${d.stt.length} STT, ${d.tts.length} TTS Entities`;
    statusEl.style.color = 'var(--green)';
  } catch(e) {
    statusEl.textContent = '✗ ' + e.message;
    statusEl.style.color = 'var(--red)';
  }
}

async function testHaConnection() {
  const el = document.getElementById('test-ha-result');
  const ha_url   = document.getElementById('svc-ha-url')?.value?.trim();
  const ha_token = document.getElementById('svc-ha-token')?.value?.trim();
  if (!ha_url)   { el.textContent = '⚠ URL fehlt';   el.style.color = 'var(--yellow)'; return; }
  if (!ha_token) { el.textContent = '⚠ Token fehlt'; el.style.color = 'var(--yellow)'; return; }
  el.textContent = '…'; el.style.color = 'var(--muted)';
  try {
    const r = await fetch('/api/test-ha', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ ha_url, ha_token }),
    });
    const d = await r.json();
    el.textContent = d.ok ? `✓ ${d.detail}` : `✗ ${d.detail}`;
    el.style.color = d.ok ? 'var(--green)' : 'var(--red)';
  } catch(e) { el.textContent = '✗ ' + e.message; el.style.color = 'var(--red)'; }
}

function toggleMcpSection(enabled) {
  const sec = document.getElementById('mcp-section');
  if (sec) sec.style.display = enabled ? 'block' : 'none';
}

function updateMcpTypeHints() {
  const mcpType = document.getElementById('svc-mcp-type')?.value || 'extended';
  const infoBuiltin = document.getElementById('mcp-info-builtin');
  const infoExtended = document.getElementById('mcp-info-extended');
  const urlHint = document.getElementById('svc-mcp-url-hint');
  const autoBtn = document.getElementById('mcp-auto-btn');
  if (infoBuiltin) infoBuiltin.style.display = mcpType === 'builtin' ? '' : 'none';
  if (infoExtended) infoExtended.style.display = mcpType === 'extended' ? '' : 'none';
  if (autoBtn) autoBtn.style.display = mcpType === 'builtin' ? '' : 'none';
  if (urlHint) {
    urlHint.textContent = mcpType === 'builtin' ? t('config_services.mcp_url_hint_builtin') : t('config_services.mcp_url_hint_extended');
    urlHint.style.display = '';
    urlHint.style.color = 'var(--muted)';
  }
}

function autoFillMcpUrl() {
  const haUrl = document.getElementById('svc-ha-url')?.value?.trim().replace(/\/$/, '');
  const mcpUrl = document.getElementById('svc-mcp-url');
  const hint   = document.getElementById('svc-mcp-url-hint');
  if (!haUrl) {
    if (hint) { hint.textContent = t('config_services.ha_url') + ' fehlt'; hint.style.display = ''; hint.style.color = 'var(--yellow)'; }
    return;
  }
  const url = `${haUrl}/mcp_server/sse`;
  if (mcpUrl) mcpUrl.value = url;
  if (hint)   { hint.textContent = `→ ${url}`; hint.style.display = ''; hint.style.color = 'var(--muted)'; }
}

async function testMcpConnection() {
  const el    = document.getElementById('test-mcp-result');
  let mcp_url = document.getElementById('svc-mcp-url')?.value?.trim();
  let token   = document.getElementById('svc-mcp-token')?.value?.trim();
  // Fallback: leerer MCP-Token → HA-Token nehmen
  if (!token) token = document.getElementById('svc-ha-token')?.value?.trim();
  // Leere MCP-URL auto-ausfüllen
  if (!mcp_url) {
    const haUrl = document.getElementById('svc-ha-url')?.value?.trim().replace(/\/$/, '');
    if (haUrl) mcp_url = `${haUrl}/mcp_server/sse`;
  }
  if (!mcp_url) { el.textContent = '⚠ MCP URL fehlt'; el.style.color = 'var(--yellow)'; return; }
  if (!token)   { el.textContent = '⚠ Token fehlt';   el.style.color = 'var(--yellow)'; return; }
  el.textContent = '…'; el.style.color = 'var(--muted)';
  try {
    const r = await fetch('/api/test-ha-mcp', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ mcp_url, token }),
    });
    const d = await r.json();
    el.textContent = d.ok ? `✓ ${d.detail}` : `✗ ${d.detail}`;
    el.style.color = d.ok ? 'var(--green)' : 'var(--red)';
  } catch(e) { el.textContent = '✗ ' + e.message; el.style.color = 'var(--red)'; }
}

function toggleLlmSlot(i) {
  const body    = document.getElementById(`prov-${i}-body`);
  const chevron = document.getElementById(`prov-${i}-chevron`);
  if (!body) return;
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  if (chevron) chevron.style.transform = open ? '' : 'rotate(90deg)';
}

async function testProviderConn(i) {
  const el   = document.getElementById(`prov-${i}-test`);
  const type = document.getElementById(`prov-${i}-type`)?.value || 'http';
  const key  = document.getElementById(`prov-${i}-key`)?.value?.trim() || '';
  let   url  = document.getElementById(`prov-${i}-url`)?.value?.trim() || '';

  // Default-URLs pro Provider-Typ
  const defaults = {
    anthropic: 'https://api.anthropic.com',
    minimax:   'https://api.minimax.io',
    ollama:    '',
  };
  if (!url && defaults[type]) url = defaults[type];

  if (!url) { el.textContent = '⚠ Keine URL konfiguriert'; el.style.color = 'var(--yellow)'; return; }

  el.textContent = '…'; el.style.color = 'var(--muted)';

  // Für Anthropic/MiniMax: Models-Endpunkt testen wenn Key vorhanden
  if ((type === 'anthropic' || type === 'minimax') && key) {
    try {
      const r = await fetch('/api/fetch-models', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ type, url, key }),
      });
      const d = await r.json();
      const count = d.models?.length ?? 0;
      el.textContent = count > 0 ? `✓ Verbunden · ${count} Modelle` : '⚠ Verbunden, aber keine Modelle gefunden';
      el.style.color = count > 0 ? 'var(--green)' : 'var(--yellow)';
    } catch(e) { el.textContent = '✗ ' + e.message; el.style.color = 'var(--red)'; }
    return;
  }

  const connType = type === 'ollama' ? 'ollama' : 'http';
  try {
    const r = await fetch('/api/test-connection', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ type: connType, url }),
    });
    const d = await r.json();
    el.textContent = d.ok ? `✓ ${d.detail}` : `✗ ${d.detail}`;
    el.style.color = d.ok ? 'var(--green)' : 'var(--red)';
  } catch(e) { el.textContent = '✗ ' + e.message; el.style.color = 'var(--red)'; }
}
