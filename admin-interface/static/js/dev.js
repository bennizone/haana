// HAANA Dev Tab — Claude Code Provider-Auswahl
'use strict';

let _savedProviderId = '';

async function loadDevProvider() {
  try {
    const [cfgRes, savedRes] = await Promise.all([
      fetch('/api/config').then(r => r.json()),
      fetch('/api/dev/claude-provider').then(r => r.json()).catch(() => ({}))
    ]);
    const providers = cfgRes.providers || [];
    const llms = cfgRes.llms || [];

    // Provider-Dropdown befüllen
    const sel = document.getElementById('dev-provider-select');
    if (!sel) return;
    sel.innerHTML = providers.map(p =>
      `<option value="${escAttr(p.id)}">${escHtml(p.name)} (${escHtml(p.type)})</option>`
    ).join('');
    if (savedRes.provider_id) sel.value = savedRes.provider_id;
    _savedProviderId = sel.value;

    // MCP-Checkboxen: sichtbar wenn Minimax-Provider existiert
    const hasMinimax = providers.some(p => p.type === 'minimax');
    const mcpRow = document.getElementById('dev-mcp-row');
    if (mcpRow) mcpRow.style.display = hasMinimax ? '' : 'none';
    const cbWs = document.getElementById('dev-mcp-web-search');
    const cbImg = document.getElementById('dev-mcp-image');
    if (cbWs) cbWs.checked = !!savedRes.mcp_web_search;
    if (cbImg) cbImg.checked = !!savedRes.mcp_image;

    // Modell-Dropdown befüllen
    _devPopulateModels(sel.value, providers, llms, savedRes.model);

    // Bei Ollama: Modelle live nachladen
    const selectedProvider = providers.find(p => p.id === sel.value);
    if (selectedProvider && selectedProvider.type === 'ollama' && selectedProvider.url) {
      _devLoadOllamaModels(selectedProvider.url).then(() => {
        if (savedRes.model) {
          const modelSel = document.getElementById('dev-model-select');
          if (modelSel) modelSel.value = savedRes.model;
        }
      });
    }
  } catch (e) {
    console.warn('loadDevProvider:', e);
  }
}

function _devPopulateModels(providerId, providers, llms, selectedModel) {
  const modelRow = document.getElementById('dev-model-row');
  const modelSel = document.getElementById('dev-model-select');
  if (!modelRow || !modelSel) return;

  const provider = providers.find(p => p.id === providerId);
  const isAnthropic = provider && provider.type === 'anthropic';
  const provLlms = llms.filter(l => l.provider_id === providerId);

  if (isAnthropic || provLlms.length === 0) {
    modelRow.style.display = 'none';
  } else {
    modelRow.style.display = '';
    modelSel.innerHTML = provLlms.map(l =>
      `<option value="${escAttr(l.model)}">${escHtml(l.name)} (${escHtml(l.model)})</option>`
    ).join('');
    if (selectedModel) modelSel.value = selectedModel;
  }
}

async function _devOnProviderChange(providerId) {
  try {
    const cfg = await fetch('/api/config').then(r => r.json());
    const providers = cfg.providers || [];
    const llms = cfg.llms || [];
    const provider = providers.find(p => p.id === providerId);

    _devPopulateModels(providerId, providers, llms, '');

    // Bei Ollama: Modelle live von der API laden
    if (provider && provider.type === 'ollama' && provider.url) {
      _devLoadOllamaModels(provider.url);
    }
  } catch (e) {
    console.warn('_devOnProviderChange:', e);
  }
}

async function _devLoadOllamaModels(url) {
  const modelSel = document.getElementById('dev-model-select');
  const modelRow = document.getElementById('dev-model-row');
  if (!modelSel || !modelRow) return;

  try {
    const data = await fetch(url.replace(/\/$/, '') + '/api/tags').then(r => r.json());
    const models = (data.models || []).map(m => m.name || m.model || m);
    if (models.length > 0) {
      modelRow.style.display = '';
      modelSel.innerHTML = models.map(m =>
        `<option value="${escAttr(m)}">${escHtml(m)}</option>`
      ).join('');
    }
  } catch (e) {
    console.warn('_devLoadOllamaModels:', e);
  }
}

async function saveDevProvider() {
  const sel = document.getElementById('dev-provider-select');
  const modelRow = document.getElementById('dev-model-row');
  const modelSel = document.getElementById('dev-model-select');
  const cbWs = document.getElementById('dev-mcp-web-search');
  const cbImg = document.getElementById('dev-mcp-image');
  const msg = document.getElementById('dev-save-msg');

  const prevProviderId = _savedProviderId;
  const modelVisible = modelRow && modelRow.style.display !== 'none';
  const body = {
    provider_id: sel ? sel.value : '',
    model: (modelVisible && modelSel) ? modelSel.value : '',
    mcp_web_search: !!(cbWs && cbWs.checked),
    mcp_image: !!(cbImg && cbImg.checked),
  };

  try {
    const res = await fetch('/api/dev/claude-provider', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.ok) {
      if (msg) {
        msg.style.display = '';
        setTimeout(() => { msg.style.display = 'none'; }, 3000);
      }
      const newProviderId = sel ? sel.value : '';
      if (prevProviderId && newProviderId !== prevProviderId) {
        toast(t('dev.provider_changed_warning') + ' <a href="#" onclick="clearDevSessions();return false;">' + t('dev.clear_now') + '</a>', 'warn', 8000, true);
      }
      _savedProviderId = newProviderId;
    }
  } catch (e) {
    console.error('saveDevProvider:', e);
  }
}

async function clearDevSessions() {
  if (!confirm(t('dev.clear_sessions_confirm'))) return;
  const btn = document.querySelector('[onclick="clearDevSessions()"]');
  if (btn) btn.disabled = true;
  try {
    const r = await fetch('/api/dev/clear-sessions', { method: 'POST' });
    if (!r.ok) throw new Error(await r.text());
    const d = await r.json();
    toast(t('dev.clear_sessions_done') + (d.deleted.length ? ` (${d.deleted.length})` : ''), 'ok');
  } catch (e) {
    toast(t('dev.clear_sessions_error') + ': ' + e.message, 'err');
  } finally {
    if (btn) btn.disabled = false;
  }
}
