// security.js – Passwort-Aenderung (v2)

async function changePassword() {
  const newEl     = document.getElementById('sec-new-password');
  const confirmEl = document.getElementById('sec-confirm-password');
  const statusEl  = document.getElementById('save-status-security');

  const newPassword     = newEl     ? newEl.value     : '';
  const confirmPassword = confirmEl ? confirmEl.value : '';

  if (!newPassword || newPassword.length < 8) {
    toast(t('auth.password_min_length'), 'err');
    return;
  }

  if (newPassword !== confirmPassword) {
    toast(t('auth.password_mismatch'), 'err');
    return;
  }

  try {
    const r = await fetch('/api/auth/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_password: newPassword }),
    });

    if (r.ok) {
      if (newEl)     newEl.value     = '';
      if (confirmEl) confirmEl.value = '';
      toast(t('auth.password_changed'), 'ok');
      if (statusEl) {
        statusEl.textContent = t('auth.password_changed');
        statusEl.style.color = 'var(--green)';
        setTimeout(() => { statusEl.textContent = ''; }, 3000);
      }
    } else {
      let msg = t('auth.password_change_error');
      try {
        const d = await r.json();
        if (d.detail) msg = d.detail;
      } catch(_) {}
      toast(msg, 'err');
      if (statusEl) {
        statusEl.textContent = msg;
        statusEl.style.color = 'var(--red)';
        setTimeout(() => { statusEl.textContent = ''; }, 4000);
      }
    }
  } catch(e) {
    toast(t('auth.password_change_error') + ': ' + e.message, 'err');
  }
}
