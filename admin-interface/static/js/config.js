// config.js – Config laden/speichern, Provider/LLM-Trennung, Memory-Rebuild, Restart-Detection, CLAUDE.md Editor

// ── Config ─────────────────────────────────────────────────────────────────
async function loadConfig() {
  try {
    const r = await fetch('/api/config');
    cfg = await r.json();
    renderConfig(cfg);
  } catch(e) { console.error('loadConfig error:', e); toast(t('config.load_failed') + ': ' + e.message, 'err'); }
}

function _setVal(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val;
}

function renderConfig(c) {
  try { renderProviders(c); } catch(e) { console.error('renderProviders error:', e); }
  try { renderLlms(c); } catch(e) { console.error('renderLlms error:', e); }

  // Memory
  const m = c.memory || {};
  _setVal('mem-window-size',    m.window_size    ?? 20);
  _setVal('mem-window-minutes', m.window_minutes ?? 60);
  _setVal('mem-min-messages',   m.min_messages   ?? 5);

  // Context-Enrichment Toggle
  const ctxEl = document.getElementById('mem-context-enrichment');
  if (ctxEl) ctxEl.checked = !!m.context_enrichment;

  // Memory Extraction LLM Dropdowns
  const memExtEl = document.getElementById('mem-extraction-llm');
  const memExtFbEl = document.getElementById('mem-extraction-llm-fallback');
  if (memExtEl) {
    memExtEl.innerHTML = _llmSelectOpts(m.extraction_llm || '');
  }
  if (memExtFbEl) {
    memExtFbEl.innerHTML = '<option value="">--</option>' + _llmSelectOpts(m.extraction_llm_fallback || '');
  }

  // Embedding
  const em = c.embedding || {};
  try { _renderEmbeddingProviderDropdowns(c, em); } catch(e) { console.error('renderEmbedding error:', e); }
  _setVal('embed-dims',  em.dims  ?? 1024);

  // Log Retention
  const lr = c.log_retention || {};
  _setVal('ret-llm-calls',  lr['llm-calls']   ?? 30);
  _setVal('ret-tool-calls', lr['tool-calls']  ?? 30);
  _setVal('ret-memory-ops', lr['memory-ops']  ?? 30);

  // Services
  const sv = c.services || {};
  _setVal('svc-ha-url',    sv.ha_url    || '');
  _setVal('svc-ha-token',  sv.ha_token  || '');
  _setVal('svc-qdrant-url', sv.qdrant_url || '');

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
  const autoBackupEl = document.getElementById('svc-ha-auto-backup');
  if (autoBackupEl) autoBackupEl.checked = !!sv.ha_auto_backup;

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

// ── Provider Rendering ────────────────────────────────────────────────────────
function renderProviders(c) {
  const providers = c.providers || [];
  document.getElementById('provider-list').innerHTML = providers.map((p, i) => `
    <div class="provider-slot" id="prov-${i}" style="padding:0;overflow:hidden;">
      <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;cursor:pointer;background:rgba(255,255,255,.02);"
           onclick="toggleProviderCard(${i})">
        <span id="prov-${i}-chevron" style="font-size:11px;color:var(--muted);transition:transform .2s;">▶</span>
        <span style="font-weight:600;color:var(--accent2);flex:1;">
          <span id="prov-${i}-label">${escHtml(p.name||p.id)}</span>
          <span style="font-size:11px;color:var(--muted);margin-left:6px;">(${escHtml(p.id)})</span>
        </span>
        <span class="provider-type-badge provider-type-${escAttr(p.type)}">${escHtml(p.type)}${p.auth_method === 'oauth' ? ' · OAuth' : ''}</span>
        <button class="btn btn-danger" style="font-size:11px;padding:2px 8px;" onclick="event.stopPropagation();removeProvider(${i})">✕</button>
      </div>
      <div id="prov-${i}-body" style="display:none;padding:12px 14px;border-top:1px solid var(--border);">
        ${_renderProvBody(p, i)}
      </div>
    </div>
  `).join('') + `
    <div style="margin-top:12px;">
      <button class="btn btn-secondary" onclick="showAddProviderModal()">+ ${t('config_provider.add_provider')}</button>
    </div>`;

  // Auto-check OAuth status for OAuth providers
  setTimeout(() => {
    (cfg?.providers || []).forEach((p, i) => {
      if (p.type === 'anthropic' && p.auth_method === 'oauth') checkProviderOAuth(i);
    });
  }, 100);
}

function _renderProvBody(p, i) {
  switch (p.type) {
    case 'anthropic': return _renderProvBodyAnthropic(p, i);
    case 'ollama':    return _renderProvBodyOllama(p, i);
    case 'minimax':   return _renderProvBodyMinimax(p, i);
    case 'openai':    return _renderProvBodyOpenai(p, i);
    case 'gemini':    return _renderProvBodyGemini(p, i);
    default:          return _renderProvBodyCustom(p, i);
  }
}

function _renderProvBodyAnthropic(p, i) {
  if (p.auth_method === 'oauth') {
    return `
      <div class="form-group" style="margin-bottom:10px;">
        <label>${t('config_provider.name')}</label>
        <input type="text" id="prov-${i}-name" value="${escAttr(p.name||'')}"
          oninput="document.getElementById('prov-${i}-label').textContent=this.value||'${escAttr(p.id)}';if(cfg&&cfg.providers&&cfg.providers[${i}])cfg.providers[${i}].name=this.value;">
      </div>
      <div class="form-group" style="margin-bottom:10px;">
        <label>${t('config_provider.url')} <span style="font-size:11px;color:var(--muted);">(${t('config_provider.url_hint')})</span></label>
        <input type="url" id="prov-${i}-url" value="${escAttr(p.url||'')}">
      </div>
      <div id="prov-${i}-oauth-section" style="margin-bottom:10px;padding:12px;background:var(--card-bg);border-radius:8px;border:1px solid var(--border);">
        <strong>${t('config_provider.oauth_status')}</strong>
        <div class="form-inline" style="margin-top:6px;">
          <span id="prov-${i}-oauth-status" class="form-hint">${t('config_services.auth_checking')}</span>
          <button class="btn btn-sm btn-secondary" onclick="checkProviderOAuth(${i})">${t('config_services.auth_check')}</button>
        </div>
        <div style="margin-top:10px;">
          <button class="btn btn-sm btn-primary" onclick="startProviderOAuthLogin(${i})">${t('config_services.oauth_start_btn')}</button>
          <span id="prov-${i}-oauth-login-status" class="form-hint" style="margin-left:12px;"></span>
        </div>
        <div id="prov-${i}-oauth-login-url" style="margin-top:8px;"></div>
        <div id="prov-${i}-oauth-code-section" style="display:none;margin-top:12px;">
          <label>${t('config_services.oauth_code_label')}</label>
          <div class="form-inline" style="gap:8px;">
            <input type="text" id="prov-${i}-oauth-code-input" style="flex:1;font-family:monospace;"
              placeholder="${t('config_services.oauth_code_placeholder')}">
            <button class="btn btn-sm btn-primary" onclick="completeProviderOAuthLogin(${i})">${t('config_services.oauth_submit_btn')}</button>
          </div>
          <span id="prov-${i}-oauth-code-result" class="form-hint" style="margin-top:6px;display:block;"></span>
        </div>
        <details style="margin-top:12px;">
          <summary class="form-hint" style="cursor:pointer;">${t('config_services.oauth_manual_title')}</summary>
          <div style="margin-top:8px;">
            <textarea id="prov-${i}-oauth-creds" rows="3" style="width:100%;font-family:monospace;font-size:12px;"
              placeholder='{"claudeAiOauth":{"accessToken":"...","refreshToken":"...","expiresAt":...}}'></textarea>
            <button class="btn btn-sm btn-secondary" style="margin-top:6px;"
              onclick="uploadProviderCredentials(${i})">${t('config_services.auth_upload_btn')}</button>
            <span id="prov-${i}-oauth-upload-result" class="form-hint" style="margin-left:12px;"></span>
          </div>
        </details>
      </div>`;
  }
  // API Key auth
  return `
    <div class="form-row">
      <div class="form-group">
        <label>${t('config_provider.name')}</label>
        <input type="text" id="prov-${i}-name" value="${escAttr(p.name||'')}"
          oninput="document.getElementById('prov-${i}-label').textContent=this.value||'${escAttr(p.id)}';if(cfg&&cfg.providers&&cfg.providers[${i}])cfg.providers[${i}].name=this.value;">
      </div>
      <div class="form-group">
        <label>${t('config_provider.api_key')}</label>
        <input type="password" id="prov-${i}-key" value="${escAttr(p.key||'')}">
      </div>
    </div>
    <div class="form-group" style="margin-bottom:10px;">
      <label>${t('config_provider.url')} <span style="font-size:11px;color:var(--muted);">(${t('config_provider.url_hint')})</span></label>
      <input type="url" id="prov-${i}-url" value="${escAttr(p.url||'')}">
    </div>
    <div style="display:flex;gap:10px;align-items:center;">
      <button class="btn btn-secondary" style="font-size:12px;padding:5px 12px;"
        onclick="testProviderConn(${i})">${t('config_provider.test_connection')}</button>
      <span id="prov-${i}-test" style="font-size:12px;color:var(--muted);"></span>
    </div>`;
}

function _renderProvBodyOllama(p, i) {
  return `
    <div class="form-row">
      <div class="form-group">
        <label>${t('config_provider.name')}</label>
        <input type="text" id="prov-${i}-name" value="${escAttr(p.name||'')}"
          oninput="document.getElementById('prov-${i}-label').textContent=this.value||'${escAttr(p.id)}';if(cfg&&cfg.providers&&cfg.providers[${i}])cfg.providers[${i}].name=this.value;">
      </div>
      <div class="form-group">
        <label>${t('config_provider.server_url')} <span style="color:var(--red);">*</span></label>
        <input type="url" id="prov-${i}-url" value="${escAttr(p.url||'')}" required placeholder="http://10.83.1.110:11434">
      </div>
    </div>
    <div style="display:flex;gap:10px;align-items:center;">
      <button class="btn btn-secondary" style="font-size:12px;padding:5px 12px;"
        onclick="testProviderConn(${i})">${t('config_provider.test_connection')}</button>
      <span id="prov-${i}-test" style="font-size:12px;color:var(--muted);"></span>
    </div>`;
}

function _renderProvBodyMinimax(p, i) {
  return `
    <div class="form-row">
      <div class="form-group">
        <label>${t('config_provider.name')}</label>
        <input type="text" id="prov-${i}-name" value="${escAttr(p.name||'')}"
          oninput="document.getElementById('prov-${i}-label').textContent=this.value||'${escAttr(p.id)}';if(cfg&&cfg.providers&&cfg.providers[${i}])cfg.providers[${i}].name=this.value;">
      </div>
      <div class="form-group">
        <label>${t('config_provider.api_key')}</label>
        <input type="password" id="prov-${i}-key" value="${escAttr(p.key||'')}">
      </div>
    </div>
    <div class="form-group" style="margin-bottom:10px;">
      <label>${t('config_provider.url')}</label>
      <input type="url" id="prov-${i}-url" value="${escAttr(p.url||'https://api.minimax.io/anthropic')}">
    </div>
    <div style="display:flex;gap:10px;align-items:center;">
      <button class="btn btn-secondary" style="font-size:12px;padding:5px 12px;"
        onclick="testProviderConn(${i})">${t('config_provider.test_connection')}</button>
      <span id="prov-${i}-test" style="font-size:12px;color:var(--muted);"></span>
    </div>`;
}

function _renderProvBodyOpenai(p, i) {
  return `
    <div class="form-row">
      <div class="form-group">
        <label>${t('config_provider.name')}</label>
        <input type="text" id="prov-${i}-name" value="${escAttr(p.name||'')}"
          oninput="document.getElementById('prov-${i}-label').textContent=this.value||'${escAttr(p.id)}';if(cfg&&cfg.providers&&cfg.providers[${i}])cfg.providers[${i}].name=this.value;">
      </div>
      <div class="form-group">
        <label>${t('config_provider.api_key')}</label>
        <input type="password" id="prov-${i}-key" value="${escAttr(p.key||'')}">
      </div>
    </div>
    <div class="form-group" style="margin-bottom:10px;">
      <label>${t('config_provider.url')} <span style="font-size:11px;color:var(--muted);">(${t('config_provider.url_hint_openai')})</span></label>
      <input type="url" id="prov-${i}-url" value="${escAttr(p.url||'')}">
    </div>
    <div style="display:flex;gap:10px;align-items:center;">
      <button class="btn btn-secondary" style="font-size:12px;padding:5px 12px;"
        onclick="testProviderConn(${i})">${t('config_provider.test_connection')}</button>
      <span id="prov-${i}-test" style="font-size:12px;color:var(--muted);"></span>
    </div>`;
}

function _renderProvBodyGemini(p, i) {
  return `
    <div class="form-row">
      <div class="form-group">
        <label>${t('config_provider.name')}</label>
        <input type="text" id="prov-${i}-name" value="${escAttr(p.name||'')}"
          oninput="document.getElementById('prov-${i}-label').textContent=this.value||'${escAttr(p.id)}';if(cfg&&cfg.providers&&cfg.providers[${i}])cfg.providers[${i}].name=this.value;">
      </div>
      <div class="form-group">
        <label>${t('config_provider.api_key')}</label>
        <input type="password" id="prov-${i}-key" value="${escAttr(p.key||'')}">
      </div>
    </div>
    <div style="display:flex;gap:10px;align-items:center;">
      <button class="btn btn-secondary" style="font-size:12px;padding:5px 12px;"
        onclick="testProviderConn(${i})">${t('config_provider.test_connection')}</button>
      <span id="prov-${i}-test" style="font-size:12px;color:var(--muted);"></span>
    </div>`;
}

function _renderProvBodyCustom(p, i) {
  return `
    <div class="form-row">
      <div class="form-group">
        <label>${t('config_provider.name')}</label>
        <input type="text" id="prov-${i}-name" value="${escAttr(p.name||'')}"
          oninput="document.getElementById('prov-${i}-label').textContent=this.value||'${escAttr(p.id)}';if(cfg&&cfg.providers&&cfg.providers[${i}])cfg.providers[${i}].name=this.value;">
      </div>
      <div class="form-group">
        <label>${t('config_provider.api_key')}</label>
        <input type="password" id="prov-${i}-key" value="${escAttr(p.key||'')}">
      </div>
    </div>
    <div class="form-group" style="margin-bottom:10px;">
      <label>${t('config_provider.url')}</label>
      <input type="url" id="prov-${i}-url" value="${escAttr(p.url||'')}">
    </div>
    <div style="display:flex;gap:10px;align-items:center;">
      <button class="btn btn-secondary" style="font-size:12px;padding:5px 12px;"
        onclick="testProviderConn(${i})">${t('config_provider.test_connection')}</button>
      <span id="prov-${i}-test" style="font-size:12px;color:var(--muted);"></span>
    </div>`;
}

function toggleProviderCard(i) {
  const body    = document.getElementById(`prov-${i}-body`);
  const chevron = document.getElementById(`prov-${i}-chevron`);
  if (!body) return;
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  if (chevron) chevron.style.transform = open ? '' : 'rotate(90deg)';
}

function showAddProviderModal() {
  if (!cfg) return;
  const types = [
    { type: 'anthropic', name: 'Anthropic', desc: t('config_provider.type_anthropic_desc') },
    { type: 'ollama',    name: 'Ollama',    desc: t('config_provider.type_ollama_desc') },
    { type: 'minimax',   name: 'MiniMax',   desc: t('config_provider.type_minimax_desc') },
    { type: 'openai',    name: 'OpenAI',    desc: t('config_provider.type_openai_desc') },
    { type: 'gemini',    name: 'Gemini',    desc: t('config_provider.type_gemini_desc') },
    { type: 'custom',    name: 'Custom',    desc: t('config_provider.type_custom_desc') },
  ];
  const grid = types.map(tp => `
    <div class="provider-type-card" onclick="onProviderTypeSelected('${tp.type}')">
      <div class="provider-type-card-name">${tp.name}</div>
      <div class="provider-type-card-desc">${tp.desc}</div>
    </div>`).join('');

  Modal.show({
    title: t('config_provider.select_type'),
    body: `<div class="provider-type-grid">${grid}</div>
      <div id="provider-auth-step" style="display:none;margin-top:16px;">
        <strong>${t('config_provider.auth_method')}</strong>
        <div class="provider-type-grid" style="margin-top:10px;">
          <div class="provider-type-card" onclick="addProviderWithType('anthropic', 'api_key')">
            <div class="provider-type-card-name">${t('config_provider.auth_method_apikey')}</div>
            <div class="provider-type-card-desc">${t('config_provider.auth_method_apikey_desc')}</div>
          </div>
          <div class="provider-type-card" onclick="addProviderWithType('anthropic', 'oauth')">
            <div class="provider-type-card-name">${t('config_provider.auth_method_oauth')}</div>
            <div class="provider-type-card-desc">${t('config_provider.auth_method_oauth_desc')}</div>
          </div>
        </div>
      </div>`,
    hideConfirm: true,
    cancelText: t('common.cancel'),
  });
}

function onProviderTypeSelected(type) {
  if (type === 'anthropic') {
    // Show auth method step
    document.querySelectorAll('.provider-type-card').forEach(c => c.style.opacity = '0.3');
    document.getElementById('provider-auth-step').style.display = '';
    return;
  }
  addProviderWithType(type);
  Modal.close();
}

function addProviderWithType(type, authMethod) {
  if (!cfg) return;
  const existing = (cfg.providers || []).map(p => p.id);
  let id = `${type}-1`;
  let n = 1;
  while (existing.includes(id)) { n++; id = `${type}-${n}`; }
  const names = { anthropic: 'Anthropic', ollama: 'Ollama', minimax: 'MiniMax', openai: 'OpenAI', gemini: 'Gemini', custom: 'Custom' };
  const p = { id, name: `${names[type] || type} ${n > 1 ? n : ''}`.trim(), type };
  if (type === 'anthropic') {
    p.auth_method = authMethod || 'api_key';
    if (authMethod === 'oauth') p.oauth_dir = `/data/claude-auth/${id}`;
    else p.key = '';
    p.url = '';
  } else if (type === 'ollama') {
    p.url = '';
  } else if (type === 'minimax') {
    p.key = ''; p.url = 'https://api.minimax.io/anthropic';
  } else if (type === 'openai') {
    p.key = ''; p.url = '';
  } else if (type === 'gemini') {
    p.key = '';
  } else {
    p.url = ''; p.key = '';
  }
  cfg.providers = cfg.providers || [];
  cfg.providers.push(p);
  Modal.close();
  renderProviders(cfg);
  // Auto-expand the new card
  setTimeout(() => toggleProviderCard(cfg.providers.length - 1), 50);
}

async function removeProvider(i) {
  if (!cfg || !cfg.providers) return;
  if (cfg.providers.length <= 1) { toast(t('config_provider.min_one_provider'), 'err'); return; }
  const prov = cfg.providers[i];
  // Referenz-Check
  try {
    const r = await fetch(`/api/references/provider/${encodeURIComponent(prov.id)}`);
    const d = await r.json();
    if (d.count > 0) {
      toast(t('config_provider.delete_blocked') + ': ' + d.refs.join(', '), 'err');
      return;
    }
  } catch(e) { /* ignore, allow delete */ }
  cfg.providers.splice(i, 1);
  renderProviders(cfg);
}

// ── LLM Rendering ───────────────────────────────────────────────────────────
function renderLlms(c) {
  const llms = c.llms || [];
  const providers = c.providers || [];
  document.getElementById('llm-list').innerHTML = llms.map((l, i) => `
    <div class="provider-slot" id="llm-${i}" style="padding:0;overflow:hidden;">
      <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;cursor:pointer;background:rgba(255,255,255,.02);"
           onclick="toggleLlmCard(${i})">
        <span id="llm-${i}-chevron" style="font-size:11px;color:var(--muted);transition:transform .2s;">▶</span>
        <span style="font-weight:600;color:var(--accent2);flex:1;">
          <span id="llm-${i}-label">${escHtml(l.name||l.id)}</span>
          <span style="font-size:11px;color:var(--muted);margin-left:6px;">(${escHtml(l.id)})</span>
        </span>
        <span style="font-size:11px;color:var(--muted);" id="llm-${i}-summary">${escHtml(_providerLabel(l.provider_id, providers))} · ${escHtml(l.model||'\u2013')}</span>
        <button class="btn btn-danger" style="font-size:11px;padding:2px 8px;" onclick="event.stopPropagation();removeLlm(${i})">\u2715</button>
      </div>
      <div id="llm-${i}-body" style="display:none;padding:12px 14px;border-top:1px solid var(--border);">
        <div class="form-row">
          <div class="form-group">
            <label>${t('config_llm.name')}</label>
            <input type="text" id="llm-${i}-name" value="${escAttr(l.name||'')}"
              oninput="document.getElementById('llm-${i}-label').textContent=this.value||'${escAttr(l.id)}'">
          </div>
          <div class="form-group">
            <label>${t('config_llm.provider')}</label>
            <select id="llm-${i}-provider" onchange="onLlmProviderChange(${i})">
              ${providers.map(p => `<option value="${escAttr(p.id)}" ${l.provider_id===p.id?'selected':''}>${escHtml(p.name)} (${escHtml(p.type)})</option>`).join('')}
            </select>
          </div>
        </div>
        <div class="form-group" style="margin-bottom:10px;">
          <label>${t('config_llm.model')}</label>
          <div style="display:flex;gap:6px;">
            <input type="text" id="llm-${i}-model" value="${escAttr(l.model||'')}" list="llmmodels-${i}" style="flex:1;"
              oninput="document.getElementById('llm-${i}-summary').textContent=_providerLabel(document.getElementById('llm-${i}-provider').value, cfg.providers||[])+' · '+(this.value||'\u2013')">
            <datalist id="llmmodels-${i}"></datalist>
            <button class="btn btn-secondary" style="font-size:11px;padding:4px 10px;flex-shrink:0;"
              onclick="fetchModelsForLlm(${i})">${t('config_llm.fetch_models')}</button>
            <span id="llm-${i}-models-status" style="font-size:11px;color:var(--muted);align-self:center;"></span>
          </div>
        </div>
      </div>
    </div>
  `).join('') + `
    <div style="margin-top:12px;">
      <button class="btn btn-secondary" onclick="addLlm()">+ ${t('config_llm.add_llm')}</button>
    </div>`;
}

function _providerLabel(providerId, providers) {
  const p = (providers || []).find(x => x.id === providerId);
  return p ? p.name : providerId || '?';
}

function toggleLlmCard(i) {
  const body    = document.getElementById(`llm-${i}-body`);
  const chevron = document.getElementById(`llm-${i}-chevron`);
  if (!body) return;
  const open = body.style.display !== 'none';
  body.style.display = open ? 'none' : 'block';
  if (chevron) chevron.style.transform = open ? '' : 'rotate(90deg)';
}

function addLlm() {
  if (!cfg) return;
  const existing = (cfg.llms || []).map(l => l.id);
  let id = 'llm-1';
  let n = 1;
  while (existing.includes(id)) { n++; id = `llm-${n}`; }
  const defaultProvider = (cfg.providers || [])[0]?.id || '';
  cfg.llms = cfg.llms || [];
  cfg.llms.push({ id, name: `LLM ${n}`, provider_id: defaultProvider, model: '' });
  renderLlms(cfg);
}

async function removeLlm(i) {
  if (!cfg || !cfg.llms) return;
  if (cfg.llms.length <= 1) { toast(t('config_llm.min_one_llm'), 'err'); return; }
  const llm = cfg.llms[i];
  // Referenz-Check
  try {
    const r = await fetch(`/api/references/llm/${encodeURIComponent(llm.id)}`);
    const d = await r.json();
    if (d.count > 0) {
      Modal.show({
        title: t('common.references_warning'),
        body: `<p class="modal-message">${escHtml(d.refs.join(', '))}</p><p>${t('common.delete_confirm_refs')}</p>`,
        confirmText: t('users.delete'),
        danger: true,
        onConfirm: () => { cfg.llms.splice(i, 1); renderLlms(cfg); },
      });
      return;
    }
  } catch(e) { /* ignore */ }
  cfg.llms.splice(i, 1);
  renderLlms(cfg);
}

function onLlmProviderChange(i) {
  const newProv = document.getElementById(`llm-${i}-provider`)?.value || '';
  const summary = document.getElementById(`llm-${i}-summary`);
  const model   = document.getElementById(`llm-${i}-model`)?.value || '';
  if (summary) summary.textContent = _providerLabel(newProv, cfg.providers || []) + ' \u00b7 ' + (model || '\u2013');
}

async function fetchModelsForLlm(i) {
  if (!cfg) return;
  const providerId = document.getElementById(`llm-${i}-provider`)?.value;
  const prov = (cfg.providers || []).find(p => p.id === providerId);
  if (!prov) return;
  const st = document.getElementById(`llm-${i}-models-status`);
  st.textContent = '\u2026';
  try {
    const r = await fetch('/api/fetch-models', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ type: prov.type, url: prov.url, key: prov.key }),
    });
    const d = await r.json();
    if (d.manual || !d.models?.length) {
      st.textContent = d.error ? '\u26a0 ' + d.error.substring(0,60) : '\u26a0 ' + t('config_llm.no_models_manual');
      st.style.color = 'var(--yellow)';
      return;
    }
    const datalist = document.getElementById(`llmmodels-${i}`);
    datalist.innerHTML = d.models.map(m => `<option value="${escAttr(m)}">`).join('');
    st.textContent = d.fallback ? '\u2713 ' + d.models.length + ' ' + t('config_llm.known_models') : '\u2713 ' + d.models.length + ' ' + t('config_llm.models_label');
    st.style.color = d.fallback ? 'var(--yellow)' : 'var(--green)';
  } catch(e) {
    st.textContent = '\u2717 ' + e.message.substring(0,40);
    st.style.color = 'var(--red)';
  }
}

// ── LLM Select Options (für User-Dropdowns + Memory) ───────────────────────
function _llmSelectOpts(selectedId) {
  if (!cfg || !cfg.llms) return '<option value="">--</option>';
  return cfg.llms.map(l => {
    const prov = (cfg.providers || []).find(p => p.id === l.provider_id);
    const label = `${l.name} (${prov ? prov.name : l.provider_id} · ${l.model || '\u2013'})`;
    return `<option value="${escAttr(l.id)}" ${l.id === selectedId ? 'selected' : ''}>${escHtml(label)}</option>`;
  }).join('');
}

// ── Embedding Provider Dropdowns ────────────────────────────────────────────
function _renderEmbeddingProviderDropdowns(c, em) {
  const providers = c.providers || [];
  const embedEl = document.getElementById('embed-provider');
  const fbEl    = document.getElementById('embed-fallback-provider');
  if (!embedEl) return;

  const opts = providers.map(p =>
    `<option value="${escAttr(p.id)}" ${p.id === em.provider_id ? 'selected' : ''}>${escHtml(p.name)} (${escHtml(p.type)})</option>`
  ).join('');
  embedEl.innerHTML = opts;

  if (fbEl) {
    fbEl.innerHTML = '<option value="">--</option>' + providers.map(p =>
      `<option value="${escAttr(p.id)}" ${p.id === em.fallback_provider_id ? 'selected' : ''}>${escHtml(p.name)} (${escHtml(p.type)})</option>`
    ).join('');
  }

  const selectedModel = em.model || 'bge-m3';
  // Bei Provider-Wechsel Modelle neu laden
  embedEl.addEventListener('change', () => _loadEmbeddingModels(c, selectedModel));
  // Initial Modelle laden
  _loadEmbeddingModels(c, selectedModel);
}

// Bekannte Embedding-Modell Dimensionen (Fallback wenn API keine liefert)
const _EMBED_DIMS = {
  'bge-m3': 1024, 'bge-m3:latest': 1024,
  'nomic-embed-text': 768, 'nomic-embed-text:latest': 768,
  'all-minilm': 384, 'all-minilm:latest': 384,
  'bge-small-en-v1.5': 384, 'bge-small-en-v1.5:latest': 384,
  'mxbai-embed-large': 1024, 'mxbai-embed-large:latest': 1024,
  'snowflake-arctic-embed': 1024, 'snowflake-arctic-embed:latest': 1024,
  'text-embedding-3-small': 1536, 'text-embedding-3-large': 3072,
  'text-embedding-ada-002': 1536,
  'models/text-embedding-004': 768,
};

async function _loadEmbeddingModels(c, selectedModel) {
  const provId = document.getElementById('embed-provider')?.value;
  const modelEl = document.getElementById('embed-model');
  const statusEl = document.getElementById('embed-model-status');
  if (!modelEl) return;

  const prov = (c.providers || []).find(p => p.id === provId);
  if (!prov) {
    modelEl.innerHTML = '<option value="">–</option>';
    if (statusEl) statusEl.textContent = '';
    return;
  }

  if (statusEl) statusEl.textContent = t('config_memory.loading_models');
  try {
    const r = await fetch('/api/fetch-embedding-models', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ type: prov.type, url: prov.url, key: prov.key }),
    });
    const d = await r.json();
    const models = d.models || [];

    const embedCount = models.filter(m => m.is_embed !== false).length;
    modelEl.innerHTML = models.map(m => {
      const id = m.id || m;
      const dims = m.dims || _EMBED_DIMS[id] || _EMBED_DIMS[id.split(':')[0]] || 0;
      const label = dims ? `${id} (${dims} dims)` : id;
      const sel = id === selectedModel ? ' selected' : '';
      return `<option value="${escAttr(id)}"${sel}>${escHtml(label)}</option>`;
    }).join('');

    // Falls gespeichertes Modell nicht in der Liste: als erste Option hinzufuegen
    if (selectedModel && ![...modelEl.options].some(o => o.value === selectedModel)) {
      const dims = _EMBED_DIMS[selectedModel] || _EMBED_DIMS[selectedModel.split(':')[0]];
      const label = dims ? `${selectedModel} (${dims} dims)` : selectedModel;
      modelEl.insertAdjacentHTML('afterbegin',
        `<option value="${escAttr(selectedModel)}" selected>${escHtml(label)} *</option>`);
    }

    if (statusEl) {
      statusEl.textContent = embedCount > 0
        ? embedCount + ' ' + t('config_memory.embedding_models_found')
        : models.length + ' ' + t('config_memory.models_available');
    }
    updateEmbedDims();
  } catch(e) {
    modelEl.innerHTML = selectedModel
      ? `<option value="${escAttr(selectedModel)}" selected>${escHtml(selectedModel)}</option>`
      : '<option value="">–</option>';
    if (statusEl) statusEl.textContent = t('config_memory.models_load_error');
  }
}

// ── Restart Detection ───────────────────────────────────────────────────────
const RESTART_FIELDS = {
  'services.qdrant_url':     'Qdrant URL',
  'services.ha_url':         'Home Assistant URL',
  'services.ha_token':       'Home Assistant Token',
  'services.ha_mcp_enabled': 'HA MCP',
  'services.ha_mcp_type':    'HA MCP Type',
  'services.ha_mcp_url':     'HA MCP URL',
  'services.ha_mcp_token':   'HA MCP Token',
  'memory.window_size':      'Window Size',
  'memory.window_minutes':   'Window Age',
  'memory.extraction_llm':   'Extraction LLM',
  'embedding.model':         'Embedding Model',
  'embedding.dims':          'Embedding Dims',
  'embedding.provider_id':   'Embedding Provider',
};

function _getNestedValue(obj, path) {
  return path.split('.').reduce((o, k) => o && o[k], obj);
}

function _detectRestartChanges(oldCfg, newCfg) {
  const changes = [];

  for (const [path, label] of Object.entries(RESTART_FIELDS)) {
    const oldVal = _getNestedValue(oldCfg, path) ?? '';
    const newVal = _getNestedValue(newCfg, path) ?? '';
    if (String(oldVal) !== String(newVal)) {
      changes.push(label);
    }
  }

  // Provider-Änderungen prüfen (key/url/type betreffen Container)
  const oldProvs = oldCfg.providers || [];
  const newProvs = newCfg.providers || [];
  for (const np of newProvs) {
    const op = oldProvs.find(p => p.id === np.id);
    if (!op) { changes.push(`Provider: ${np.name} (neu)`); continue; }
    for (const f of ['key', 'url', 'type']) {
      if ((op[f] ?? '') !== (np[f] ?? '')) {
        changes.push(`Provider ${np.name}: ${f}`);
        break;
      }
    }
  }

  // LLM-Änderungen prüfen (model/provider_id betreffen Container)
  const oldLlms = oldCfg.llms || [];
  const newLlms = newCfg.llms || [];
  for (const nl of newLlms) {
    const ol = oldLlms.find(l => l.id === nl.id);
    if (!ol) { changes.push(`LLM: ${nl.name} (neu)`); continue; }
    for (const f of ['model', 'provider_id']) {
      if ((ol[f] ?? '') !== (nl[f] ?? '')) {
        changes.push(`LLM ${nl.name}: ${f}`);
        break;
      }
    }
  }

  return changes;
}

// ── Save Config ─────────────────────────────────────────────────────────────
async function saveConfig() {
  if (!cfg) return;

  // Provider aus DOM lesen
  const providers = (cfg.providers || []).map((p, i) => ({
    ...p,
    name: document.getElementById(`prov-${i}-name`)?.value ?? p.name,
    url:  document.getElementById(`prov-${i}-url`)?.value  ?? p.url,
    key:  document.getElementById(`prov-${i}-key`)?.value  ?? p.key,
  }));

  // LLMs aus DOM lesen
  const llms = (cfg.llms || []).map((l, i) => ({
    ...l,
    name:        document.getElementById(`llm-${i}-name`)?.value     ?? l.name,
    provider_id: document.getElementById(`llm-${i}-provider`)?.value ?? l.provider_id,
    model:       document.getElementById(`llm-${i}-model`)?.value    ?? l.model,
  }));

  const retLlm   = parseInt(document.getElementById('ret-llm-calls').value)  || null;
  const retTool  = parseInt(document.getElementById('ret-tool-calls').value) || null;
  const retMem   = parseInt(document.getElementById('ret-memory-ops').value) || null;

  const newCfg = {
    ...cfg,
    providers,
    llms,
    memory: {
      extraction_llm:          document.getElementById('mem-extraction-llm')?.value || '',
      extraction_llm_fallback: document.getElementById('mem-extraction-llm-fallback')?.value || '',
      context_enrichment:      document.getElementById('mem-context-enrichment')?.checked ?? false,
      window_size:    parseInt(document.getElementById('mem-window-size').value),
      window_minutes: parseInt(document.getElementById('mem-window-minutes').value),
      min_messages:   parseInt(document.getElementById('mem-min-messages').value),
    },
    embedding: {
      provider_id:          document.getElementById('embed-provider')?.value || '',
      model:                document.getElementById('embed-model')?.value || 'bge-m3',
      dims:                 parseInt(document.getElementById('embed-dims').value) || 1024,
      fallback_provider_id: document.getElementById('embed-fallback-provider')?.value || '',
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
      ha_auto_backup:  document.getElementById('svc-ha-auto-backup')?.checked ?? false,
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
      toast(t('config.config_saved'), 'ok');
      if (statusEl) { statusEl.style.color = 'var(--green)'; statusEl.textContent = '\u2713 ' + t('config.saved'); setTimeout(() => { statusEl.textContent = ''; }, 3000); }

      if (restartChanges.length > 0) {
        const changedList = restartChanges.join('\n  - ');
        Modal.show({
          title: t('config.restart_title'),
          body: `<p class="modal-message">${escHtml(t('config.restart_changes_intro') + '\n\n- ' + changedList + '\n\n' + t('config.restart_changes_warning')).replace(/\n/g, '<br>')}</p>`,
          confirmText: t('config.restart_now'),
          onConfirm: async () => { await restartAllAgents(); },
          onCancel: () => { toast(t('config.restart_pending'), 'warn'); },
        });
      }
    } else {
      toast(t('config.save_error'), 'err');
      if (statusEl) { statusEl.style.color = 'var(--red)'; statusEl.textContent = '\u2717 ' + t('config.error_label'); }
    }
  } catch(e) {
    toast(e.message, 'err');
    if (statusEl) { statusEl.style.color = 'var(--red)'; statusEl.textContent = '\u2717 ' + e.message; }
  }
}

async function restartAllAgents() {
  toast(t('config.restarting'), 'ok');
  try {
    const r = await fetch('/api/instances/restart-all', { method: 'POST' });
    const data = await r.json();
    if (data.ok) {
      toast(t('config.restart_success'), 'ok');
    } else {
      const failed = Object.entries(data.results || {})
        .filter(([, v]) => !v.ok)
        .map(([k, v]) => `${k}: ${v.error || t('common.error')}`)
        .join(', ');
      toast(t('config.restart_partial') + ': ' + (failed || t('chat.unknown_error')), 'err');
    }
  } catch(e) {
    toast(t('config.restart_failed') + ': ' + e.message, 'err');
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
  st.textContent = t('common.loading');
  try {
    const r = await fetch(`/api/claude-md/${inst}`);
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    ed.value = data.content;
    st.textContent = t('config_claude_md.loaded', {instance: inst});
  } catch(e) { st.textContent = '\u274c ' + e.message; }
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
    if (r.ok) { st.textContent = '\u2713 ' + t('config_claude_md.saved'); toast(t('config_claude_md.saved_toast'), 'ok'); }
    else       { st.textContent = '\u274c ' + t('config_claude_md.save_error'); toast(t('common.error'), 'err'); }
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
  list.innerHTML = '<div style="color:var(--muted);font-size:12px;">' + t('common.loading') + '</div>';
  try {
    const r = await fetch('/api/memory-stats');
    _memStats = await r.json();
    list.innerHTML = _memStats.map(m => {
      const scopeStr = Object.entries(m.scopes).map(([k,v]) =>
        `<span class="tag" style="${v===0?'color:var(--red)':''}">${escHtml(k)}: ${v}</span>`
      ).join(' ');
      const logColor = m.log_entries > 0 ? 'var(--text)' : 'var(--muted)';
      const emptyWarn = m.rebuild_suggested
        ? `<span style="color:var(--yellow);font-size:11px;"> \u26a0 ${t('config_memory.empty_warning')}</span>` : '';
      return `
      <label style="display:flex;align-items:flex-start;gap:10px;padding:8px 10px;background:var(--bg);border:1px solid var(--border);border-radius:6px;cursor:pointer;${m.rebuild_suggested?'border-color:var(--yellow);':''}">
        <input type="checkbox" class="rebuild-cb" data-inst="${escAttr(m.instance)}" ${m.rebuild_suggested?'checked':''} style="margin-top:2px;flex-shrink:0;">
        <div style="flex:1;min-width:0;">
          <div style="font-weight:500;font-size:13px;">${escHtml(m.instance)}${emptyWarn}</div>
          <div style="font-size:11px;color:${logColor};margin-top:2px;">
            ${m.log_entries} ${t('config_memory.log_entries')} (${m.log_days} ${t('config_memory.days')}) \u00b7 ${scopeStr}
          </div>
        </div>
      </label>`;
    }).join('');
  } catch(e) {
    list.innerHTML = `<div style="color:var(--red);font-size:12px;">${t('config_memory.error_label')}: ${e.message}</div>`;
  }
  checkResumeInfo();
}

function rebuildSelectEmpty() {
  document.querySelectorAll('.rebuild-cb').forEach(cb => {
    const inst = _memStats.find(m => m.instance === cb.dataset.inst);
    cb.checked = inst?.rebuild_suggested ?? false;
  });
}
function rebuildSelectAll()  { document.querySelectorAll('.rebuild-cb').forEach(cb => cb.checked = true); }
function rebuildSelectNone() { document.querySelectorAll('.rebuild-cb').forEach(cb => cb.checked = false); }

async function startRebuild(resumeMode = false) {
  const selected = [...document.querySelectorAll('.rebuild-cb:checked')].map(cb => cb.dataset.inst);
  if (!selected.length) { toast(t('config_memory.rebuild_no_instance'), 'err'); return; }

  const skipTrivial = document.getElementById('rebuild-skip-trivial')?.checked ?? true;
  const delayMs = parseInt(document.getElementById('rebuild-delay')?.value || '0', 10);
  const scanInfo = document.getElementById('rebuild-scan-info');

  // Pre-Scan: Logs analysieren und Kosten schätzen
  scanInfo.style.display = '';
  scanInfo.innerHTML = t('config_memory.rebuild_scanning');

  let totalRelevant = 0, totalFiltered = 0, totalRaw = 0, estTokens = 0;
  let isApi = false, providerType = '';
  for (const inst of selected) {
    try {
      const r = await fetch(`/api/rebuild-scan/${inst}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({skip_trivial: skipTrivial}),
      });
      const d = await r.json();
      totalRelevant += d.total_relevant;
      totalFiltered += d.total_filtered;
      totalRaw += d.total_raw;
      estTokens += d.est_tokens;
      if (d.is_api) { isApi = true; providerType = d.provider_type; }
    } catch(e) {
      toast(`Scan ${inst}: ${e.message}`, 'err');
    }
  }

  let scanHtml = t('config_memory.rebuild_scan_result', {
    relevant: totalRelevant, total: totalRaw, filtered: totalFiltered
  }) + '<br>' + t('config_memory.rebuild_scan_tokens', {tokens: estTokens.toLocaleString()});
  if (isApi) {
    scanHtml += '<br><strong style="color:var(--yellow);">' +
      t('config_memory.rebuild_scan_api_warn', {type: providerType}) + '</strong>';
  }
  scanInfo.innerHTML = scanHtml;

  const confirmMsg = t('config_memory.rebuild_confirm_filtered', {
    count: selected.length, instances: selected.join(', '),
    relevant: totalRelevant, filtered: totalFiltered,
    tokens: estTokens.toLocaleString(),
  });

  Modal.showConfirm(confirmMsg, async () => {
    const btn    = document.getElementById('rebuild-btn');
    const cancel = document.getElementById('rebuild-cancel-btn');
    const overall = document.getElementById('rebuild-overall-status');
    btn.disabled = true;
    cancel.style.display = '';
    document.getElementById('rebuild-progress-wrap').style.display = '';
    overall.textContent = '0 / ' + selected.length + ' ' + t('config_memory.rebuild_instances_label');

    for (let i = 0; i < selected.length; i++) {
      const inst = selected[i];
      overall.textContent = (i+1) + ' / ' + selected.length + ': ' + inst;
      setRebuildProgress(0, 0, null, t('config_memory.rebuild_starting') + ' ' + inst + '\u2026');
      try {
        const r = await fetch(`/api/rebuild-memory/${inst}`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            skip_trivial: skipTrivial,
            delay_ms: delayMs,
            resume: resumeMode,
          }),
        });
        const d = await r.json();
        if (!d.ok) {
          toast(`${inst}: ${d.error}`, 'err');
          continue;
        }
        if (d.skipped_trivial > 0) {
          toast(`${inst}: ${t('config_memory.rebuild_scan_result', {relevant: d.total - d.skipped_trivial, total: d.total + d.skipped_trivial, filtered: d.skipped_trivial})}`, 'info');
        }
        await new Promise(resolve => startRebuildSSE(inst, resolve));
      } catch(e) {
        toast(`${inst}: ${e.message}`, 'err');
      }
    }

    overall.textContent = '\u2713 ' + t('config_memory.rebuild_done') + ' (' + selected.length + ' ' + t('config_memory.rebuild_instances_label') + ')';
    btn.disabled = false;
    cancel.style.display = 'none';
    const _resumeEl = document.getElementById('rebuild-resume-info');
    if (_resumeEl) _resumeEl.style.display = 'none';
    loadMemoryStats();
    checkResumeInfo();
  });
}

async function cancelRebuild() {
  if (_rebuildSSE) { _rebuildSSE.close(); _rebuildSSE = null; }
  const selected = [...document.querySelectorAll('.rebuild-cb:checked')].map(cb => cb.dataset.inst);
  for (const inst of selected) {
    await fetch(`/api/rebuild-cancel/${inst}`, { method: 'POST' }).catch(() => {});
  }
  setRebuildProgress(0, 0, null, '\u25a0 ' + t('config_memory.rebuild_cancelled'));
  document.getElementById('rebuild-btn').disabled = false;
  document.getElementById('rebuild-cancel-btn').style.display = 'none';
  // Nach kurzer Pause Resume-Info laden
  setTimeout(checkResumeInfo, 1000);
}

async function checkResumeInfo() {
  const resumeDiv = document.getElementById('rebuild-resume-info');
  if (!resumeDiv) return;
  const instances = [...document.querySelectorAll('.rebuild-cb')].map(cb => cb.dataset.inst);
  let html = '';
  for (const inst of instances) {
    try {
      const r = await fetch(`/api/rebuild-resume-info/${inst}`);
      const d = await r.json();
      if (d.has_progress) {
        html += `<div style="margin-bottom:4px;">
          <strong>${escHtml(inst)}</strong>: ${t('config_memory.rebuild_resume_info', {processed: d.processed, total: d.total_entries})}
          <button class="btn btn-sm btn-primary" style="margin-left:8px;" onclick="resumeRebuild('${escAttr(inst)}')">${t('config_memory.rebuild_resume')}</button>
        </div>`;
      }
    } catch(e) { /* ignore */ }
  }
  if (html) {
    resumeDiv.innerHTML = html;
    resumeDiv.style.display = '';
  } else {
    resumeDiv.style.display = 'none';
  }
}

async function resumeRebuild(inst) {
  // Instanz auswählen und Resume starten
  document.querySelectorAll('.rebuild-cb').forEach(cb => {
    cb.checked = cb.dataset.inst === inst;
  });
  startRebuild(true);
}

function startRebuildSSE(inst, onDone) {
  if (_rebuildSSE) _rebuildSSE.close();
  _rebuildSSE = new EventSource(`/api/rebuild-progress/${inst}`);
  _rebuildSSE.onmessage = (e) => {
    const d = JSON.parse(e.data);
    const errSuffix = d.errors > 0 ? ' (' + d.errors + ' ' + t('config_memory.rebuild_error') + ')' : '';
    setRebuildProgress(d.done, d.total, d.eta_s, statusLabel(d.status, d.error) + errSuffix);
    if (['done','error','cancelled'].includes(d.status)) {
      _rebuildSSE.close(); _rebuildSSE = null;
      if (d.status === 'done') {
        const msg = d.errors > 0
          ? inst + ': ' + t('config_memory.rebuild_complete_errors', {errors: d.errors})
          : inst + ': ' + t('config_memory.rebuild_complete') + ' \u2713';
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
    ? done + ' / ' + total + ' ' + t('logs.entries') + ' (' + pct + '%)'
    : (statusText || '');
  document.getElementById('rebuild-eta').textContent = eta_s != null && eta_s > 0
    ? (eta_s > 60 ? t('config_memory.rebuild_eta_min', {min: Math.round(eta_s/60)}) : t('config_memory.rebuild_eta_sec', {sec: eta_s})) : '';
  document.getElementById('rebuild-status-text').textContent = total > 0 ? statusText : '';
}

function statusLabel(status, error) {
  if (status === 'running')   return '\u23f3 ' + t('config_memory.rebuild_running');
  if (status === 'done')      return '\u2713 ' + t('config_memory.rebuild_done');
  if (status === 'error')     return '\u274c ' + t('config_memory.rebuild_error') + ': ' + (error || '');
  if (status === 'cancelled') return '\u25a0 ' + t('config_memory.rebuild_cancelled');
  return '';
}

// ── Embedding-Modell Hilfe ─────────────────────────────────────────────────
function updateEmbedDims() {
  const sel = document.getElementById('embed-model');
  const dims = document.getElementById('embed-dims');
  if (!sel || !dims) return;
  const modelName = sel.value;
  const knownDims = _EMBED_DIMS[modelName] || _EMBED_DIMS[modelName.split(':')[0]];
  if (knownDims) dims.value = knownDims;
}

// ── Verbindungstest ────────────────────────────────────────────────────────
async function testSvcConn(type, url, resultId) {
  const el = document.getElementById(resultId);
  if (!url) { el.textContent = '\u26a0 ' + t('config_services.url_missing'); el.style.color = 'var(--yellow)'; return; }
  el.textContent = '\u2026'; el.style.color = 'var(--muted)';
  try {
    const r = await fetch('/api/test-connection', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ type, url }),
    });
    const d = await r.json();
    el.textContent = d.ok ? `\u2713 ${d.detail}` : `\u2717 ${d.detail}`;
    el.style.color = d.ok ? 'var(--green)' : 'var(--red)';
  } catch(e) { el.textContent = '\u2717 ' + e.message; el.style.color = 'var(--red)'; }
}

async function loadSttTtsEntities() {
  const statusEl = document.getElementById('stt-tts-load-status');
  statusEl.textContent = t('config_services.stt_tts_loading');
  statusEl.style.color = 'var(--muted)';
  try {
    const r = await fetch('/api/ha-stt-tts');
    const d = await r.json();
    if (!d.ok) {
      statusEl.textContent = '\u2717 ' + (d.error || t('config_services.stt_tts_error'));
      statusEl.style.color = 'var(--red)';
      return;
    }
    const sttEl = document.getElementById('svc-stt-entity');
    const ttsEl = document.getElementById('svc-tts-entity');
    const prevStt = sttEl.value;
    const prevTts = ttsEl.value;

    sttEl.innerHTML = '<option value="">' + t('config_services.not_configured') + '</option>';
    d.stt.forEach(e => {
      sttEl.add(new Option(`${e.name} (${e.id})`, e.id));
    });
    if (prevStt) sttEl.value = prevStt;

    ttsEl.innerHTML = '<option value="">' + t('config_services.not_configured') + '</option>';
    d.tts.forEach(e => {
      ttsEl.add(new Option(`${e.name} (${e.id})`, e.id));
    });
    if (prevTts) ttsEl.value = prevTts;

    statusEl.textContent = '\u2713 ' + d.stt.length + ' ' + t('config_services.stt_tts_entities', {tts: d.tts.length});
    statusEl.style.color = 'var(--green)';
  } catch(e) {
    statusEl.textContent = '\u2717 ' + e.message;
    statusEl.style.color = 'var(--red)';
  }
}

async function testHaConnection() {
  const el = document.getElementById('test-ha-result');
  const ha_url   = document.getElementById('svc-ha-url')?.value?.trim();
  const ha_token = document.getElementById('svc-ha-token')?.value?.trim();
  if (!ha_url)   { el.textContent = '\u26a0 ' + t('config_services.url_missing');   el.style.color = 'var(--yellow)'; return; }
  if (!ha_token) { el.textContent = '\u26a0 ' + t('config_services.token_missing'); el.style.color = 'var(--yellow)'; return; }
  el.textContent = '\u2026'; el.style.color = 'var(--muted)';
  try {
    const r = await fetch('/api/test-ha', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ ha_url, ha_token }),
    });
    const d = await r.json();
    el.textContent = d.ok ? `\u2713 ${d.detail}` : `\u2717 ${d.detail}`;
    el.style.color = d.ok ? 'var(--green)' : 'var(--red)';
  } catch(e) { el.textContent = '\u2717 ' + e.message; el.style.color = 'var(--red)'; }
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
    if (hint) { hint.textContent = t('config_services.ha_url_missing'); hint.style.display = ''; hint.style.color = 'var(--yellow)'; }
    return;
  }
  const url = `${haUrl}/mcp_server/sse`;
  if (mcpUrl) mcpUrl.value = url;
  if (hint)   { hint.textContent = `\u2192 ${url}`; hint.style.display = ''; hint.style.color = 'var(--muted)'; }
}

async function testMcpConnection() {
  const el    = document.getElementById('test-mcp-result');
  let mcp_url = document.getElementById('svc-mcp-url')?.value?.trim();
  let token   = document.getElementById('svc-mcp-token')?.value?.trim();
  if (!token) token = document.getElementById('svc-ha-token')?.value?.trim();
  if (!mcp_url) {
    const haUrl = document.getElementById('svc-ha-url')?.value?.trim().replace(/\/$/, '');
    if (haUrl) mcp_url = `${haUrl}/mcp_server/sse`;
  }
  if (!mcp_url) { el.textContent = '\u26a0 ' + t('config_services.mcp_url_missing'); el.style.color = 'var(--yellow)'; return; }
  if (!token)   { el.textContent = '\u26a0 ' + t('config_services.token_missing');   el.style.color = 'var(--yellow)'; return; }
  el.textContent = '\u2026'; el.style.color = 'var(--muted)';
  try {
    const r = await fetch('/api/test-ha-mcp', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ mcp_url, token }),
    });
    const d = await r.json();
    el.textContent = d.ok ? `\u2713 ${d.detail}` : `\u2717 ${d.detail}`;
    el.style.color = d.ok ? 'var(--green)' : 'var(--red)';
  } catch(e) { el.textContent = '\u2717 ' + e.message; el.style.color = 'var(--red)'; }
}

async function testProviderConn(i) {
  const el   = document.getElementById(`prov-${i}-test`);
  const type = cfg?.providers?.[i]?.type || 'custom';
  const key  = document.getElementById(`prov-${i}-key`)?.value?.trim() || '';
  let   url  = document.getElementById(`prov-${i}-url`)?.value?.trim() || '';

  const defaults = {
    anthropic: 'https://api.anthropic.com',
    minimax:   'https://api.minimax.io',
    openai:    'https://api.openai.com',
    gemini:    'https://generativelanguage.googleapis.com',
    ollama:    '',
  };
  if (!url && defaults[type]) url = defaults[type];

  if (!url) { el.textContent = '\u26a0 ' + t('config_provider.no_url_configured'); el.style.color = 'var(--yellow)'; return; }

  el.textContent = '\u2026'; el.style.color = 'var(--muted)';

  if (['anthropic','minimax','openai','gemini'].includes(type) && key) {
    try {
      const r = await fetch('/api/fetch-models', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ type, url, key }),
      });
      const d = await r.json();
      const count = d.models?.length ?? 0;
      el.textContent = count > 0 ? '\u2713 ' + t('config_provider.connected') + ' \u00b7 ' + count + ' ' + t('config_provider.models_label') : '\u26a0 ' + t('config_provider.connected_no_models');
      el.style.color = count > 0 ? 'var(--green)' : 'var(--yellow)';
    } catch(e) { el.textContent = '\u2717 ' + e.message; el.style.color = 'var(--red)'; }
    return;
  }

  const connType = type === 'ollama' ? 'ollama' : 'http';
  try {
    const r = await fetch('/api/test-connection', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ type: connType, url }),
    });
    const d = await r.json();
    el.textContent = d.ok ? `\u2713 ${d.detail}` : `\u2717 ${d.detail}`;
    el.style.color = d.ok ? 'var(--green)' : 'var(--red)';
  } catch(e) { el.textContent = '\u2717 ' + e.message; el.style.color = 'var(--red)'; }
}

// ── Claude Auth ─────────────────────────────────────────────────────────────

async function checkClaudeAuth() {
  const el = document.getElementById('claude-auth-status');
  if (!el) return;
  el.textContent = t('config_services.auth_checking');
  el.style.color = '';
  try {
    const r = await fetch('/api/claude-auth/status');
    const d = await r.json();
    if (d.ok) {
      el.innerHTML = `<span style="color:var(--green)">\u2713 ${escHtml(d.detail)}</span>`;
    } else {
      el.innerHTML = `<span style="color:var(--red)">\u2717 ${escHtml(d.detail)}</span>`;
    }
  } catch(e) {
    el.innerHTML = `<span style="color:var(--red)">\u2717 ${escHtml(e.message)}</span>`;
  }
}

async function uploadClaudeAuth() {
  const textarea = document.getElementById('claude-auth-creds');
  const result = document.getElementById('claude-auth-upload-result');
  if (!textarea || !result) return;
  const raw = textarea.value.trim();
  if (!raw) { result.textContent = t('config_services.auth_paste_prompt'); result.style.color = 'var(--red)'; return; }
  let creds;
  try { creds = JSON.parse(raw); } catch(e) { result.textContent = t('config_services.auth_invalid_json'); result.style.color = 'var(--red)'; return; }
  try {
    const r = await fetch('/api/claude-auth/upload', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ credentials: creds }),
    });
    const d = await r.json();
    result.textContent = d.ok ? `\u2713 ${d.detail}` : `\u2717 ${d.detail || d.error}`;
    result.style.color = d.ok ? 'var(--green)' : 'var(--red)';
    if (d.ok) { textarea.value = ''; checkClaudeAuth(); }
  } catch(e) { result.textContent = '\u2717 ' + e.message; result.style.color = 'var(--red)'; }
}

async function startOAuthLogin() {
  const statusEl = document.getElementById('oauth-login-status');
  const urlEl = document.getElementById('oauth-login-url');
  const codeSection = document.getElementById('oauth-code-section');
  if (!statusEl) return;

  statusEl.innerHTML = `<span style="color:var(--muted)">${t('config_services.auth_checking')}</span>`;
  urlEl.innerHTML = '';
  codeSection.style.display = 'none';

  try {
    const r = await fetch('/api/claude-auth/login/start', { method: 'POST' });
    const d = await r.json();
    if (!d.ok) {
      statusEl.innerHTML = `<span style="color:var(--red)">\u2717 ${escHtml(d.detail)}</span>`;
      return;
    }
    statusEl.innerHTML = `<span style="color:var(--green)">${t('config_services.oauth_url_ready')}</span>`;
    urlEl.innerHTML = `<a href="${escHtml(d.url)}" target="_blank" rel="noopener" style="word-break:break-all;color:var(--accent);">${t('config_services.oauth_open_link')}</a>`;
    codeSection.style.display = 'block';
    document.getElementById('oauth-code-input').value = '';
    document.getElementById('oauth-code-result').textContent = '';
  } catch(e) {
    statusEl.innerHTML = `<span style="color:var(--red)">\u2717 ${e.message}</span>`;
  }
}

async function completeOAuthLogin() {
  const codeInput = document.getElementById('oauth-code-input');
  const resultEl = document.getElementById('oauth-code-result');
  if (!codeInput || !resultEl) return;

  const code = codeInput.value.trim();
  if (!code) { resultEl.textContent = t('config_services.oauth_code_missing'); resultEl.style.color = 'var(--red)'; return; }

  resultEl.innerHTML = `<span style="color:var(--muted)">${t('config_services.auth_checking')}</span>`;
  try {
    const r = await fetch('/api/claude-auth/login/complete', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ code }),
    });
    const d = await r.json();
    resultEl.textContent = d.ok ? `\u2713 ${d.detail}` : `\u2717 ${d.detail}`;
    resultEl.style.color = d.ok ? 'var(--green)' : 'var(--red)';
    if (d.ok) {
      codeInput.value = '';
      document.getElementById('oauth-code-section').style.display = 'none';
      checkClaudeAuth();
    }
  } catch(e) { resultEl.textContent = '\u2717 ' + e.message; resultEl.style.color = 'var(--red)'; }
}


// ── Provider-scoped OAuth ──────────────────────────────────────────────────────────

async function checkProviderOAuth(i) {
  const p = cfg?.providers?.[i];
  if (!p) return;
  const el = document.getElementById(`prov-${i}-oauth-status`);
  if (!el) return;
  el.textContent = t('config_services.auth_checking');
  el.style.color = '';
  try {
    const r = await fetch(`/api/claude-auth/status/${encodeURIComponent(p.id)}`);
    const d = await r.json();
    if (d.ok) {
      el.innerHTML = `<span style="color:var(--green)">✓ ${escHtml(d.detail)}</span>`;
    } else {
      el.innerHTML = `<span style="color:var(--red)">✗ ${escHtml(d.detail)}</span>`;
    }
  } catch(e) {
    el.innerHTML = `<span style="color:var(--red)">✗ ${escHtml(e.message)}</span>`;
  }
}

async function startProviderOAuthLogin(i) {
  const p = cfg?.providers?.[i];
  if (!p) return;
  const statusEl = document.getElementById(`prov-${i}-oauth-login-status`);
  const urlEl = document.getElementById(`prov-${i}-oauth-login-url`);
  const codeSection = document.getElementById(`prov-${i}-oauth-code-section`);
  if (!statusEl) return;

  statusEl.innerHTML = `<span style="color:var(--muted)">${t('config_services.auth_checking')}</span>`;
  urlEl.innerHTML = '';
  codeSection.style.display = 'none';

  try {
    const r = await fetch(`/api/claude-auth/login/start/${encodeURIComponent(p.id)}`, { method: 'POST' });
    const d = await r.json();
    if (!d.ok) {
      statusEl.innerHTML = `<span style="color:var(--red)">✗ ${escHtml(d.detail)}</span>`;
      return;
    }
    statusEl.innerHTML = `<span style="color:var(--green)">${t('config_services.oauth_url_ready')}</span>`;
    urlEl.innerHTML = `<a href="${escHtml(d.url)}" target="_blank" rel="noopener" style="word-break:break-all;color:var(--accent);">${t('config_services.oauth_open_link')}</a>`;
    codeSection.style.display = 'block';
    document.getElementById(`prov-${i}-oauth-code-input`).value = '';
    document.getElementById(`prov-${i}-oauth-code-result`).textContent = '';
  } catch(e) {
    statusEl.innerHTML = `<span style="color:var(--red)">✗ ${e.message}</span>`;
  }
}

async function completeProviderOAuthLogin(i) {
  const p = cfg?.providers?.[i];
  if (!p) return;
  const codeInput = document.getElementById(`prov-${i}-oauth-code-input`);
  const resultEl = document.getElementById(`prov-${i}-oauth-code-result`);
  if (!codeInput || !resultEl) return;

  const code = codeInput.value.trim();
  if (!code) { resultEl.textContent = t('config_services.oauth_code_missing'); resultEl.style.color = 'var(--red)'; return; }

  resultEl.innerHTML = `<span style="color:var(--muted)">${t('config_services.auth_checking')}</span>`;
  try {
    const r = await fetch(`/api/claude-auth/login/complete/${encodeURIComponent(p.id)}`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ code }),
    });
    const d = await r.json();
    resultEl.textContent = d.ok ? `✓ ${d.detail}` : `✗ ${d.detail}`;
    resultEl.style.color = d.ok ? 'var(--green)' : 'var(--red)';
    if (d.ok) {
      codeInput.value = '';
      document.getElementById(`prov-${i}-oauth-code-section`).style.display = 'none';
      checkProviderOAuth(i);
    }
  } catch(e) { resultEl.textContent = '✗ ' + e.message; resultEl.style.color = 'var(--red)'; }
}

async function uploadProviderCredentials(i) {
  const p = cfg?.providers?.[i];
  if (!p) return;
  const textarea = document.getElementById(`prov-${i}-oauth-creds`);
  const result = document.getElementById(`prov-${i}-oauth-upload-result`);
  if (!textarea || !result) return;
  const raw = textarea.value.trim();
  if (!raw) { result.textContent = t('config_services.auth_paste_prompt'); result.style.color = 'var(--red)'; return; }
  let creds;
  try { creds = JSON.parse(raw); } catch(e) { result.textContent = t('config_services.auth_invalid_json'); result.style.color = 'var(--red)'; return; }
  try {
    const r = await fetch(`/api/claude-auth/upload/${encodeURIComponent(p.id)}`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ credentials: creds }),
    });
    const d = await r.json();
    result.textContent = d.ok ? `✓ ${d.detail}` : `✗ ${d.detail || d.error}`;
    result.style.color = d.ok ? 'var(--green)' : 'var(--red)';
    if (d.ok) { textarea.value = ''; checkProviderOAuth(i); }
  } catch(e) { result.textContent = '✗ ' + e.message; result.style.color = 'var(--red)'; }
}