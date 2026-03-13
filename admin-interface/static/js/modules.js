// modules.js – Dynamische Module (Channels/Skills): Config-Tabs, Skills-Tab, User-Felder (v1)

let _modulesData = null; // Cache für GET /api/modules

async function _loadModules() {
  if (_modulesData) return _modulesData;
  try {
    const r = await fetch('/api/modules');
    _modulesData = await r.json();
  } catch(e) {
    _modulesData = {channels: [], skills: []};
  }
  return _modulesData;
}

// ── Config-Sub-Tabs für Module ─────────────────────────────────────────────

async function loadModuleConfigTabs() {
  const [modules, modCfg] = await Promise.all([
    _loadModules(),
    fetch('/api/modules/config').then(r => r.json()).catch(() => ({}))
  ]);

  const tabsEl = document.querySelector('.cfg-tabs');
  if (!tabsEl) return;

  // Channels mit config_schema > 0
  for (const ch of (modules.channels || [])) {
    if ((!ch.config_schema || ch.config_schema.length === 0) && !ch.custom_tab_html) continue;
    const tabId = 'mod-' + ch.id;
    if (document.getElementById('cfgtab-' + tabId)) continue;

    const btn = document.createElement('button');
    btn.className = 'cfg-tab-btn';
    btn.id = 'cfgtab-' + tabId;
    btn.textContent = ch.display_name;
    btn.onclick = () => showCfgTab(tabId);
    tabsEl.appendChild(btn);

    const panel = document.createElement('div');
    panel.id = 'cfgpanel-' + tabId;
    panel.className = 'cfg-tab-panel';
    panel.style.display = 'none';

    const vals = modCfg[ch.id] || {};
    const customHtml = ch.custom_tab_html || '';
    const fieldsHtml = (ch.config_schema && ch.config_schema.length > 0)
      ? _renderModuleConfigFields(ch.id, ch.display_name, ch.config_schema, vals, false)
      : '';
    panel.innerHTML = customHtml + fieldsHtml;
    const parentEl = tabsEl.closest('.panel') || tabsEl.parentElement;
    parentEl.appendChild(panel);
  }

  // Skills mit config_schema > 0
  let skillSeparatorAdded = false;
  for (const sk of (modules.skills || [])) {
    if (!sk.config_schema || sk.config_schema.length === 0) continue;
    const tabId = 'mod-' + sk.id;
    if (document.getElementById('cfgtab-' + tabId)) continue;

    if (!skillSeparatorAdded) {
      const sep = document.createElement('span');
      sep.className = 'cfg-tab-separator';
      sep.style.cssText = 'display:inline-block;width:1px;background:var(--border);margin:4px 4px;align-self:stretch;';
      tabsEl.appendChild(sep);
      skillSeparatorAdded = true;
    }

    const btn = document.createElement('button');
    btn.className = 'cfg-tab-btn';
    btn.id = 'cfgtab-' + tabId;
    btn.textContent = sk.display_name;
    btn.onclick = () => showCfgTab(tabId);
    tabsEl.appendChild(btn);

    const panel = document.createElement('div');
    panel.id = 'cfgpanel-' + tabId;
    panel.className = 'cfg-tab-panel';
    panel.style.display = 'none';

    const vals = modCfg[sk.id] || {};
    panel.innerHTML = _renderModuleConfigFields(sk.id, sk.display_name, sk.config_schema, vals, true);
    tabsEl.parentElement.appendChild(panel);
  }
}

function _renderModuleConfigFields(modId, displayName, fields, vals, isSkill) {
  const kind = isSkill ? t('modules.kind_skill') : t('modules.kind_channel');
  let html = `<div style="margin-bottom:16px;">
    <span style="font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;">${escHtml(kind)}: ${escHtml(displayName)}</span>
  </div>`;

  for (const f of fields) {
    const val = vals[f.key] !== undefined ? vals[f.key] : (f.default || '');
    const labelText = escHtml(f.label_de || f.label);
    const hintText = f.hint_de || f.hint;
    const fieldId = `modcfg-${modId}-${f.key}`;

    html += `<div class="form-group" style="margin-bottom:12px;">
      <label for="${escAttr(fieldId)}">${labelText}${f.required ? ' <span style="color:var(--red);">*</span>' : ''}</label>`;

    if (f.field_type === 'toggle') {
      html += `<input type="checkbox" id="${escAttr(fieldId)}" ${val ? 'checked' : ''}>`;
    } else if (f.field_type === 'select') {
      html += `<select id="${escAttr(fieldId)}">`;
      for (const opt of (f.options || [])) {
        const o = typeof opt === 'string' ? {value: opt, label: opt} : opt;
        html += `<option value="${escAttr(o.value)}" ${o.value == val ? 'selected' : ''}>${escHtml(o.label || o.value)}</option>`;
      }
      html += `</select>`;
    } else {
      const type = f.field_type === 'password' ? 'password' : f.field_type === 'number' ? 'number' : 'text';
      html += `<input type="${type}" id="${escAttr(fieldId)}" value="${escAttr(String(val))}">`;
    }

    if (hintText) {
      html += `<span class="form-hint">${escHtml(hintText)}</span>`;
    }
    html += `</div>`;
  }

  html += `<div style="display:flex;gap:8px;margin-top:12px;">
    <button class="btn btn-primary" onclick="saveModuleConfig('${escAttr(modId)}')">${t('common.save')}</button>
    <span id="modcfg-${escAttr(modId)}-status" style="font-size:12px;color:var(--muted);align-self:center;"></span>
  </div>`;

  return html;
}

async function saveModuleConfig(modId) {
  const statusEl = document.getElementById(`modcfg-${modId}-status`);
  try {
    const modules = await _loadModules();
    const allModules = [...(modules.channels || []), ...(modules.skills || [])];
    const mod = allModules.find(m => m.id === modId);
    if (!mod) return;

    const data = {};
    for (const f of (mod.config_schema || [])) {
      const fieldId = `modcfg-${modId}-${f.key}`;
      const el = document.getElementById(fieldId);
      if (!el) continue;
      data[f.key] = f.field_type === 'toggle' ? el.checked : el.value;
    }

    const r = await fetch('/api/modules/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({[modId]: data})
    });
    const res = await r.json();
    if (res.ok) {
      if (statusEl) { statusEl.textContent = t('common.saved'); statusEl.style.color = 'var(--green)'; }
      _modulesData = null;
    } else {
      if (statusEl) { statusEl.textContent = res.error || t('common.error'); statusEl.style.color = 'var(--red)'; }
    }
  } catch(e) {
    if (statusEl) { statusEl.textContent = e.message; statusEl.style.color = 'var(--red)'; }
  }
}

// ── Skills-Haupttab ────────────────────────────────────────────────────────

async function loadSkillsTab() {
  const list = document.getElementById('skills-list');
  if (!list) return;
  try {
    const modules = await _loadModules();
    const skills = (modules.skills || []);
    if (!skills.length) {
      list.innerHTML = `<div class="empty-state"><div class="icon">\u2014</div><div>${t('skills.no_skills')}</div></div>`;
      return;
    }

    const tabBtn = document.getElementById('tab-btn-skills');
    if (tabBtn) tabBtn.style.display = '';

    list.innerHTML = skills.map(sk => {
      const isActive = sk.enabled;
      const statusColor = isActive ? 'var(--green)' : 'var(--muted)';
      const statusText = isActive ? t('skills.active') : t('skills.inactive');
      const fieldCount = (sk.config_fields || 0) + (sk.user_config_fields || 0);
      const toolsText = `${fieldCount} ${t('skills.tools_count')}`;
      return `<div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:12px;opacity:${isActive ? 1 : 0.6};">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
          <span style="font-weight:600;">${escHtml(sk.display_name)}</span>
          <span style="font-size:11px;background:rgba(96,165,250,.15);color:var(--blue);border-radius:4px;padding:1px 6px;">${escHtml(sk.id)}</span>
          <span style="font-size:11px;color:${statusColor};margin-left:auto;">${statusText}</span>
        </div>
        <div style="font-size:12px;color:var(--muted);">${escHtml(toolsText)}</div>
        ${!isActive ? `<div style="font-size:11px;color:var(--yellow);margin-top:6px;">${t('skills.config_missing')}</div>` : ''}
      </div>`;
    }).join('');
  } catch(e) {
    if (list) list.innerHTML = `<div class="empty-state"><div class="icon">!</div><div>${escHtml(e.message)}</div></div>`;
  }
}

// ── Dynamische User-Karten-Felder ──────────────────────────────────────────

async function loadModuleUserFields(uid, userData) {
  const expandEl = document.getElementById(`user-expand-${uid}`);
  if (!expandEl) return;

  if (expandEl.dataset.modulesLoaded) return;

  try {
    const modules = await _loadModules();
    const allModules = [...(modules.channels || []), ...(modules.skills || [])];

    let html = '';
    for (const mod of allModules) {
      if (!mod.user_config_schema || mod.user_config_schema.length === 0) continue;

      let sectionHtml = '';
      for (const f of mod.user_config_schema) {
        const fieldId = `uf-${uid}-modfield-${f.key}`;
        if (document.getElementById(fieldId)) continue;

        const val = (userData && userData[f.key] !== undefined) ? userData[f.key] : (f.default || '');
        const labelText = escHtml(f.label_de || f.label);
        const hintText = f.hint_de || f.hint;

        sectionHtml += `<div class="form-group" style="margin-bottom:10px;">
          <label for="${escAttr(fieldId)}">${labelText}${f.required ? ' <span style="color:var(--red);">*</span>' : ''}</label>`;

        if (f.field_type === 'toggle') {
          sectionHtml += `<input type="checkbox" id="${escAttr(fieldId)}" ${val ? 'checked' : ''}>`;
        } else if (f.field_type === 'select') {
          sectionHtml += `<select id="${escAttr(fieldId)}">`;
          for (const opt of (f.options || [])) {
            const o = typeof opt === 'string' ? {value: opt, label: opt} : opt;
            sectionHtml += `<option value="${escAttr(o.value)}" ${o.value == val ? 'selected' : ''}>${escHtml(o.label || o.value)}</option>`;
          }
          sectionHtml += `</select>`;
        } else {
          const type = f.field_type === 'password' ? 'password' : f.field_type === 'number' ? 'number' : 'text';
          sectionHtml += `<input type="${type}" id="${escAttr(fieldId)}" value="${escAttr(String(val || ''))}">`;
        }

        if (hintText) {
          sectionHtml += `<span class="form-hint">${escHtml(hintText)}</span>`;
        }
        sectionHtml += `</div>`;
      }

      if (sectionHtml) {
        html += `<div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border);">
          <div style="font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px;">${escHtml(mod.display_name)}</div>
          ${sectionHtml}
        </div>`;
      }
    }

    if (html) {
      const saveBtn = expandEl.querySelector('.btn.btn-primary');
      if (saveBtn) {
        const insertTarget = saveBtn.closest('div[style*="display:flex"]') || saveBtn.parentElement;
        insertTarget.insertAdjacentHTML('beforebegin', html);
      } else {
        expandEl.insertAdjacentHTML('beforeend', html);
      }
    }

    expandEl.dataset.modulesLoaded = '1';
  } catch(e) {
    console.warn('loadModuleUserFields:', e);
  }
}

// Skills-Tab-Button einblenden beim App-Start
function initSkillsTabVisibility() {
  _loadModules().then(data => {
    if ((data.skills || []).length > 0) {
      const tabBtn = document.getElementById('tab-btn-skills');
      if (tabBtn) tabBtn.style.display = '';
    }
  }).catch(() => {});
}
