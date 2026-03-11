#!/usr/bin/env bash
# HAANA Update Script
# Ausfuehren im HAANA LXC:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/alicezone/haana/main/update.sh)"
# Oder lokal:
#   bash /opt/haana/update.sh

set -eo pipefail

# ── Farben ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

warn() {
    echo -e "${YELLOW}  ⚠ $1${NC}"
}

# ── Fehlerbehandlung ──────────────────────────────────────────────────────────
trap 'echo -e "${RED}Fehler in Zeile $LINENO — Update abgebrochen.${NC}"; exit 1' ERR

# Root-Check
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}Fehler: update.sh muss als root ausgefuehrt werden.${NC}"
    echo "  Tipp: sudo bash /opt/haana/update.sh"
    exit 1
fi

# ── Voraussetzungen ───────────────────────────────────────────────────────────
if [ ! -d /opt/haana/.git ]; then
    echo -e "${RED}Fehler: /opt/haana ist kein Git-Repository.${NC}"
    echo -e "${RED}       Bitte HAANA zuerst mit install.sh installieren.${NC}"
    exit 1
fi

if ! command -v docker &>/dev/null; then
    echo -e "${RED}Fehler: Docker ist nicht installiert.${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}HAANA Update wird gestartet...${NC}"
echo ""

# ── Self-Update ───────────────────────────────────────────────────────────────
# Nur wenn Script lokal ausgeführt wird (nicht wenn es selbst schon per curl gestartet wurde)
if [ "${HAANA_SELF_UPDATED:-0}" != "1" ]; then
    echo -e "${YELLOW}→ Update-Script auf neue Version prüfen...${NC}"
    REMOTE_URL="https://raw.githubusercontent.com/alicezone/haana/main/update.sh"
    REMOTE_TMP=$(mktemp)
    if curl -fsSL "$REMOTE_URL" -o "$REMOTE_TMP" 2>/dev/null; then
        LOCAL_HASH=$(md5sum /opt/haana/update.sh 2>/dev/null | cut -d' ' -f1)
        REMOTE_HASH=$(md5sum "$REMOTE_TMP" | cut -d' ' -f1)
        if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
            echo -e "  Neue Version gefunden — Update-Script wird aktualisiert."
            cp "$REMOTE_TMP" /opt/haana/update.sh
            chown haana:haana /opt/haana/update.sh
            chmod +x /opt/haana/update.sh
            rm -f "$REMOTE_TMP"
            echo -e "  Starte neue Version..."
            echo ""
            export HAANA_SELF_UPDATED=1
            exec bash /opt/haana/update.sh
        else
            echo -e "  Update-Script ist aktuell."
        fi
    else
        warn "Konnte Update-Script nicht prüfen (kein Internet?)"
    fi
    rm -f "$REMOTE_TMP"
    echo ""
fi

# ── System-Update ─────────────────────────────────────────────────────────────
echo -e "${YELLOW}→ System-Pakete aktualisieren...${NC}"
DEBIAN_FRONTEND=noninteractive apt-get update -qq && \
    DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq
echo -e "${GREEN}  System-Pakete aktualisiert.${NC}"
echo ""

# ── Claude Code Update ────────────────────────────────────────────────────────
echo -e "${YELLOW}→ Claude Code aktualisieren...${NC}"
NPM_OUT=$(npm install -g @anthropic-ai/claude-code 2>&1) || warn "Claude Code Update fehlgeschlagen"
echo "$NPM_OUT" | tail -5
CC_VERSION=$(claude --version 2>/dev/null || echo "n/a")
echo -e "${GREEN}  Claude Code: $CC_VERSION${NC}"
echo ""

# ── Git Pull ──────────────────────────────────────────────────────────────────
echo -e "${YELLOW}→ HAANA Code aktualisieren...${NC}"
cd /opt/haana

OLD_HASH=$(su -s /bin/bash haana -c "git -C /opt/haana rev-parse --short HEAD")
su -s /bin/bash haana -c "git -C /opt/haana reset --hard HEAD"
su -s /bin/bash haana -c "git -C /opt/haana pull"
NEW_HASH=$(su -s /bin/bash haana -c "git -C /opt/haana rev-parse --short HEAD")

if [ "$OLD_HASH" = "$NEW_HASH" ]; then
    echo -e "  Kein Code-Update verfuegbar (bereits aktuell: ${GREEN}$NEW_HASH${NC})"
else
    echo -e "  Update: ${YELLOW}$OLD_HASH${NC} → ${GREEN}$NEW_HASH${NC}"

    # Changelog der neuen Commits anzeigen
    echo ""
    echo "  Neue Commits:"
    su -s /bin/bash haana -c "git -C /opt/haana log --oneline '${OLD_HASH}..${NEW_HASH}'" | sed 's/^/    /'
fi
echo ""

# ── Docker Compose neu starten ────────────────────────────────────────────────
echo -e "${YELLOW}→ Docker-Services neu starten...${NC}"
docker compose pull
docker compose up -d --build
echo ""

# ── Abschlussmeldung ──────────────────────────────────────────────────────────
echo -e "${GREEN}✓ Update abgeschlossen!${NC}"
echo ""
echo "  Laufende Services:"
docker compose ps
echo ""
