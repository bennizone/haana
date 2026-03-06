// users.js – User-CRUD, Container-Management (restart/stop/delete)

let editingUserId = null;

function _llmOpts(selectedSlot) {
  if (!cfg || !cfg.llm_providers) return `<option value="1">Slot 1</option>`;
  return cfg.llm_providers.map(s =>
    `<option value="${s.slot}" ${s.slot == selectedSlot ? 'selected' : ''}>Slot ${s.slot} – ${escHtml(s.name||'')}</option>`
  ).join('');
}

function renderUserCard(u) {
  const sc = u.container_status === 'running' ? 'var(--green)' : u.container_status === 'absent' ? 'var(--muted)' : 'var(--red)';
  const dot = `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${sc};flex-shrink:0;"></span>`;
  const roleColor = {'admin':'var(--accent2)','voice':'var(--yellow)','voice-advanced':'var(--blue)','user':'var(--green)'}[u.role]||'var(--muted)';
  const sysTag = u.system ? `<span style="font-size:10px;background:rgba(96,165,250,.15);color:var(--blue);border-radius:4px;padding:1px 6px;margin-left:6px;">System</span>` : '';
  const isVoice = ['voice','voice-advanced'].includes(u.role);
  const waInfo = !isVoice && u.whatsapp_phone ? ` · WA: ${escHtml(u.whatsapp_phone)}` : '';
  const haInfo = !isVoice && u.ha_user ? ` · HA: ${escHtml(u.ha_user)}` : '';

  return `
  <div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;overflow:hidden;" id="user-card-${escAttr(u.id)}">
    <!-- Header -->
    <div style="padding:12px 16px;display:flex;align-items:center;gap:10px;">
      ${dot}
      <div style="flex:1;min-width:0;">
        <span style="font-weight:600;">${escHtml(u.display_name)}</span>
        <span style="color:var(--muted);font-size:12px;margin-left:6px;">(${escHtml(u.id)})</span>
        <span style="color:${roleColor};font-size:12px;margin-left:6px;">${escHtml(u.role)}</span>${sysTag}
        <div style="font-size:11px;color:var(--muted);margin-top:2px;">
          Port :${u.api_port}${haInfo}${waInfo} · ${escHtml(u.container_status)}
        </div>
      </div>
      <div style="display:flex;gap:5px;flex-shrink:0;" onclick="event.stopPropagation()">
        <button class="btn btn-secondary" style="font-size:11px;padding:3px 8px;" title="Neu starten" onclick="restartUserContainer('${escAttr(u.id)}')">↺</button>
        <button class="btn btn-secondary" style="font-size:11px;padding:3px 8px;" title="Stoppen" onclick="stopUserContainer('${escAttr(u.id)}')">Stop</button>
        <button class="btn btn-secondary" style="font-size:11px;padding:3px 10px;" id="uedit-btn-${escAttr(u.id)}" onclick="toggleUserExpand('${escAttr(u.id)}')">✎ Bearbeiten</button>
        ${!u.system ? `<button class="btn btn-danger" style="font-size:11px;padding:3px 8px;" onclick="deleteUser('${escAttr(u.id)}')">✕</button>` : ''}
      </div>
    </div>
    <!-- Expandable edit form -->
    <div id="user-expand-${escAttr(u.id)}" style="display:none;border-top:1px solid var(--border);padding:16px 16px 12px;">
      <div class="form-row">
        <div class="form-group">
          <label>Anzeigename</label>
          <input type="text" id="uf-${escAttr(u.id)}-name" value="${escAttr(u.display_name||'')}">
        </div>
        <div class="form-group">
          <label>Rolle</label>
          <select id="uf-${escAttr(u.id)}-role">
            <option value="user"  ${u.role==='user' ?'selected':''}>User (eingeschränkt)</option>
            <option value="admin" ${u.role==='admin'?'selected':''}>Admin (voller Zugriff)</option>
          </select>
        </div>
      </div>
      ${!isVoice ? `
      <div class="form-row">
        <div class="form-group">
          <label>HA-User <span style="font-size:11px;color:var(--muted);">(Person-Entität aus HA)</span></label>
          <div style="display:flex;gap:6px;">
            <select id="uf-${escAttr(u.id)}-ha" style="flex:1;">
              <option value="${escAttr(u.ha_user||'')}">${escHtml(u.ha_user||'– nicht zugeordnet –')}</option>
            </select>
            <button class="btn btn-secondary" style="font-size:11px;padding:4px 8px;flex-shrink:0;" onclick="loadHaUsersForCard('${escAttr(u.id)}')">↺</button>
          </div>
          <span id="uf-${escAttr(u.id)}-ha-status" style="font-size:11px;color:var(--muted);"></span>
        </div>
        <div class="form-group">
          <label>WhatsApp Rufnummer <span style="font-size:11px;color:var(--muted);">(z.B. 491234567890)</span></label>
          <input type="text" id="uf-${escAttr(u.id)}-wa-phone" value="${escAttr(u.whatsapp_phone||'')}" placeholder="Ohne +, ohne Leerzeichen">
        </div>
      </div>
      ` : ''}
      <div class="form-row">
        <div class="form-group">
          <label>Primäres LLM</label>
          <select id="uf-${escAttr(u.id)}-primary-llm">${_llmOpts(u.primary_llm_slot)}</select>
        </div>
        <div class="form-group">
          <label>Extraktions-LLM</label>
          <select id="uf-${escAttr(u.id)}-extract-llm">${_llmOpts(u.extraction_llm_slot)}</select>
        </div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;margin-top:8px;">
        <button class="btn btn-primary" onclick="saveUserEdit('${escAttr(u.id)}')">Speichern</button>
        <button class="btn btn-secondary" onclick="toggleUserExpand('${escAttr(u.id)}')">Abbrechen</button>
        <span id="uf-${escAttr(u.id)}-status" style="font-size:12px;color:var(--muted);"></span>
      </div>
      <!-- CLAUDE.md Inline-Editor -->
      <div style="margin-top:14px;border-top:1px solid var(--border);padding-top:12px;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
          <span style="font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;">CLAUDE.md</span>
          <button class="btn btn-secondary" style="font-size:11px;padding:3px 10px;"
            onclick="toggleUserClaudeMd('${escAttr(u.id)}')">✎ Bearbeiten</button>
          <button class="btn btn-secondary" style="font-size:11px;padding:3px 10px;"
            onclick="loadDefaultClaudeMd('${escAttr(u.id)}')">↺ Role Default laden</button>
          <span id="uf-${escAttr(u.id)}-md-status" style="font-size:11px;color:var(--muted);"></span>
        </div>
        <div id="uf-${escAttr(u.id)}-md-editor" style="display:none;">
          <textarea id="uf-${escAttr(u.id)}-md-content" spellcheck="false"
            style="width:100%;min-height:260px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:10px;font-family:var(--mono);font-size:12px;resize:vertical;"></textarea>
          <div style="display:flex;gap:8px;margin-top:8px;">
            <button class="btn btn-primary" onclick="saveUserClaudeMd('${escAttr(u.id)}')">CLAUDE.md speichern</button>
            <button class="btn btn-secondary" onclick="document.getElementById('uf-${escAttr(u.id)}-md-editor').style.display='none'">Schließen</button>
          </div>
        </div>
      </div>
    </div>
  </div>`;
}

async function loadUsers() {
  const list = document.getElementById('user-list');
  if (!cfg) await loadConfig();
  try {
    const r = await fetch('/api/users');
    const users = await r.json();
    if (!users.length) {
      list.innerHTML = '<div class="empty-state"><div class="icon">--</div><div>Noch keine User.</div></div>';
      return;
    }
    list.innerHTML = users.map(u => renderUserCard(u)).join('');
    // Auto-load HA users for expanded cards (none expanded on fresh load)
  } catch(e) {
    list.innerHTML = `<div class="empty-state"><div class="icon">!</div><div>${e.message}</div></div>`;
  }
}

function toggleUserExpand(uid) {
  const el  = document.getElementById(`user-expand-${uid}`);
  const btn = document.getElementById(`uedit-btn-${uid}`);
  if (!el) return;
  const open = el.style.display !== 'none';
  el.style.display = open ? 'none' : 'block';
  if (btn) btn.textContent = open ? '✎ Bearbeiten' : '▲ Schließen';
  if (!open) loadHaUsersForCard(uid);
}

async function loadHaUsersForCard(uid) {
  const sel    = document.getElementById(`uf-${uid}-ha`);
  const status = document.getElementById(`uf-${uid}-ha-status`);
  if (!sel) return;
  const currentVal = sel.value;
  try {
    const r = await fetch('/api/ha-users');
    const data = await r.json();
    if (data.ok && data.users.length > 0) {
      sel.innerHTML = '<option value="">– nicht zugeordnet –</option>' +
        data.users.map(u =>
          `<option value="${escAttr(u.id)}" ${u.id === currentVal ? 'selected' : ''}>${escHtml(u.display_name)} (${escHtml(u.id)})</option>`
        ).join('');
      if (status) { status.textContent = `${data.users.length} HA-User gefunden`; status.style.color = 'var(--green)'; }
    } else {
      if (status) { status.textContent = data.error || 'HA nicht konfiguriert'; status.style.color = 'var(--yellow)'; }
    }
  } catch(e) {
    if (status) { status.textContent = 'Fehler beim Laden'; status.style.color = 'var(--red)'; }
  }
}

async function saveUserEdit(uid) {
  const status = document.getElementById(`uf-${uid}-status`);
  const isVoice = ['voice','voice-advanced'].includes(document.getElementById(`uf-${uid}-role`)?.value || '');
  const body = {
    display_name:        document.getElementById(`uf-${uid}-name`)?.value?.trim(),
    role:                document.getElementById(`uf-${uid}-role`)?.value,
    primary_llm_slot:    parseInt(document.getElementById(`uf-${uid}-primary-llm`)?.value || '1'),
    extraction_llm_slot: parseInt(document.getElementById(`uf-${uid}-extract-llm`)?.value || '3'),
  };
  if (!isVoice) {
    body.ha_user        = document.getElementById(`uf-${uid}-ha`)?.value || '';
    body.whatsapp_phone = document.getElementById(`uf-${uid}-wa-phone`)?.value?.trim() || '';
  }
  if (status) { status.textContent = '…'; status.style.color = 'var(--muted)'; }
  try {
    const r = await fetch(`/api/users/${uid}`, {
      method: 'PATCH', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body),
    });
    const d = await r.json();
    if (r.ok && d.ok) {
      toast(`User ${uid} gespeichert ✓`, 'ok');
      loadUsers();
    } else {
      const err = d.detail || d.error || 'Unbekannter Fehler';
      if (status) { status.textContent = '✗ ' + err.substring(0,80); status.style.color = 'var(--red)'; }
      toast(err.substring(0,60), 'err');
    }
  } catch(e) {
    if (status) { status.textContent = '✗ ' + e.message; status.style.color = 'var(--red)'; }
  }
}

async function toggleUserClaudeMd(uid) {
  const editor = document.getElementById(`uf-${uid}-md-editor`);
  const status = document.getElementById(`uf-${uid}-md-status`);
  if (!editor) return;
  if (editor.style.display !== 'none') { editor.style.display = 'none'; return; }
  // Load current content
  try {
    const r = await fetch(`/api/claude-md/${uid}`);
    if (r.ok) {
      const d = await r.json();
      document.getElementById(`uf-${uid}-md-content`).value = d.content || '';
      editor.style.display = 'block';
    } else {
      if (status) { status.textContent = 'Nicht gefunden'; status.style.color = 'var(--yellow)'; }
    }
  } catch(e) {
    if (status) { status.textContent = e.message; status.style.color = 'var(--red)'; }
  }
}

async function loadDefaultClaudeMd(uid) {
  const status = document.getElementById(`uf-${uid}-md-status`);
  const role   = document.getElementById(`uf-${uid}-role`)?.value || 'user';
  const tpl    = role === 'admin' ? 'admin' : 'user';
  try {
    const r = await fetch(`/api/claude-md-template/${tpl}`);
    const d = await r.json();
    const editor  = document.getElementById(`uf-${uid}-md-editor`);
    const content = document.getElementById(`uf-${uid}-md-content`);
    if (content) content.value = d.content || '';
    if (editor)  editor.style.display = 'block';
    if (status)  { status.textContent = `Template "${d.template}" geladen`; status.style.color = 'var(--green)'; setTimeout(() => { status.textContent = ''; }, 3000); }
  } catch(e) {
    if (status) { status.textContent = e.message; status.style.color = 'var(--red)'; }
  }
}

async function saveUserClaudeMd(uid) {
  const status  = document.getElementById(`uf-${uid}-md-status`);
  const content = document.getElementById(`uf-${uid}-md-content`)?.value || '';
  try {
    const r = await fetch(`/api/claude-md/${uid}`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ content }),
    });
    const d = await r.json();
    if (d.ok) {
      toast(`CLAUDE.md für ${uid} gespeichert ✓`, 'ok');
      if (status) { status.textContent = '✓ Gespeichert'; status.style.color = 'var(--green)'; setTimeout(() => { status.textContent = ''; }, 3000); }
    } else {
      if (status) { status.textContent = '✗ Fehler'; status.style.color = 'var(--red)'; }
    }
  } catch(e) {
    if (status) { status.textContent = '✗ ' + e.message; status.style.color = 'var(--red)'; }
  }
}

function showNewUserCard() {
  document.getElementById('new-user-card').style.display = '';
  document.getElementById('nuf-id').focus();
}

async function submitNewUser() {
  const st  = document.getElementById('nuf-status');
  const uid = document.getElementById('nuf-id').value.trim();
  if (!uid) { st.textContent = '⚠ ID fehlt'; st.style.color = 'var(--yellow)'; return; }
  const payload = {
    id:           uid,
    display_name: document.getElementById('nuf-display-name').value.trim() || uid,
    role:         document.getElementById('nuf-role').value,
    claude_md_template: document.getElementById('nuf-template').value,
  };
  st.textContent = '…'; st.style.color = 'var(--muted)';
  try {
    const r = await fetch('/api/users', {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload),
    });
    const d = await r.json();
    if (r.ok && d.ok) {
      const cOk = d.container?.ok !== false;
      st.textContent = cOk ? `✓ Angelegt · Port :${d.user?.api_port}` : `⚠ Gespeichert, Container-Start fehlgeschlagen: ${(d.container?.error||'?').substring(0,60)}`;
      st.style.color = cOk ? 'var(--green)' : 'var(--yellow)';
      document.getElementById('new-user-card').style.display = 'none';
      toast('User angelegt ✓', 'ok');
      loadUsers();
    } else {
      const err = d.detail || d.error || 'Fehler';
      st.textContent = '✗ ' + err.substring(0,80); st.style.color = 'var(--red)';
    }
  } catch(e) { st.textContent = '✗ ' + e.message; st.style.color = 'var(--red)'; }
}

async function deleteUser(userId) {
  Modal.showDangerConfirm(`User "${userId}" wirklich löschen? Container wird gestoppt und entfernt.`, async () => {
    try {
      const r = await fetch(`/api/users/${userId}`, { method: 'DELETE' });
      const d = await r.json();
      if (d.ok) { toast('User gelöscht', 'ok'); loadUsers(); }
      else       { toast(d.detail || 'Fehler beim Löschen', 'err'); }
    } catch(e) { toast(e.message, 'err'); }
  });
}

async function restartUserContainer(userId) {
  const r = await fetch(`/api/users/${userId}/restart`, { method: 'POST' });
  const d = await r.json();
  if (d.ok) { toast(`Container für ${userId} neu gestartet ✓`, 'ok'); loadUsers(); }
  else       { toast(`Fehler: ${(d.container?.error || d.error || '?').substring(0,80)}`, 'err'); }
}

async function stopUserContainer(userId) {
  const r = await fetch(`/api/users/${userId}/stop`, { method: 'POST' });
  const d = await r.json();
  if (d.ok) { toast(`Container für ${userId} gestoppt`, 'ok'); loadUsers(); }
  else       { toast(`Fehler: ${(d.error || '?').substring(0,80)}`, 'err'); }
}
