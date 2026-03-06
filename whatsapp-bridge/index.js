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
 * HTTP-API (Port 3001):
 *   GET  /status  → Verbindungsstatus + Account-Info
 *   GET  /qr      → aktueller QR-Code als Base64 Data-URL (PNG)
 *   POST /logout   → Session trennen, Daten löschen
 *
 * Env-Vars:
 *   ADMIN_URL         Admin-Interface URL (default: http://admin-interface:8080)
 *   BRIDGE_LOG_LEVEL  pino log level (default: info)
 *   SESSION_DIR       Session-Verzeichnis (default: /app/session)
 *   BRIDGE_HTTP_PORT  HTTP-API Port (default: 3001)
 */

const {
  default: makeWASocket,
  useMultiFileAuthState,
  makeCacheableSignalKeyStore,
  DisconnectReason,
  fetchLatestBaileysVersion,
  isJidBroadcast,
  isJidGroup,
  downloadMediaMessage,
} = require("@whiskeysockets/baileys");

const http     = require("http");
const qrcode   = require("qrcode");
const qrTerm   = require("qrcode-terminal");
const fetch    = require("node-fetch");
const pino     = require("pino");
const path     = require("path");
const fs       = require("fs");

// ── Konfiguration ──────────────────────────────────────────────────────────

const ADMIN_URL   = (process.env.ADMIN_URL || "http://admin-interface:8080").replace(/\/$/, "");
const SESSION_DIR = path.resolve(process.env.SESSION_DIR || "/app/session");
const LOG_LEVEL   = process.env.BRIDGE_LOG_LEVEL || "info";
const HTTP_PORT   = parseInt(process.env.BRIDGE_HTTP_PORT || "3001", 10);

const log = pino({ level: LOG_LEVEL, transport: { target: "pino-pretty", options: { colorize: false } } });

// ── Bridge State ────────────────────────────────────────────────────────────

let _status      = "disconnected"; // "disconnected" | "qr" | "connected"
let _qrDataUrl   = null;           // Base64 Data-URL des aktuellen QR-Codes
let _accountJid  = null;           // JID des verbundenen Accounts
let _accountName = null;           // Push-Name des Accounts
let _sock        = null;           // aktuelle Baileys-Socket-Instanz

// ── Routing-Tabelle ────────────────────────────────────────────────────────
// Map: sender-jid (normalized) → { agent_url, user_id }

let _routes     = new Map();
let _waMode     = "separate";
let _selfPrefix = "!h ";

// ── STT/TTS-Konfiguration (Home Assistant) ───────────────────────────────
let _sttConfig  = null; // { ha_url, ha_token, stt_entity, stt_language }
let _ttsConfig  = null; // { ha_url, ha_token, tts_entity, tts_language }

// ── LID → Phone Mapping ───────────────────────────────────────────────────
// Neuere WhatsApp-Versionen senden LID (Linked ID) statt phone@s.whatsapp.net.
// Strategie nach NanoClaw: lokaler Cache + signalRepository.lidMapping Fallback.
const _lidToPhone = {};  // lidUser → "491XXXXXXXXX@s.whatsapp.net"

async function translateJid(jid, sock) {
  if (!jid.endsWith("@lid")) return jid;
  const lidUser = jid.split("@")[0].split(":")[0];

  // Lokaler Cache
  const cached = _lidToPhone[lidUser];
  if (cached) {
    log.debug({ lidJid: jid, phoneJid: cached }, "LID→Phone (cached)");
    return cached;
  }

  // Baileys signalRepository Fallback
  try {
    const pn = await sock?.signalRepository?.lidMapping?.getPNForLID(jid);
    if (pn) {
      const phoneJid = `${pn.split("@")[0].split(":")[0]}@s.whatsapp.net`;
      _lidToPhone[lidUser] = phoneJid;
      log.info({ lidJid: jid, phoneJid }, "LID→Phone (signalRepository)");
      return phoneJid;
    }
  } catch (err) {
    log.warn({ err: err.message, jid }, "LID-Resolve via signalRepository fehlgeschlagen");
  }

  log.warn({ lidJid: jid }, "LID konnte nicht aufgelöst werden");
  return jid;
}

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
      const jid = normalizeJid(route.jid);
      if (jid) newRoutes.set(jid, { agent_url: route.agent_url, user_id: route.user_id });
    }
    _routes     = newRoutes;
    _waMode     = data.mode       || "separate";
    _selfPrefix = data.self_prefix || "!h ";

    // STT/TTS-Konfiguration aus Admin-Interface übernehmen
    _sttConfig = data.stt || null;
    _ttsConfig = data.tts || null;
    if (_sttConfig) log.info({ entity: _sttConfig.stt_entity, lang: _sttConfig.stt_language }, "STT konfiguriert");
    if (_ttsConfig) log.info({ entity: _ttsConfig.tts_entity, lang: _ttsConfig.tts_language }, "TTS konfiguriert");

    log.info({ routes: _routes.size, mode: _waMode, stt: !!_sttConfig, tts: !!_ttsConfig }, "WhatsApp-Routing aktualisiert");
  } catch (e) {
    log.warn({ err: e.message }, "Routing-Refresh fehlgeschlagen");
  }
}

function normalizeJid(jid) {
  if (!jid) return null;
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

// ── STT via Home Assistant ────────────────────────────────────────────────

async function sttViaHA(audioBuffer) {
  if (!_sttConfig || !_sttConfig.ha_url || !_sttConfig.ha_token || !_sttConfig.stt_entity) {
    log.warn("STT nicht konfiguriert – Sprachnachricht kann nicht transkribiert werden");
    return null;
  }

  const { ha_url, ha_token, stt_entity, stt_language } = _sttConfig;
  const lang = stt_language || "de-DE";
  const url = `${ha_url}/api/stt/${stt_entity}`;

  log.info({ url, lang, bytes: audioBuffer.length }, "STT-Anfrage an Home Assistant");

  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${ha_token}`,
      "X-Speech-Content": `format=ogg; codec=opus; sample_rate=16000; bit_rate=16; channel=1; language=${lang}`,
      "Content-Type": "application/octet-stream",
    },
    body: audioBuffer,
    timeout: 30_000,
  });

  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`HA STT HTTP ${res.status}: ${txt.slice(0, 200)}`);
  }

  const json = await res.json();
  if (json.result === "success" && json.text) {
    log.info({ text: json.text.slice(0, 100) }, "STT-Transkription erfolgreich");
    return json.text;
  }

  log.warn({ result: json.result }, "STT-Transkription fehlgeschlagen");
  return null;
}

async function transcribeVoiceMessage(msg, sock) {
  try {
    const buffer = await downloadMediaMessage(
      msg,
      "buffer",
      {},
      {
        logger: pino({ level: "silent" }),
        reuploadRequest: sock.updateMediaMessage,
      },
    );

    if (!buffer || buffer.length === 0) {
      log.error("Audio-Download fehlgeschlagen – leerer Buffer");
      return null;
    }

    log.info({ bytes: buffer.length }, "Audio heruntergeladen");
    return await sttViaHA(buffer);
  } catch (err) {
    log.error({ err: err.message }, "Fehler bei Sprachnachricht-Verarbeitung");
    return null;
  }
}

// ── TTS via Home Assistant ────────────────────────────────────────────────

async function ttsViaHA(text) {
  if (!_ttsConfig || !_ttsConfig.ha_url || !_ttsConfig.ha_token || !_ttsConfig.tts_entity) {
    return null;
  }

  const { ha_url, ha_token, tts_entity, tts_language, tts_voice } = _ttsConfig;
  const lang = tts_language || "de-DE";

  log.info({ entity: tts_entity, lang, voice: tts_voice || "(default)", chars: text.length }, "TTS-Anfrage an Home Assistant");

  // Schritt 1: Audio-URL via tts_get_url generieren
  const body = {
    engine_id: tts_entity,
    platform: tts_entity.replace("tts.", ""),
    message: text,
    language: lang,
  };
  if (tts_voice) {
    body.options = { voice: tts_voice };
  }

  const urlRes = await fetch(`${ha_url}/api/tts_get_url`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${ha_token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    timeout: 30_000,
  });

  if (!urlRes.ok) {
    const txt = await urlRes.text();
    throw new Error(`HA TTS HTTP ${urlRes.status}: ${txt.slice(0, 200)}`);
  }

  const urlJson = await urlRes.json();
  const audioUrl = urlJson.url || urlJson.path;
  if (!audioUrl) {
    throw new Error("HA TTS: keine Audio-URL in Antwort");
  }

  // Schritt 2: Audio herunterladen
  const fullUrl = audioUrl.startsWith("http") ? audioUrl : `${ha_url}${audioUrl}`;
  const audioRes = await fetch(fullUrl, {
    headers: { "Authorization": `Bearer ${ha_token}` },
    timeout: 30_000,
  });

  if (!audioRes.ok) {
    throw new Error(`Audio-Download HTTP ${audioRes.status}`);
  }

  const audioBuffer = Buffer.from(await audioRes.arrayBuffer());
  log.info({ bytes: audioBuffer.length, url: audioUrl }, "TTS-Audio heruntergeladen");
  return audioBuffer;
}

// ── Nachrichtentext extrahieren ────────────────────────────────────────────

function extractText(msg) {
  const m = msg.message;
  if (!m) return null;
  if (m.conversation) return m.conversation;
  if (m.extendedTextMessage?.text) return m.extendedTextMessage.text;
  if (m.imageMessage?.caption) return m.imageMessage.caption;
  if (m.documentMessage?.caption) return m.documentMessage.caption;
  // audioMessage wird separat im Message-Handler verarbeitet (STT)
  return null;
}

function isVoiceMessage(msg) {
  return !!msg.message?.audioMessage;
}

// ── HTTP-API ───────────────────────────────────────────────────────────────

function startHttpServer() {
  const server = http.createServer(async (req, res) => {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");

    if (req.method === "OPTIONS") {
      res.writeHead(204);
      res.end();
      return;
    }

    const url = req.url.split("?")[0];

    if (req.method === "GET" && url === "/status") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({
        status: _status,
        account_jid: _accountJid,
        account_name: _accountName,
        has_qr: _qrDataUrl !== null,
        routes: _routes.size,
      }));
      return;
    }

    if (req.method === "GET" && url === "/qr") {
      if (!_qrDataUrl) {
        res.writeHead(404, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "Kein QR-Code verfügbar", status: _status }));
        return;
      }
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ qr: _qrDataUrl, status: _status }));
      return;
    }

    if (req.method === "POST" && url === "/logout") {
      log.info("Logout angefordert via HTTP-API");
      try {
        if (_sock) {
          await _sock.logout();
        }
      } catch (e) {
        log.warn({ err: e.message }, "Logout-Fehler (Session wird trotzdem gelöscht)");
      }
      // Session-Daten löschen
      fs.rmSync(SESSION_DIR, { recursive: true, force: true });
      fs.mkdirSync(SESSION_DIR, { recursive: true });
      _status = "disconnected";
      _qrDataUrl = null;
      _accountJid = null;
      _accountName = null;
      _sock = null;

      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true, message: "Session getrennt. Bridge startet neu..." }));

      // Neustart nach kurzer Verzögerung
      setTimeout(() => {
        startBridge();
      }, 2000);
      return;
    }

    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "Not found" }));
  });

  server.listen(HTTP_PORT, () => {
    log.info({ port: HTTP_PORT }, "Bridge HTTP-API gestartet");
  });
}

// ── Haupt-Loop ─────────────────────────────────────────────────────────────

async function startBridge() {
  if (!fs.existsSync(SESSION_DIR)) {
    fs.mkdirSync(SESSION_DIR, { recursive: true });
  }

  _status = "disconnected";
  _qrDataUrl = null;
  _accountJid = null;
  _accountName = null;

  // Initiales Routing laden
  await refreshConfig();
  // Alle 5 Minuten aktualisieren
  const configInterval = setInterval(refreshConfig, 5 * 60 * 1000);

  const { version } = await fetchLatestBaileysVersion();
  log.info({ version }, "Baileys Version");

  const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);

  const sock = makeWASocket({
    version,
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, pino({ level: "silent" })),
    },
    logger: pino({ level: "silent" }),
    printQRInTerminal: false,
    browser: ["HAANA", "Chrome", "1.0.0"],
    generateHighQualityLinkPreview: false,
    markOnlineOnConnect: false,
  });

  _sock = sock;

  sock.ev.on("creds.update", saveCreds);

  // ── Verbindungsstatus ────────────────────────────────────────────────────

  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      _status = "qr";
      // QR-Code als Base64 Data-URL generieren
      try {
        _qrDataUrl = await qrcode.toDataURL(qr, { width: 256, margin: 2 });
      } catch (e) {
        log.error({ err: e.message }, "QR-Code Generierung fehlgeschlagen");
        _qrDataUrl = null;
      }
      // Auch weiterhin im Terminal anzeigen (für docker logs)
      console.log("\n========================================");
      console.log("  HAANA WhatsApp – QR-Code scannen:");
      console.log("========================================\n");
      qrTerm.generate(qr, { small: true });
      console.log("\n(QR-Code auch im Admin-Interface verfügbar)\n");
    }

    if (connection === "open") {
      _status = "connected";
      _qrDataUrl = null;  // QR nicht mehr nötig
      _accountJid = sock.user?.id || null;
      _accountName = sock.user?.name || null;
      log.info({ jid: _accountJid, name: _accountName }, "WhatsApp verbunden");

      // LID→Phone Mapping für eigenen Account aufbauen (NanoClaw-Strategie)
      if (sock.user) {
        const phoneUser = sock.user.id?.split(":")[0];
        const lidUser = sock.user.lid?.split(":")[0];
        if (lidUser && phoneUser) {
          _lidToPhone[lidUser] = `${phoneUser}@s.whatsapp.net`;
          log.info({ lidUser, phoneUser }, "Eigene LID→Phone Zuordnung gesetzt");
        }
      }

      // Routing direkt nach Verbindung aktualisieren
      refreshConfig();
    }

    if (connection === "close") {
      const code   = lastDisconnect?.error?.output?.statusCode;
      const reason = Object.keys(DisconnectReason).find((k) => DisconnectReason[k] === code);
      const logout = code === DisconnectReason.loggedOut;

      _status = "disconnected";
      _qrDataUrl = null;
      _accountJid = null;
      _accountName = null;
      _sock = null;

      log.warn({ code, reason }, "Verbindung getrennt");
      clearInterval(configInterval);

      if (logout) {
        log.error("Session ungültig (ausgeloggt). Session löschen und neu starten.");
        fs.rmSync(SESSION_DIR, { recursive: true, force: true });
        fs.mkdirSync(SESSION_DIR, { recursive: true });
        setTimeout(startBridge, 3_000);
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
      if (msg.key.fromMe)                        continue;
      if (isJidBroadcast(msg.key.remoteJid))     continue;
      if (isJidGroup(msg.key.remoteJid))          continue;

      const rawFrom      = msg.key.remoteJid;
      const from         = await translateJid(rawFrom, sock);
      const fromNorm     = normalizeJid(from);

      // ── Sicherheitsfilter: nur bekannte Nummern ──────────────────────────
      if (_routes.size === 0) {
        log.warn({ from }, "Keine Routen konfiguriert – Nachricht ignoriert");
        continue;
      }

      const route = _routes.get(fromNorm);
      if (!route) {
        log.warn({ from: fromNorm }, "Unbekannte Nummer – Nachricht ignoriert (Sicherheitsfilter)");
        continue;
      }

      // ── Text oder Sprachnachricht verarbeiten ─────────────────────────────
      let text = extractText(msg);

      if (!text && isVoiceMessage(msg)) {
        // Sprachnachricht: Audio herunterladen und via HA STT transkribieren
        log.info({ from: fromNorm }, "Sprachnachricht empfangen – starte Transkription");
        await sock.sendPresenceUpdate("composing", from);
        const transcript = await transcribeVoiceMessage(msg, sock);
        if (transcript) {
          text = `[Sprachnachricht: ${transcript}]`;
        } else {
          text = null;
          await sock.sendMessage(from, {
            text: "Ich konnte die Sprachnachricht leider nicht verarbeiten. Bitte schreib mir stattdessen.",
          });
          await sock.sendPresenceUpdate("paused", from);
          continue;
        }
      }

      if (!text) {
        log.debug({ from, type: Object.keys(msg.message || {}) }, "Kein verarbeitbarer Text – ignoriert");
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

      const wasVoice = isVoiceMessage(msg);
      log.info({ from: fromNorm, user: route.user_id, voice: wasVoice, text: text.slice(0, 100) }, "Eingehende Nachricht");

      await sock.sendPresenceUpdate("composing", from);

      try {
        const response = await queryAgent(route.agent_url, text, "whatsapp");
        log.info({ from: fromNorm, response: response.slice(0, 100) }, "Agent-Antwort");

        // TTS: Sprachnachricht zurücksenden wenn Input Voice war und TTS konfiguriert
        let sentVoice = false;
        if (wasVoice && _ttsConfig) {
          try {
            const audioBuffer = await ttsViaHA(response);
            if (audioBuffer && audioBuffer.length > 0) {
              await sock.sendMessage(from, {
                audio: audioBuffer,
                mimetype: "audio/mp4",
                ptt: true, // Push-to-Talk = als Sprachnachricht anzeigen
              });
              sentVoice = true;
              log.info({ from: fromNorm, bytes: audioBuffer.length }, "TTS-Sprachnachricht gesendet");
            }
          } catch (ttsErr) {
            log.warn({ err: ttsErr.message }, "TTS fehlgeschlagen – sende Text stattdessen");
          }
        }

        // Text als Fallback oder wenn kein Voice gewünscht
        if (!sentVoice) {
          await sock.sendMessage(from, { text: response });
        }
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

log.info({ adminUrl: ADMIN_URL, sessionDir: SESSION_DIR, httpPort: HTTP_PORT }, "HAANA WhatsApp Bridge startet");

startHttpServer();
startBridge().catch((err) => {
  log.error({ err: err.message }, "Fataler Fehler – Bridge beendet");
  process.exit(1);
});
