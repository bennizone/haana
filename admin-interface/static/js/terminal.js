// HAANA Terminal - Claude Code Integration
'use strict';

// ── Dev: Claude Code Provider ─────────────────────────────────────────────────

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
      `<option value="${p.id}">${escHtml(p.name)} (${escHtml(p.type)})</option>`
    ).join('');
    if (savedRes.provider_id) sel.value = savedRes.provider_id;

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
    if (data.ok && msg) {
      msg.style.display = '';
      setTimeout(() => { msg.style.display = 'none'; }, 3000);
    }
  } catch (e) {
    console.error('saveDevProvider:', e);
  }
}

// ─────────────────────────────────────────────────────────────────────────────

let _term = null;
let _ws = null;
let _fitAddon = null;
let _termResizeObserver = null;
let _termConnected = false;
let _termProviderId = '';

function initTerminal() {
    if (_term) return; // Nur einmal initialisieren

    // xterm.js Terminal erstellen
    _term = new Terminal({
        theme: { background: '#1e1e1e', foreground: '#d4d4d4', cursor: '#ffffff' },
        fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
        fontSize: 14,
        lineHeight: 1.2,
        cursorBlink: true,
        scrollback: 2000,
        allowTransparency: false,
    });

    _fitAddon = new FitAddon.FitAddon();
    _term.loadAddon(_fitAddon);

    const container = document.getElementById('terminal-xterm');
    _term.open(container);
    _fitAddon.fit();

    // Resize Observer
    _termResizeObserver = new ResizeObserver(() => {
        if (_fitAddon) _fitAddon.fit();
        _termSendResize();
    });
    _termResizeObserver.observe(container);

    // User-Eingabe -> WebSocket
    _term.onData(data => {
        if (_ws && _ws.readyState === WebSocket.OPEN) {
            _ws.send(data);
        }
    });

    // Provider laden und Status pruefen
    _termLoadProviders();
    _termLoadStatus();
    loadDevProvider();

    // Willkommensnachricht
    _term.writeln('\x1b[1;36mHAANA Development Terminal\x1b[0m');
    _term.writeln('\x1b[90mProvider waehlen und "Verbinden" klicken um Claude Code zu starten.\x1b[0m');
    _term.writeln('');
}

function _termLoadProviders() {
    fetch('/api/config')
        .then(r => r.json())
        .then(cfg => {
            const sel = document.getElementById('term-provider-select');
            if (!sel) return;
            sel.innerHTML = '<option value="">' + (I18n.t('terminal.provider_none') || 'Kein Provider') + '</option>';
            (cfg.providers || [])
                .filter(p => p.type === 'anthropic')
                .forEach(p => {
                    const opt = document.createElement('option');
                    opt.value = p.id || p.name;
                    opt.textContent = p.name + (p.auth_method === 'oauth' ? ' (OAuth)' : ' (API Key)');
                    sel.appendChild(opt);
                });
        })
        .catch(() => {});
}

function _termLoadStatus() {
    fetch('/api/terminal/status')
        .then(r => r.json())
        .then(s => {
            const dot = document.getElementById('term-status-dot');
            const txt = document.getElementById('term-status-text');
            if (s.session_active) {
                if (dot) dot.className = 'terminal-status-dot connected';
                if (txt) txt.textContent = I18n.t('terminal.session_active') || 'Session aktiv';
            } else {
                if (dot) dot.className = 'terminal-status-dot disconnected';
                if (txt) txt.textContent = I18n.t('terminal.no_session') || 'Keine Session';
            }
        })
        .catch(() => {});
}

function termConnect() {
    if (_termConnected) return;

    const sel = document.getElementById('term-provider-select');
    _termProviderId = sel ? sel.value : '';

    // Provider setzen falls gewaehlt
    const connect = () => {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = proto + '//' + location.host + '/ws/terminal';

        _ws = new WebSocket(url);
        _ws.binaryType = 'arraybuffer';

        _ws.onopen = () => {
            _termConnected = true;
            _termUpdateConnBtn(true);
            _termSendResize();
        };

        _ws.onmessage = e => {
            const data = e.data instanceof ArrayBuffer
                ? new Uint8Array(e.data)
                : e.data;
            _term.write(data);
        };

        _ws.onclose = () => {
            _termConnected = false;
            _termUpdateConnBtn(false);
            _term.writeln('\r\n\x1b[33m[Verbindung getrennt \u2013 Session laeuft in tmux weiter]\x1b[0m');
            _termLoadStatus();
        };

        _ws.onerror = () => {
            _term.writeln('\r\n\x1b[31m[WebSocket Fehler]\x1b[0m');
        };
    };

    if (_termProviderId) {
        fetch('/api/terminal/set-provider', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({provider_id: _termProviderId})
        }).then(() => connect()).catch(() => connect());
    } else {
        connect();
    }
}

function termDisconnect() {
    if (_ws) { _ws.close(); _ws = null; }
    _termConnected = false;
    _termUpdateConnBtn(false);
}

function _termUpdateConnBtn(connected) {
    const btn = document.getElementById('term-conn-btn');
    if (!btn) return;
    if (connected) {
        btn.textContent = I18n.t('terminal.disconnect_btn') || 'Trennen';
        btn.onclick = termDisconnect;
        btn.className = 'btn btn-secondary btn-sm';
    } else {
        btn.textContent = I18n.t('terminal.connect_btn') || 'Verbinden';
        btn.onclick = termConnect;
        btn.className = 'btn btn-primary btn-sm';
    }
}

function _termSendResize() {
    if (!_ws || _ws.readyState !== WebSocket.OPEN || !_term) return;
    const msg = JSON.stringify({type: 'resize', cols: _term.cols, rows: _term.rows});
    _ws.send(msg);
}

function termDetach() {
  const w = window.open(
    '/terminal',
    'haana-terminal',
    'width=1200,height=800,menubar=no,toolbar=no,location=no,status=no'
  );
  if (!w) {
    window.open('/terminal', '_blank');
  }
}
