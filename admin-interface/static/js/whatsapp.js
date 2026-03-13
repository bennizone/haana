// whatsapp.js – Bridge-Status, QR-Code polling, Disconnect

let _waPolling = null;

async function refreshWaStatus() {
  const dot   = document.getElementById('wa-status-dot');
  const txt   = document.getElementById('wa-status-text');
  const info  = document.getElementById('wa-account-info');
  const qrBox = document.getElementById('wa-qr-container');
  const offl  = document.getElementById('wa-offline-info');
  const logoutBtn = document.getElementById('wa-logout-btn');

  // Pflicht-Elemente prüfen — WA-Sektion evtl. nicht im DOM
  if (!dot || !txt || !offl || !info || !qrBox || !logoutBtn) return;

  try {
    const r = await fetch('/api/whatsapp-status');
    const d = await r.json();

    info.style.display  = 'none';
    qrBox.style.display = 'none';
    offl.style.display  = 'none';
    logoutBtn.style.display = 'none';

    const stopBtn  = document.getElementById('wa-stop-btn');
    const startBtn = document.getElementById('wa-start-btn');

    if (d.status === 'connected') {
      dot.style.background = 'var(--accent)';
      txt.textContent = t('whatsapp.connected');
      if (d.account_name || d.account_jid) {
        document.getElementById('wa-account-name').textContent = d.account_name || '–';
        document.getElementById('wa-account-jid').textContent  = d.account_jid  || '–';
        info.style.display = 'block';
      }
      logoutBtn.style.display = 'inline-block';
      if (stopBtn)  stopBtn.style.display  = 'inline-block';
      if (startBtn) startBtn.style.display = 'none';
      stopWaPolling();
    } else if (d.status === 'qr') {
      dot.style.background = '#f59e0b';
      txt.textContent = t('whatsapp.waiting_qr');
      // QR-Code laden
      const qr = await fetch('/api/whatsapp-qr');
      const qd = await qr.json();
      if (qd.qr) {
        document.getElementById('wa-qr-img').src = qd.qr;
        qrBox.style.display = 'block';
      }
      if (stopBtn)  stopBtn.style.display  = 'inline-block';
      if (startBtn) startBtn.style.display = 'none';
      startWaPolling();
    } else if (d.status === 'offline') {
      dot.style.background = '#888';
      txt.textContent = t('whatsapp.bridge_offline');
      offl.style.display = 'block';
      if (stopBtn)  stopBtn.style.display  = 'none';
      if (startBtn) startBtn.style.display = '';
      stopWaPolling();
    } else {
      dot.style.background = '#ef4444';
      txt.textContent = t('whatsapp.not_connected');
      if (stopBtn)  stopBtn.style.display  = 'inline-block';
      if (startBtn) startBtn.style.display = 'none';
      startWaPolling();
    }
  } catch (e) {
    dot.style.background = '#888';
    txt.textContent = t('whatsapp.bridge_unreachable');
    offl.style.display = 'block';
    const stopBtn  = document.getElementById('wa-stop-btn');
    const startBtn = document.getElementById('wa-start-btn');
    if (stopBtn)  stopBtn.style.display  = 'none';
    if (startBtn) startBtn.style.display = '';
    stopWaPolling();
  }
}

function startWaPolling() {
  if (_waPolling) return;
  _waPolling = setInterval(refreshWaStatus, 3000);
}

function stopWaPolling() {
  if (_waPolling) { clearInterval(_waPolling); _waPolling = null; }
}

async function waLogout() {
  Modal.showDangerConfirm(t('whatsapp.disconnect_confirm'), async () => {
    const r = await fetch('/api/whatsapp-logout', { method: 'POST' });
    const d = await r.json();
    if (d.ok) {
      toast(t('whatsapp.disconnected'), 'ok');
      setTimeout(refreshWaStatus, 3000);
    } else {
      toast(t('whatsapp.error') + ': ' + (d.error || t('whatsapp.unknown')), 'err');
    }
  });
}

async function waBridgeStart() {
  const btn = document.getElementById('wa-start-btn');
  if (btn) { btn.disabled = true; btn.textContent = t('whatsapp.starting') || '…'; }
  try {
    const r = await fetch('/api/whatsapp/start', { method: 'POST' });
    if (!r.ok) throw new Error(await r.text());
    // Polling starten, Bridge braucht ~5s zum Hochfahren
    startWaPolling();
  } catch(e) {
    toast(e.message || t('whatsapp.error'), 'error');
    if (btn) { btn.disabled = false; btn.textContent = t('whatsapp.start_bridge') || 'Bridge starten'; }
  }
}

async function waBridgeStop() {
  if (!confirm(t('whatsapp.stop_confirm') || 'Bridge wirklich stoppen?')) return;
  const btn = document.getElementById('wa-stop-btn');
  if (btn) { btn.disabled = true; btn.textContent = t('whatsapp.stopping') || '…'; }
  try {
    const r = await fetch('/api/whatsapp/stop', { method: 'POST' });
    if (!r.ok) throw new Error(await r.text());
    setTimeout(() => refreshWaStatus(), 2000);
  } catch(e) {
    toast(e.message || t('whatsapp.error'), 'error');
    if (btn) { btn.disabled = false; btn.textContent = t('whatsapp.stop_bridge') || 'Bridge stoppen'; }
  }
}
