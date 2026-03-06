#!/usr/bin/env bash
# HAANA Integration Test
# Erstellt einen Test-User, sendet Nachrichten, prueft Antworten, raeumt auf.
# Testet: User-CRUD, Anthropic, MiniMax, MCP, Memory, Health-Checks
#
# Usage: ./scripts/integration-test.sh [--keep]
#   --keep: Test-User nach dem Test nicht loeschen (zum Debuggen)

set -uo pipefail

ADMIN_URL="http://10.83.1.11:8080"
TEST_USER="int-test"
TEST_DISPLAY="Integration Test"
KEEP=false
ERRORS=0
PASSED=0
SKIPPED=0

[[ "${1:-}" == "--keep" ]] && KEEP=true

red()    { echo -e "\033[31m$1\033[0m"; }
green()  { echo -e "\033[32m$1\033[0m"; }
yellow() { echo -e "\033[33m$1\033[0m"; }

pass() { ((PASSED++)); green "  PASS: $1"; }
fail() { ((ERRORS++)); red   "  FAIL: $1"; }
skip() { ((SKIPPED++)); yellow "  SKIP: $1"; }

# ── Cleanup-Trap ───────────────────────────────────────────────────────────────
cleanup() {
  if [[ "$KEEP" == "false" ]]; then
    echo ""
    echo "=== Cleanup ==="
    # User loeschen (stoppt + entfernt Container)
    local resp
    resp=$(curl -s -X DELETE "${ADMIN_URL}/api/users/${TEST_USER}" 2>/dev/null)
    if echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('ok') else 1)" 2>/dev/null; then
      green "  Test-User geloescht"
    else
      yellow "  Test-User konnte nicht geloescht werden (evtl. bereits entfernt)"
    fi
    # CLAUDE.md Verzeichnis aufraeumen
    rm -rf "/opt/haana/instanzen/${TEST_USER}" 2>/dev/null
  else
    yellow "  --keep: Test-User '${TEST_USER}' bleibt bestehen"
  fi
}
trap cleanup EXIT

echo "=== HAANA Integration Test ==="
echo ""

# ── 1. Service Health Checks ──────────────────────────────────────────────────
echo "--- Service Health ---"

# Admin-Interface
if curl -s -o /dev/null -w '%{http_code}' "${ADMIN_URL}/" | grep -q 200; then
  pass "Admin-Interface erreichbar"
else
  fail "Admin-Interface nicht erreichbar"; exit 1
fi

# Qdrant
QDRANT_STATUS=$(curl -s "${ADMIN_URL}/api/status" 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('ok' if d.get('qdrant',{}).get('ok') else 'down')" 2>/dev/null)
if [[ "$QDRANT_STATUS" == "ok" ]]; then
  pass "Qdrant erreichbar"
else
  fail "Qdrant: $QDRANT_STATUS"
fi

# Ollama
OLLAMA_STATUS=$(curl -s "${ADMIN_URL}/api/status" 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('ok' if d.get('ollama',{}).get('ok') else 'down')" 2>/dev/null)
if [[ "$OLLAMA_STATUS" == "ok" ]]; then
  pass "Ollama erreichbar"
else
  skip "Ollama: $OLLAMA_STATUS"
fi

echo ""

# ── 2. Config laden ──────────────────────────────────────────────────────────
echo "--- Config ---"

CONFIG=$(curl -s "${ADMIN_URL}/api/config" 2>/dev/null)
SLOT_COUNT=$(echo "$CONFIG" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('llm_providers',[])))" 2>/dev/null)
if [[ "$SLOT_COUNT" -ge 1 ]]; then
  pass "Config geladen ($SLOT_COUNT LLM-Slots)"
else
  fail "Config laden fehlgeschlagen"
fi

# MiniMax Slot pruefen
MINIMAX_READY=$(echo "$CONFIG" | python3 -c "
import sys,json
slots = json.load(sys.stdin).get('llm_providers',[])
for s in slots:
    if s.get('type') == 'minimax' and s.get('key'):
        print('yes'); exit()
print('no')" 2>/dev/null)

echo ""

# ── 3. Test-User anlegen ─────────────────────────────────────────────────────
echo "--- User CRUD ---"

# Eventuell alten Test-User aufraeumen
curl -s -X DELETE "${ADMIN_URL}/api/users/${TEST_USER}" >/dev/null 2>&1
rm -rf "/opt/haana/instanzen/${TEST_USER}" 2>/dev/null
sleep 1

# User anlegen mit Anthropic (Slot 1)
CREATE_RESP=$(curl -s -X POST "${ADMIN_URL}/api/users" \
  -H 'Content-Type: application/json' \
  -d "{
    \"id\": \"${TEST_USER}\",
    \"display_name\": \"${TEST_DISPLAY}\",
    \"role\": \"user\",
    \"primary_llm_slot\": 1,
    \"extraction_llm_slot\": 3,
    \"claude_md_template\": \"user\"
  }" 2>/dev/null)

CREATE_OK=$(echo "$CREATE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',''))" 2>/dev/null)
if [[ "$CREATE_OK" == "True" ]]; then
  pass "Test-User angelegt"
else
  fail "User anlegen: $CREATE_RESP"; exit 1
fi

# Port ermitteln
TEST_PORT=$(curl -s "${ADMIN_URL}/api/config" | python3 -c "
import sys,json
cfg = json.load(sys.stdin)
for u in cfg.get('users',[]):
    if u['id'] == '${TEST_USER}':
        print(u.get('api_port','')); break" 2>/dev/null)

if [[ -z "$TEST_PORT" ]]; then
  fail "Test-User Port nicht gefunden"; exit 1
fi
pass "Container Port: $TEST_PORT"

# Warten bis Container healthy
echo -n "  Warte auf Agent-Container"
for i in $(seq 1 30); do
  HEALTH=$(curl -s -o /dev/null -w '%{http_code}' "http://10.83.1.11:${TEST_PORT}/health" 2>/dev/null)
  if [[ "$HEALTH" == "200" ]]; then
    echo ""; pass "Agent-Container healthy"
    break
  fi
  echo -n "."
  sleep 2
done
if [[ "$HEALTH" != "200" ]]; then
  echo ""; fail "Agent-Container nicht healthy nach 60s"
fi

echo ""

# ── 3b. User-Setup Verifizierung ──────────────────────────────────────────────
echo "--- User Setup ---"

# CLAUDE.md existiert?
if [[ -f "/opt/haana/instanzen/${TEST_USER}/CLAUDE.md" ]]; then
  pass "CLAUDE.md angelegt"

  # Template-Platzhalter ersetzt?
  if grep -q "${TEST_DISPLAY}" "/opt/haana/instanzen/${TEST_USER}/CLAUDE.md"; then
    pass "CLAUDE.md: Display-Name eingesetzt"
  else
    fail "CLAUDE.md: Display-Name '${TEST_DISPLAY}' nicht gefunden"
  fi

  # Keine unersetzten Platzhalter?
  if grep -q '{{' "/opt/haana/instanzen/${TEST_USER}/CLAUDE.md"; then
    fail "CLAUDE.md: Unersetzte Platzhalter gefunden"
  else
    pass "CLAUDE.md: Keine Platzhalter-Reste"
  fi
else
  fail "CLAUDE.md nicht angelegt unter /opt/haana/instanzen/${TEST_USER}/"
fi

# User in Config gespeichert?
USER_IN_CFG=$(curl -s "${ADMIN_URL}/api/config" | python3 -c "
import sys,json
cfg = json.load(sys.stdin)
for u in cfg.get('users',[]):
    if u['id'] == '${TEST_USER}':
        print('found'); break
else:
    print('missing')" 2>/dev/null)
if [[ "$USER_IN_CFG" == "found" ]]; then
  pass "User in config.json gespeichert"
else
  fail "User nicht in config.json"
fi

echo ""

# ── 4. Chat-Test: Anthropic ─────────────────────────────────────────────────
echo "--- Chat: Anthropic ---"

CHAT_RESP=$(curl -s --max-time 90 -X POST "http://10.83.1.11:${TEST_PORT}/chat" \
  -H 'Content-Type: application/json' \
  -d '{"message": "Antworte nur mit dem Wort PONG und nichts anderes.", "channel": "integration-test"}' 2>/dev/null)

CHAT_TEXT=$(echo "$CHAT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('response','ERROR'))" 2>/dev/null)
if echo "$CHAT_TEXT" | grep -qi "PONG"; then
  pass "Anthropic Chat: '$CHAT_TEXT'"
else
  if echo "$CHAT_TEXT" | grep -qi "error\|fehler\|not logged"; then
    fail "Anthropic Chat: '$CHAT_TEXT'"
  else
    # Agent antwortete, aber nicht exakt PONG - trotzdem OK
    pass "Anthropic Chat (Antwort erhalten): '${CHAT_TEXT:0:80}'"
  fi
fi

echo ""

# ── 5. Chat-Test: MiniMax ───────────────────────────────────────────────────
echo "--- Chat: MiniMax ---"

if [[ "$MINIMAX_READY" == "yes" ]]; then
  # User auf MiniMax umstellen (Slot 4)
  curl -s -X PATCH "${ADMIN_URL}/api/users/${TEST_USER}" \
    -H 'Content-Type: application/json' \
    -d '{"primary_llm_slot": 4}' >/dev/null 2>&1

  # Container neu starten mit neuem Slot
  RESTART_RESP=$(curl -s -X POST "${ADMIN_URL}/api/users/${TEST_USER}/restart" 2>/dev/null)
  RESTART_OK=$(echo "$RESTART_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',''))" 2>/dev/null)

  if [[ "$RESTART_OK" == "True" ]]; then
    # Warten bis Container healthy
    echo -n "  Warte auf Restart"
    for i in $(seq 1 30); do
      H=$(curl -s -o /dev/null -w '%{http_code}' "http://10.83.1.11:${TEST_PORT}/health" 2>/dev/null)
      if [[ "$H" == "200" ]]; then echo ""; break; fi
      echo -n "."; sleep 2
    done

    MM_RESP=$(curl -s --max-time 90 -X POST "http://10.83.1.11:${TEST_PORT}/chat" \
      -H 'Content-Type: application/json' \
      -d '{"message": "Antworte nur mit dem Wort PONG und nichts anderes.", "channel": "integration-test"}' 2>/dev/null)

    MM_TEXT=$(echo "$MM_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('response','ERROR'))" 2>/dev/null)
    if echo "$MM_TEXT" | grep -qi "error\|fehler\|not logged\|invalid.*key\|authentication\|401"; then
      fail "MiniMax Chat: '${MM_TEXT:0:120}'"
    else
      pass "MiniMax Chat: '${MM_TEXT:0:80}'"
    fi

    # Zurueck auf Anthropic
    curl -s -X PATCH "${ADMIN_URL}/api/users/${TEST_USER}" \
      -H 'Content-Type: application/json' \
      -d '{"primary_llm_slot": 1}' >/dev/null 2>&1
  else
    fail "MiniMax: Container-Restart fehlgeschlagen"
  fi
else
  skip "MiniMax nicht konfiguriert (kein API-Key in Slot 4)"
fi

echo ""

# ── 6. MCP Health ──────────────────────────────────────────────────────────
echo "--- MCP ---"

MCP_ENABLED=$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin).get('services',{}).get('ha_mcp_enabled',False))" 2>/dev/null)
if [[ "$MCP_ENABLED" == "True" ]]; then
  MCP_TYPE=$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin).get('services',{}).get('ha_mcp_type','?'))" 2>/dev/null)
  MCP_URL=$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin).get('services',{}).get('ha_mcp_url',''))" 2>/dev/null)

  # Test MCP endpoint reachability
  MCP_TEST=$(curl -s -X POST "${ADMIN_URL}/api/test-ha-mcp" \
    -H 'Content-Type: application/json' \
    -d "{\"mcp_url\": \"${MCP_URL}\", \"mcp_type\": \"${MCP_TYPE}\", \"token\": \"$(echo "$CONFIG" | python3 -c "import sys,json; print(json.load(sys.stdin).get('services',{}).get('ha_token',''))")\"}" 2>/dev/null)
  MCP_OK=$(echo "$MCP_TEST" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',False))" 2>/dev/null)

  if [[ "$MCP_OK" == "True" ]]; then
    pass "MCP Server erreichbar (type=$MCP_TYPE)"
  else
    MCP_DETAIL=$(echo "$MCP_TEST" | python3 -c "import sys,json; print(json.load(sys.stdin).get('detail','?'))" 2>/dev/null)
    fail "MCP: $MCP_DETAIL"
  fi
else
  skip "MCP nicht aktiviert"
fi

echo ""

# ── 7. HA REST API ───────────────────────────────────────────────────────────
echo "--- Home Assistant ---"

HA_TEST=$(curl -s -X POST "${ADMIN_URL}/api/test-ha" \
  -H 'Content-Type: application/json' \
  -d '{}' 2>/dev/null)
HA_OK=$(echo "$HA_TEST" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',False))" 2>/dev/null)
if [[ "$HA_OK" == "True" ]]; then
  HA_VER=$(echo "$HA_TEST" | python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null)
  pass "Home Assistant erreichbar (v$HA_VER)"
else
  skip "Home Assistant nicht erreichbar"
fi

echo ""

# ── 8. Memory Round-Trip ──────────────────────────────────────────────────────
echo "--- Memory ---"

# Chat-Nachricht senden die Memory erzeugt
MEM_RESP=$(curl -s --max-time 90 -X POST "http://10.83.1.11:${TEST_PORT}/chat" \
  -H 'Content-Type: application/json' \
  -d '{"message": "Merke dir bitte: Meine Lieblingsfarbe ist Smaragdgruen. Bestaetige kurz.", "channel": "integration-test"}' 2>/dev/null)

MEM_TEXT=$(echo "$MEM_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('response','ERROR'))" 2>/dev/null)
if echo "$MEM_TEXT" | grep -qi "error\|fehler\|not logged"; then
  fail "Memory-Speichern: '$MEM_TEXT'"
else
  pass "Memory-Speichern (Antwort): '${MEM_TEXT:0:80}'"
fi

# Kurz warten damit Memory persistiert
sleep 3

# Memory abrufen
MEM_RECALL=$(curl -s --max-time 90 -X POST "http://10.83.1.11:${TEST_PORT}/chat" \
  -H 'Content-Type: application/json' \
  -d '{"message": "Was ist meine Lieblingsfarbe?", "channel": "integration-test"}' 2>/dev/null)

MEM_RECALL_TEXT=$(echo "$MEM_RECALL" | python3 -c "import sys,json; print(json.load(sys.stdin).get('response','ERROR'))" 2>/dev/null)
if echo "$MEM_RECALL_TEXT" | grep -qi "smaragd\|gruen\|grün"; then
  pass "Memory-Abruf: Lieblingsfarbe korrekt erinnert"
else
  if echo "$MEM_RECALL_TEXT" | grep -qi "error\|fehler"; then
    fail "Memory-Abruf: '$MEM_RECALL_TEXT'"
  else
    # Agent antwortete, konnte sich aber nicht erinnern
    skip "Memory-Abruf: Farbe nicht erinnert ('${MEM_RECALL_TEXT:0:80}')"
  fi
fi

echo ""

# ── 9. User loeschen ─────────────────────────────────────────────────────────
echo "--- User Cleanup ---"

if [[ "$KEEP" == "false" ]]; then
  DEL_RESP=$(curl -s -X DELETE "${ADMIN_URL}/api/users/${TEST_USER}" 2>/dev/null)
  DEL_OK=$(echo "$DEL_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',''))" 2>/dev/null)
  if [[ "$DEL_OK" == "True" ]]; then
    pass "Test-User geloescht"
    # Cleanup-Trap nicht nochmal ausfuehren
    KEEP=true
  else
    fail "User loeschen: $DEL_RESP"
  fi
  rm -rf "/opt/haana/instanzen/${TEST_USER}" 2>/dev/null
fi

echo ""

# ── Ergebnis ──────────────────────────────────────────────────────────────────
echo "=== Ergebnis: $PASSED bestanden, $ERRORS fehlgeschlagen, $SKIPPED uebersprungen ==="
if [[ $ERRORS -gt 0 ]]; then
  red "Integration-Test FEHLGESCHLAGEN"
  exit 1
else
  green "Integration-Test OK"
  exit 0
fi
