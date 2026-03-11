# HAANA — KI-Haushaltsassistent

HAANA ist ein selbst-hostbarer KI-Assistent fuer Home Assistant mit persistentem Gedaechtnis,
Sprachsteuerung und WhatsApp-Integration. Er laeuft als Docker-Stack auf einem Proxmox LXC
und verbindet sich ueber ein leichtgewichtiges HA-Addon mit Home Assistant.

---

## Installation

### Schritt 1 — Proxmox LXC einrichten

Auf dem Proxmox-Host als root ausfuehren:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/alicezone/haana/main/install.sh)"
```

Das Skript:
- Erstellt ein Debian LXC
- Installiert Docker und Claude Code
- Deployt den HAANA-Stack
- Gibt am Ende einen Setup-Token aus — diesen notieren

### Schritt 2 — HA Companion Addon installieren

1. Home Assistant oeffnen → **Einstellungen → Add-ons → Add-on Store → Drei-Punkte-Menu → Repositories**
2. Repository-URL eintragen: `https://github.com/alicezone/haana`
3. Addon **"HAANA Companion"** installieren und starten
4. Konfiguration:
   - **HAANA-URL:** `http://<LXC-IP>:8080` (z.B. `http://192.168.1.100:8080`)
   - **Setup-Token:** aus Schritt 1

Das Addon bindet das HAANA Admin-Interface in die HA-Seitenleiste ein (via Ingress).

### Schritt 3 — Fertig

Admin-Interface direkt erreichbar unter: `http://<LXC-IP>:8080`

---

## HA Voice einrichten

In Home Assistant unter **Einstellungen → Voice Assistants** einen neuen Assistenten anlegen:

- **Spracherkennungs-Modell (STT):** Ollama-kompatible URL: `http://<LXC-IP>:11435`
- **Sprachausgabe (TTS):** nach Bedarf konfigurieren

HAANA verarbeitet die Anfragen und antwortet ueber die konfigurierte Voice Pipeline.

---

## Entwicklung

SSH in das LXC, dann Benutzer wechseln:

```bash
ssh root@<lxc-ip>
su - haana
# Claude Code startet automatisch in /opt/haana
```

Fuer Updates des Stacks (als root im LXC):

```bash
bash /opt/haana/update.sh
```

---

## Status

HAANA befindet sich in der **Beta-Phase**. Rueckmeldungen und Issues sind willkommen.
