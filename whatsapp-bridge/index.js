"use strict";

/**
 * HAANA WhatsApp Bridge
 *
 * Verbindet WhatsApp (Baileys) mit der HAANA Agent-API.
 * Unterstützt Multi-User-Routing: jede eingehende Nachricht wird anhand
 * der Absender-JID dem richtigen Agent-Container zugeordnet.
 *
 * Sicherheit: Nachrichten von unbekannten Nummern werden stillschweigend
 * ignoriert – nur konfigurierte User können die Brücke nutzen.
 *
 * Env-Vars:
 *   ADMIN_URL         Admin-Interface URL (default: http://admin-interface:8080)
 *   BRIDGE_LOG_LEVEL  pino log level (default: info)
 *   SESSION_DIR       Session-Verzeichnis (default: /app/session)
 */

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  isJidBroadcast,
  isJidGroup,
} = require("@whiskeysockets/baileys");

const qrcode = require("qrcode-terminal");
const fetch  = require("node-fetch");
const pino   = require("pino");
const path   = require("path");
const fs     = require("fs");

// ── Konfiguration ──────────────────────────────────────────────────────────

const ADMIN_URL   = (process.env.ADMIN_URL || "http://admin-interface:8080").replace(/\/$/, "");
const SESSION_DIR = path.resolve(process.env.SESSION_DIR || "/app/session");
const LOG_LEVEL   = process.env.BRIDGE_LOG_LEVEL || "info";

const log = pino({ level: LOG_LEVEL, transport: { target: "pino-pretty", options: { colorize: false } } });

// ── Routing-Tabelle ────────────────────────────────────────────────────────
// Map: sender-jid (normalized) → { agent_url, user_id }

let _routes     = new Map();  // jid → { agent_url, user_id }
let _waMode     = "separate";
let _selfPrefix = "!h ";

async function refreshConfig() {
  try {
    const r = await fetch(`${ADMIN_URL}/api/whatsapp-config`, { timeout: 5000 });
    if (!r.ok) {
      log.warn({ status: r.status }, "whatsapp-config konnte nicht geladen werden");
      return;
    }
    const data = await r.json();

    const newRoutes = new Map();
    for (const route of (data.routes || [])) {
      // Normalize JID: strip device-suffix if present (e.g. "49xxx@s.whatsapp.net:1" → "49xxx@s.whatsapp.net")
      const jid = normalizeJid(route.jid);
      if (jid) newRoutes.set(jid, { agent_url: route.agent_url, user_id: route.user_id });
    }
    _routes     = newRoutes;
    _waMode     = data.mode       || "separate";
    _selfPrefix = data.self_prefix || "!h ";
    log.info({ routes: _routes.size, mode: _waMode }, "WhatsApp-Routing aktualisiert");
  } catch (e) {
    log.warn({ err: e.message }, "Routing-Refresh fehlgeschlagen");
  }
}

function normalizeJid(jid) {
  if (!jid) return null;
  // Strip device suffix: "491234@s.whatsapp.net:5" → "491234@s.whatsapp.net"
  return jid.split(":")[0];
}

// ── Agent-Anfrage ──────────────────────────────────────────────────────────

async function queryAgent(agentUrl, message, channel = "whatsapp") {
  const url = `${agentUrl}/chat`;
  log.debug({ url, message: message.slice(0, 80) }, "Agent-Anfrage");

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, channel }),
    timeout: 120_000,
  });

  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`Agent HTTP ${res.status}: ${txt.slice(0, 200)}`);
  }

  const json = await res.json();
  return json.response || "[Keine Antwort]";
}

// ── Nachrichtentext extrahieren ────────────────────────────────────────────

function extractText(msg) {
  const m = msg.message;
  if (!m) return null;
  if (m.conversation) return m.conversation;
  if (m.extendedTextMessage?.text) return m.extendedTextMessage.text;
  if (m.imageMessage?.caption) return m.imageMessage.caption;
  if (m.audioMessage) return "[Sprachnachricht – wird noch nicht unterstützt]";
  if (m.documentMessage?.caption) return m.documentMessage.caption;
  return null;
}

// ── Haupt-Loop ─────────────────────────────────────────────────────────────

async function startBridge() {
  if (!fs.existsSync(SESSION_DIR)) {
    fs.mkdirSync(SESSION_DIR, { recursive: true });
  }

  // Initiales Routing laden
  await refreshConfig();
  // Alle 5 Minuten aktualisieren
  setInterval(refreshConfig, 5 * 60 * 1000);

  const { version } = await fetchLatestBaileysVersion();
  log.info({ version }, "Baileys Version");

  const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);

  const sock = makeWASocket({
    version,
    auth: state,
    logger: pino({ level: "silent" }),
    printQRInTerminal: false,
    browser: ["HAANA", "Chrome", "1.0.0"],
    generateHighQualityLinkPreview: false,
    markOnlineOnConnect: false,
  });

  sock.ev.on("creds.update", saveCreds);

  // ── Verbindungsstatus ────────────────────────────────────────────────────

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log("\n\n========================================");
      console.log("  HAANA WhatsApp – QR-Code scannen:");
      console.log("========================================\n");
      qrcode.generate(qr, { small: true });
      console.log("\n(QR-Code verfällt nach ~60 Sekunden – bei Timeout neu starten)\n");
    }

    if (connection === "open") {
      const jid = sock.user?.id || "?";
      log.info({ jid }, "WhatsApp verbunden");
    }

    if (connection === "close") {
      const code   = lastDisconnect?.error?.output?.statusCode;
      const reason = Object.keys(DisconnectReason).find((k) => DisconnectReason[k] === code);
      const logout = code === DisconnectReason.loggedOut;

      log.warn({ code, reason }, "Verbindung getrennt");

      if (logout) {
        log.error("Session ungültig (ausgeloggt). Session löschen und neu starten.");
        fs.rmSync(SESSION_DIR, { recursive: true, force: true });
        process.exit(1);
      } else {
        log.info("Verbinde in 5 Sekunden neu...");
        setTimeout(startBridge, 5_000);
      }
    }
  });

  // ── Eingehende Nachrichten ───────────────────────────────────────────────

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;

    for (const msg of messages) {
      // Eigene Nachrichten und Broadcasts ignorieren
      if (msg.key.fromMe)                        continue;
      if (isJidBroadcast(msg.key.remoteJid))     continue;
      if (isJidGroup(msg.key.remoteJid))          continue;

      const from         = msg.key.remoteJid;
      const fromNorm     = normalizeJid(from);
      let   text         = extractText(msg);

      if (!text) {
        log.debug({ from, type: Object.keys(msg.message || {}) }, "Kein verarbeitbarer Text – ignoriert");
        continue;
      }

      // ── Sicherheitsfilter: nur bekannte Nummern ──────────────────────────
      if (_routes.size === 0) {
        // Keine Routen konfiguriert → alle ignorieren (fail-safe)
        log.warn({ from }, "Keine Routen konfiguriert – Nachricht ignoriert");
        continue;
      }

      const route = _routes.get(fromNorm);
      if (!route) {
        log.warn({ from: fromNorm }, "Unbekannte Nummer – Nachricht ignoriert (Sicherheitsfilter)");
        continue;
      }

      // ── Selbst-Modus: Prefix prüfen ──────────────────────────────────────
      if (_waMode === "self") {
        if (!text.startsWith(_selfPrefix)) {
          log.debug({ from, prefix: _selfPrefix }, "Selbst-Modus: kein Prefix – ignoriert");
          continue;
        }
        text = text.slice(_selfPrefix.length).trim();
      }

      log.info({ from: fromNorm, user: route.user_id, text: text.slice(0, 100) }, "Eingehende Nachricht");

      await sock.sendPresenceUpdate("composing", from);

      try {
        const response = await queryAgent(route.agent_url, text, "whatsapp");
        log.info({ from: fromNorm, response: response.slice(0, 100) }, "Agent-Antwort");
        await sock.sendMessage(from, { text: response });
      } catch (err) {
        log.error({ err: err.message, from, agent: route.agent_url }, "Fehler bei Agent-Anfrage");
        await sock.sendMessage(from, {
          text: "Entschuldigung, ich konnte deine Nachricht gerade nicht verarbeiten. Versuch es nochmal.",
        });
      } finally {
        await sock.sendPresenceUpdate("paused", from);
      }
    }
  });
}

// ── Start ──────────────────────────────────────────────────────────────────

log.info({ adminUrl: ADMIN_URL, sessionDir: SESSION_DIR }, "HAANA WhatsApp Bridge startet");

startBridge().catch((err) => {
  log.error({ err: err.message }, "Fataler Fehler – Bridge beendet");
  process.exit(1);
});
