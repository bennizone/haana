"use strict";

/**
 * HAANA WhatsApp Bridge
 *
 * Verbindet WhatsApp (Baileys) mit der HAANA Agent-API.
 *
 * Beim ersten Start: QR-Code in stdout ausgeben → scannen → Session wird
 * in /app/session persistiert und überlebt Container-Restarts.
 *
 * Env-Vars:
 *   AGENT_URL_BENNI   Agent-API URL  (default: http://instanz-alice:8001)
 *   BRIDGE_LOG_LEVEL  pino log level (default: info)
 *   BRIDGE_OWNER_JID  Alices WhatsApp-JID (z.B. 4917612345678@s.whatsapp.net)
 *                     Optional – nur für Logging / künftige Filterung
 */

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  isJidBroadcast,
  isJidGroup,
  downloadMediaMessage,
} = require("@whiskeysockets/baileys");

const qrcode   = require("qrcode-terminal");
const fetch    = require("node-fetch");
const pino     = require("pino");
const path     = require("path");
const fs       = require("fs");

// ── Konfiguration ──────────────────────────────────────────────────────────

const AGENT_URL   = (process.env.AGENT_URL_BENNI || "http://instanz-alice:8001").replace(/\/$/, "");
const SESSION_DIR = path.resolve(process.env.SESSION_DIR || "/app/session");
const LOG_LEVEL   = process.env.BRIDGE_LOG_LEVEL || "info";
const OWNER_JID   = process.env.BRIDGE_OWNER_JID || null; // optional

const log = pino({ level: LOG_LEVEL, transport: { target: "pino-pretty", options: { colorize: false } } });

// ── Hilfsfunktionen ────────────────────────────────────────────────────────

/**
 * Sendet eine Textnachricht an die Agent-API und gibt die Antwort zurück.
 */
async function queryAgent(message, channel = "whatsapp") {
  const url = `${AGENT_URL}/chat`;
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

/**
 * Extrahiert den Text aus einer eingehenden Nachricht.
 * Gibt null zurück wenn kein verarbeitbarer Inhalt vorhanden ist.
 */
function extractText(msg) {
  const m = msg.message;
  if (!m) return null;

  // Normaler Text
  if (m.conversation) return m.conversation;
  if (m.extendedTextMessage?.text) return m.extendedTextMessage.text;

  // Bild mit Caption
  if (m.imageMessage?.caption) return m.imageMessage.caption;

  // Sprachnachricht → Platzhalter bis STT in Phase 2 kommt
  if (m.audioMessage) return "[Sprachnachricht – wird noch nicht unterstützt]";

  // Dokument mit Caption
  if (m.documentMessage?.caption) return m.documentMessage.caption;

  return null;
}

// ── Haupt-Loop ─────────────────────────────────────────────────────────────

async function startBridge() {
  if (!fs.existsSync(SESSION_DIR)) {
    fs.mkdirSync(SESSION_DIR, { recursive: true });
  }

  const { version } = await fetchLatestBaileysVersion();
  log.info({ version }, "Baileys Version");

  const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);

  const sock = makeWASocket({
    version,
    auth: state,
    logger: pino({ level: "silent" }), // Baileys intern stumm schalten
    printQRInTerminal: false,           // wir machen das selbst (größer + lesbarer)
    browser: ["HAANA", "Chrome", "1.0.0"],
    generateHighQualityLinkPreview: false,
    markOnlineOnConnect: false,
  });

  // Credentials nach jedem Update speichern
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
      if (OWNER_JID && !jid.startsWith(OWNER_JID.split("@")[0])) {
        log.warn({ jid, expected: OWNER_JID }, "Verbundene Nummer weicht von BRIDGE_OWNER_JID ab");
      }
    }

    if (connection === "close") {
      const code    = lastDisconnect?.error?.output?.statusCode;
      const reason  = Object.keys(DisconnectReason).find((k) => DisconnectReason[k] === code);
      const logout  = code === DisconnectReason.loggedOut;

      log.warn({ code, reason }, "Verbindung getrennt");

      if (logout) {
        log.error("Session ungültig (ausgeloggt). Session löschen und neu starten.");
        // Session löschen damit beim nächsten Start ein neuer QR-Code erscheint
        fs.rmSync(SESSION_DIR, { recursive: true, force: true });
        process.exit(1);
      } else {
        // Kurz warten, dann neu verbinden
        log.info("Verbinde in 5 Sekunden neu...");
        setTimeout(startBridge, 5_000);
      }
    }
  });

  // ── Eingehende Nachrichten ───────────────────────────────────────────────

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;

    for (const msg of messages) {
      // Eigene Nachrichten und Status-Broadcasts ignorieren
      if (msg.key.fromMe)          continue;
      if (isJidBroadcast(msg.key.remoteJid)) continue;
      if (isJidGroup(msg.key.remoteJid))     continue;

      const from = msg.key.remoteJid;
      const text = extractText(msg);

      if (!text) {
        log.debug({ from, type: Object.keys(msg.message || {}) }, "Nachricht ohne verarbeitbaren Text – ignoriert");
        continue;
      }

      log.info({ from, text: text.slice(0, 100) }, "Eingehende Nachricht");

      // "Tippen..." anzeigen während Agent antwortet
      await sock.sendPresenceUpdate("composing", from);

      try {
        const response = await queryAgent(text, "whatsapp");
        log.info({ from, response: response.slice(0, 100) }, "Agent-Antwort");

        await sock.sendMessage(from, { text: response });
      } catch (err) {
        log.error({ err: err.message, from }, "Fehler bei Agent-Anfrage");
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

log.info({ agentUrl: AGENT_URL, sessionDir: SESSION_DIR }, "HAANA WhatsApp Bridge startet");

startBridge().catch((err) => {
  log.error({ err: err.message }, "Fataler Fehler – Bridge beendet");
  process.exit(1);
});
