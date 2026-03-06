// chat.js – Konversationen laden/rendern, Send-Box, SSE Live-Updates

// ── Konversationen laden ───────────────────────────────────────────────────
async function loadConversations(inst) {
  const limit = document.getElementById('conv-limit')?.value || 50;
  try {
    const r = await fetch(`/api/conversations/${inst}?limit=${limit}`);
    const data = await r.json();
    renderConversations(data);
  } catch(e) {
    document.getElementById('conv-list').innerHTML =
      `<div class="empty-state"><div class="icon">!</div><div>${e.message}</div></div>`;
  }
}

function channelBadge(ch) {
  const map = { repl:'REPL', whatsapp:'WhatsApp', webchat:'Webchat', ha_app:'HA App' };
  return `<span class="channel-badge ch-${ch}">${map[ch] || ch}</span>`;
}

function renderConversations(records) {
  const list = document.getElementById('conv-list');
  if (!records.length) {
    list.innerHTML = '<div class="empty-state"><div class="icon">--</div><div>Noch keine Konversationen für diese Instanz.</div></div>';
    return;
  }
  list.innerHTML = records.map((r, i) => {
    const ts   = r.ts ? new Date(r.ts).toLocaleString('de-DE', {hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '–';
    const user = escHtml(r.user || '').substring(0, 120);
    const asst = escHtml(r.assistant || '').substring(0, 200);
    const tools = (r.tool_calls || []).map(t => {
      const inp = t.input ? ` <span style="color:var(--muted);font-weight:400;">→ ${escHtml(String(t.input).substring(0,60))}${String(t.input).length>60?'…':''}</span>` : '';
      return `<span class="tool-chip">${escHtml(t.tool)}${inp}</span>`;
    }).join('');
    const memHits = r.memory_hits > 0 ? ` (${r.memory_hits})` : '';
    const memBadge = r.memory_used
      ? `<span class="mem-badge mem-yes">Memory${memHits}</span>`
      : '<span class="mem-badge mem-no">kein Memory</span>';

    return `
    <div class="conv-card" id="card-${i}">
      <div class="conv-header" onclick="toggleCard(${i})">
        <div class="conv-meta">
          <span class="conv-time">${ts}</span>
          ${channelBadge(r.channel || 'repl')}
        </div>
        <div class="conv-messages">
          <div class="conv-user"><strong>Du:</strong> ${user}${r.user?.length > 120 ? '…' : ''}</div>
          <div class="conv-assistant"><em>${asst}${r.assistant?.length > 200 ? '…' : ''}</em></div>
        </div>
        <div class="expand-icon">›</div>
      </div>
      <div class="conv-details">
        <div class="detail-grid">
          <div class="detail-box">
            <div class="detail-label">User (vollständig)</div>
            <div class="detail-value">${escHtml(r.user || '')}</div>
          </div>
          <div class="detail-box">
            <div class="detail-label">HAANA Antwort</div>
            <div class="detail-value">${escHtml(r.assistant || '')}</div>
          </div>
          <div class="detail-box">
            <div class="detail-label">Meta</div>
            <div class="detail-value">
              ${memBadge}<br>
              <span class="latency">${r.latency_s ?? '–'}s</span>
            </div>
          </div>
          <div class="detail-box">
            <div class="detail-label">Tool-Aufrufe</div>
            <div class="detail-value">${tools || '<span style="color:var(--muted)">keine</span>'}</div>
          </div>
        </div>
      </div>
    </div>`;
  }).join('');
}

function toggleCard(i) {
  document.getElementById('card-' + i)?.classList.toggle('expanded');
}

// ── SSE Live-Updates ───────────────────────────────────────────────────────
function startSSE(inst) {
  if (sse) { sse.close(); sse = null; }
  const dot   = document.getElementById('live-dot');
  const label = document.getElementById('live-label');

  sse = new EventSource(`/api/events/${inst}`);
  sse.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'connected') {
      dot.classList.remove('offline');
      label.textContent = 'Live';
    } else if (msg.type === 'conversation') {
      prependConversation(msg.record);
    }
  };
  sse.onerror = () => {
    dot.classList.add('offline');
    label.textContent = 'Offline';
  };
}

function prependConversation(record) {
  const list = document.getElementById('conv-list');
  const emptyState = list.querySelector('.empty-state');
  if (emptyState) list.innerHTML = '';

  const div = document.createElement('div');
  const i = 'live-' + Date.now();
  div.innerHTML = renderSingleConv(record, i);
  list.insertAdjacentElement('afterbegin', div.firstElementChild);
}

function renderSingleConv(r, cardId) {
  const ts    = r.ts ? new Date(r.ts).toLocaleString('de-DE', {hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '–';
  const user  = escHtml(r.user || '').substring(0, 120);
  const asst  = escHtml(r.assistant || '').substring(0, 200);
  const tools = (r.tool_calls || []).map(t => `<span class="tool-chip">${escHtml(t.tool)}</span>`).join('');
  const memBadge = r.memory_used ? '<span class="mem-badge mem-yes">Memory</span>' : '';
  return `
  <div class="conv-card" id="${cardId}" style="border-color:var(--accent);">
    <div class="conv-header" onclick="this.closest('.conv-card').classList.toggle('expanded')">
      <div class="conv-meta">
        <span class="conv-time">${ts}</span>
        ${channelBadge(r.channel || 'repl')}
        ${memBadge}
      </div>
      <div class="conv-messages">
        <div class="conv-user"><strong>Du:</strong> ${user}</div>
        <div class="conv-assistant"><em>${asst}</em></div>
      </div>
      <div class="expand-icon">›</div>
    </div>
    <div class="conv-details">
      <div class="detail-grid">
        <div class="detail-box"><div class="detail-label">User</div><div class="detail-value">${escHtml(r.user||'')}</div></div>
        <div class="detail-box"><div class="detail-label">HAANA</div><div class="detail-value">${escHtml(r.assistant||'')}</div></div>
        <div class="detail-box"><div class="detail-label">Latenz</div><div class="detail-value latency">${r.latency_s??'–'}s</div></div>
        <div class="detail-box"><div class="detail-label">Tools</div><div class="detail-value">${tools||'–'}</div></div>
      </div>
    </div>
  </div>`;
}

// ── Chat-Eingabe ───────────────────────────────────────────────────────────
function handleChatKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendChat();
  }
}

async function sendChat() {
  const input  = document.getElementById('chat-input');
  const status = document.getElementById('chat-status');
  const btn    = document.getElementById('send-btn');
  const msg    = input.value.trim();
  if (!msg) return;

  input.value = '';
  input.style.borderColor = 'var(--border)';
  btn.disabled = true;
  btn.textContent = '...';
  status.textContent = `⏳ ${currentInstance} denkt nach...`;

  // Optimistisch sofort anzeigen
  const tempId = 'pending-' + Date.now();
  prependPendingMessage(msg, tempId);

  try {
    const r = await fetch(`/api/chat/${currentInstance}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ message: msg }),
    });

    if (!r.ok) {
      const err = await r.json().catch(() => ({detail: r.statusText}));
      const errMsg = err.detail || 'Unbekannter Fehler';
      updatePendingMessage(tempId, msg, '❌ ' + errMsg, true);
      status.textContent = '❌ ' + errMsg;
    } else {
      const data = await r.json();
      updatePendingMessage(tempId, msg, data.response, false);
      status.textContent = '';
    }
  } catch(e) {
    updatePendingMessage(tempId, msg, '❌ Verbindungsfehler: ' + e.message, true);
    status.textContent = '❌ ' + e.message;
  }

  btn.disabled = false;
  btn.textContent = 'Senden ↵';
  input.focus();
}

function prependPendingMessage(userMsg, cardId) {
  const list = document.getElementById('conv-list');
  const empty = list.querySelector('.empty-state');
  if (empty) list.innerHTML = '';

  const now = new Date().toLocaleString('de-DE', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  const html = `
  <div class="conv-card" id="${cardId}" style="border-color:var(--accent2);opacity:0.7;">
    <div class="conv-header" style="cursor:default;">
      <div class="conv-meta">
        <span class="conv-time">${now}</span>
        <span class="channel-badge ch-webchat">Webchat</span>
      </div>
      <div class="conv-messages">
        <div class="conv-user"><strong>Du:</strong> ${escHtml(userMsg)}</div>
        <div class="conv-assistant" id="${cardId}-resp" style="color:var(--muted);">
          <span style="animation:pulse 1s infinite;">…</span>
        </div>
      </div>
    </div>
  </div>`;
  list.insertAdjacentHTML('afterbegin', html);
}

function updatePendingMessage(cardId, userMsg, response, isError) {
  const card = document.getElementById(cardId);
  if (!card) return;
  card.style.opacity = '1';
  card.style.borderColor = isError ? 'var(--red)' : 'var(--border)';
  const respEl = document.getElementById(cardId + '-resp');
  if (respEl) {
    respEl.style.color = isError ? 'var(--red)' : '';
    respEl.innerHTML = `<em>${escHtml(response)}</em>`;
  }
  // Expandierbar machen
  const header = card.querySelector('.conv-header');
  if (header && !isError) {
    header.style.cursor = 'pointer';
    header.onclick = () => card.classList.toggle('expanded');
    card.insertAdjacentHTML('beforeend', `
      <div class="conv-details">
        <div class="detail-grid">
          <div class="detail-box"><div class="detail-label">User (vollständig)</div><div class="detail-value">${escHtml(userMsg)}</div></div>
          <div class="detail-box"><div class="detail-label">HAANA Antwort</div><div class="detail-value">${escHtml(response)}</div></div>
        </div>
      </div>`);
    const expandIcon = document.createElement('div');
    expandIcon.className = 'expand-icon';
    expandIcon.textContent = '›';
    header.appendChild(expandIcon);
  }
}

async function checkAgentHealth(inst) {
  const el = document.getElementById('agent-status');
  try {
    const r = await fetch(`/api/agent-health/${inst}`);
    const d = await r.json();
    el.textContent = d.ok ? '● Agent online' : '● Agent offline';
    el.style.color  = d.ok ? 'var(--green)' : 'var(--red)';
  } catch {
    el.textContent = '● Agent nicht erreichbar';
    el.style.color = 'var(--red)';
  }
}
