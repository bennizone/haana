// whatsapp.js – Bridge-Status, QR-Code polling, Disconnect

let _waPolling = null;

async function refreshWaStatus() {
  const dot   = document.getElementById('wa-status-dot');
  const txt   = document.getElementById('wa-status-text');
  const info  = document.getElementById('wa-account-info');
  const qrBox = document.getElementById('wa-qr-container');
  const offl  = document.getElementById('wa-offline-info');
  const logoutBtn = document.getElementById('wa-logout-btn');

  try {
    const r = await fetch('/api/whatsapp-status');
    const d = await r.json();

    info.style.display  = 'none';
    qrBox.style.display = 'none';
    offl.style.display  = 'none';
    logoutBtn.style.display = 'none';

    if (d.status === 'connected') {
      dot.style.background = 'var(--accent)';
      txt.textContent = 'Verbunden';
      if (d.account_name || d.account_jid) {
        document.getElementById('wa-account-name').textContent = d.account_name || '–';
        document.getElementById('wa-account-jid').textContent  = d.account_jid  || '–';
        info.style.display = 'block';
      }
      logoutBtn.style.display = 'inline-block';
      stopWaPolling();
    } else if (d.status === 'qr') {
      dot.style.background = '#f59e0b';
      txt.textContent = 'Warte auf QR-Code Scan...';
      // QR-Code laden
      const qr = await fetch('/api/whatsapp-qr');
      const qd = await qr.json();
      if (qd.qr) {
        document.getElementById('wa-qr-img').src = qd.qr;
        qrBox.style.display = 'block';
      }
      startWaPolling();
    } else if (d.status === 'offline') {
      dot.style.background = '#888';
      txt.textContent = 'Bridge offline';
      offl.style.display = 'block';
      stopWaPolling();
    } else {
      dot.style.background = '#ef4444';
      txt.textContent = 'Nicht verbunden';
      startWaPolling();
    }
  } catch (e) {
    dot.style.background = '#888';
    txt.textContent = 'Bridge nicht erreichbar';
    offl.style.display = 'block';
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
  Modal.showDangerConfirm('WhatsApp-Session wirklich trennen? Du musst danach den QR-Code erneut scannen.', async () => {
    const r = await fetch('/api/whatsapp-logout', { method: 'POST' });
    const d = await r.json();
    if (d.ok) {
      toast('WhatsApp getrennt – QR-Code erscheint gleich', 'ok');
      setTimeout(refreshWaStatus, 3000);
    } else {
      toast('Fehler: ' + (d.error || 'Unbekannt'), 'err');
    }
  });
}
