#!/usr/bin/env bash
# HAANA Proxmox LXC Installer
# Ausfuehren auf dem Proxmox-Host:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/alicezone/haana/main/install.sh)"
# Oder lokal:
#   bash /opt/haana/install.sh

set -eo pipefail

# ── Farben ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Fehlerbehandlung ──────────────────────────────────────────────────────────
CTID=""
trap 'on_error $LINENO' ERR

on_error() {
    echo ""
    echo -e "${RED}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  Fehler in Zeile $1 — Installation abgebrochen.      ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════╝${NC}"
    if [ -n "$CTID" ]; then
        echo -e "${YELLOW}  Hinweis: Container $CTID wurde ggf. teilweise erstellt.${NC}"
        echo -e "${YELLOW}  Bereinigen mit: pct stop $CTID && pct destroy $CTID${NC}"
    fi
    exit 1
}

step() {
    local num="$1"
    local total="$2"
    local msg="$3"
    echo -e "${GREEN}  → Schritt $num/$total: $msg${NC}"
}

warn() {
    echo -e "${YELLOW}  ⚠ $1${NC}"
}

# IP-Validierung (IPv4 mit optionalem CIDR-Suffix)
validate_ip() {
    local ip="$1"
    local label="$2"
    if [[ ! "$ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}(/[0-9]{1,2})?$ ]]; then
        echo -e "${RED}Fehler: '$ip' ist keine gueltige IP-Adresse fuer $label.${NC}"
        exit 1
    fi
}

# ── Banner ────────────────────────────────────────────────────────────────────
clear
echo -e "${CYAN}${BOLD}"
cat << 'EOF'
    __  __   ___    ___   _  _   ___
   / / / /  / _ |  / _ | / |/ / / _ |
  / /_/ /  / __ | / __ |/ ,  / / __ |
  \____/  /_/ |_|/_/ |_/_/|_/ /_/ |_|

  Proxmox LXC Installer
  https://github.com/alicezone/haana
EOF
echo -e "${NC}"
echo ""

# ── Voraussetzungen pruefen ───────────────────────────────────────────────────
if ! command -v pct &>/dev/null; then
    echo -e "${RED}Fehler: Dieses Script muss auf einem Proxmox-Host ausgefuehrt werden.${NC}"
    echo -e "${RED}       'pct' wurde nicht gefunden.${NC}"
    exit 1
fi

if ! command -v pvesh &>/dev/null; then
    echo -e "${RED}Fehler: 'pvesh' wurde nicht gefunden. Proxmox VE erforderlich.${NC}"
    exit 1
fi

# ── Hilfsfunktion: Eingabe mit Default ───────────────────────────────────────
ask() {
    # ask <variablenname> <prompt> <default>
    local varname="$1"
    local prompt="$2"
    local default="$3"
    local value=""

    if [ -n "$default" ]; then
        read -rp "  $prompt [$default]: " value
        value="${value:-$default}"
    else
        read -rp "  $prompt []: " value
    fi

    printf -v "$varname" '%s' "$value"
}

ask_choice() {
    # ask_choice <variablenname> <prompt> <default>
    local varname="$1"
    local prompt="$2"
    local default="$3"
    local value=""

    read -rp "  $prompt [$default]: " value
    value="${value:-$default}"
    printf -v "$varname" '%s' "$value"
}

# ── Naechste freie Container-ID ermitteln ─────────────────────────────────────
NEXT_ID=$(pvesh get /cluster/nextid 2>/dev/null || echo "200")

# ── Interaktive Konfiguration ─────────────────────────────────────────────────
echo -e "${BOLD}Konfiguration${NC}"
echo "────────────────────────────────────────────────────"
echo ""

ask CTID "Container ID" "$NEXT_ID"
ask HOSTNAME "Hostname" "haana"

echo ""
echo -e "${YELLOW}  Ressourcen (min. 2 Cores / 2048 MB RAM / 20 GB Disk):${NC}"
ask CORES "CPU Cores (empfohlen: 4)" "4"
ask RAM "RAM in MB (empfohlen: 4096)" "4096"
ask DISK "Disk in GB (empfohlen: 50)" "50"

echo ""
echo -e "${YELLOW}  Netzwerk:${NC}"
ask BRIDGE "Bridge" "vmbr0"
ask VLAN "VLAN Tag (leer = kein VLAN)" ""

echo ""
echo "  IP-Konfiguration:"
echo "    (1) DHCP"
echo "    (2) Statische IP"
ask_choice IP_MODE "Auswahl" "1"

if [ "$IP_MODE" = "2" ]; then
    ask STATIC_IP "IP-Adresse (z.B. 192.168.1.100/24)" ""
    ask GATEWAY "Gateway (z.B. 192.168.1.1)" ""
    ask DNS_SERVER "DNS (z.B. 192.168.1.1)" ""
    validate_ip "$STATIC_IP" "IP-Adresse"
    validate_ip "$GATEWAY" "Gateway"
    validate_ip "$DNS_SERVER" "DNS-Server"
    NET_CONFIG="ip=$STATIC_IP,gw=$GATEWAY"
    NET_DISPLAY="$STATIC_IP (GW: $GATEWAY)"
else
    NET_CONFIG="ip=dhcp"
    NET_DISPLAY="DHCP"
fi

# ── Validierung ───────────────────────────────────────────────────────────────
if [ "$CORES" -lt 2 ] 2>/dev/null; then
    warn "Mindestens 2 CPU Cores erforderlich — setze auf 2."
    CORES=2
fi

if [ "$RAM" -lt 2048 ] 2>/dev/null; then
    warn "Mindestens 2048 MB RAM erforderlich — setze auf 2048."
    RAM=2048
fi

if [ "$DISK" -lt 20 ] 2>/dev/null; then
    warn "Mindestens 20 GB Disk erforderlich — setze auf 20."
    DISK=20
fi

# VLAN-Suffix fuer pct create
VLAN_SUFFIX=""
if [ -n "$VLAN" ]; then
    VLAN_SUFFIX=",tag=$VLAN"
fi

# ── Zusammenfassung ───────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}┌─────────────────────────────────────────┐${NC}"
echo -e "${BOLD}│  HAANA LXC Konfiguration                │${NC}"
echo -e "${BOLD}├─────────────────────────────────────────┤${NC}"
printf "${BOLD}│${NC}  Container ID:  %-23s${BOLD}│${NC}\n" "$CTID"
printf "${BOLD}│${NC}  Hostname:      %-23s${BOLD}│${NC}\n" "$HOSTNAME"
printf "${BOLD}│${NC}  CPU:           %-23s${BOLD}│${NC}\n" "$CORES Cores"
printf "${BOLD}│${NC}  RAM:           %-23s${BOLD}│${NC}\n" "$RAM MB"
printf "${BOLD}│${NC}  Disk:          %-23s${BOLD}│${NC}\n" "$DISK GB"
printf "${BOLD}│${NC}  Bridge:        %-23s${BOLD}│${NC}\n" "$BRIDGE"
printf "${BOLD}│${NC}  Netzwerk:      %-23s${BOLD}│${NC}\n" "$NET_DISPLAY"
echo -e "${BOLD}└─────────────────────────────────────────┘${NC}"
echo ""

read -rp "Fortfahren? [y/N]: " CONFIRM
if [[ ! "$CONFIRM" =~ ^[yYjJ]$ ]]; then
    echo "Abgebrochen."
    exit 0
fi

echo ""

# ── Schritt 1: Template pruefen / herunterladen ───────────────────────────────
TEMPLATE="debian-12-standard_12.7-1_amd64.tar.zst"
TEMPLATE_PATH="local:vztmpl/$TEMPLATE"

step 1 6 "Debian 12 Template pruefen..."
if ! pveam list local 2>/dev/null | grep -q "$TEMPLATE"; then
    warn "Template nicht gefunden — wird heruntergeladen..."
    if ! pveam available 2>/dev/null | grep -q "debian-12-standard_12.7-1"; then
        echo -e "${RED}Fehler: Template '$TEMPLATE' nicht in pveam verfuegbar.${NC}"
        echo "  Verfuegbare Debian-Templates:"
        pveam available 2>/dev/null | grep debian || true
        exit 1
    fi
    pveam download local "$TEMPLATE"
    echo -e "${GREEN}  Template heruntergeladen.${NC}"
else
    echo -e "${GREEN}  Template bereits vorhanden.${NC}"
fi

# ── Schritt 2: Container erstellen ───────────────────────────────────────────
step 2 6 "LXC Container $CTID erstellen..."
pct create "$CTID" "$TEMPLATE_PATH" \
    --hostname "$HOSTNAME" \
    --cores "$CORES" \
    --memory "$RAM" \
    --rootfs "local-lvm:$DISK" \
    --net0 "name=eth0,bridge=${BRIDGE}${VLAN_SUFFIX},ip=${NET_CONFIG}" \
    --unprivileged 1 \
    --features nesting=1 \
    --ostype debian \
    --start 1

echo -e "${GREEN}  Container erstellt und gestartet.${NC}"

# Kurz warten bis Container vollstaendig gestartet ist
echo "  Warte auf Container-Start..."
sleep 5

# DNS nur bei statischer IP konfigurieren
if [ "$IP_MODE" = "2" ] && [ -n "$DNS_SERVER" ]; then
    pct exec "$CTID" -- bash -c "echo 'nameserver $DNS_SERVER' > /etc/resolv.conf"
fi

# ── Schritt 3: System-Pakete installieren ─────────────────────────────────────
step 3 6 "System-Pakete installieren (curl, git, ca-certificates)..."
pct exec "$CTID" -- bash -c "
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq curl git ca-certificates sudo openssl
"
echo -e "${GREEN}  Pakete installiert.${NC}"

# ── Schritt 4: Docker installieren ───────────────────────────────────────────
step 4 6 "Docker installieren..."
pct exec "$CTID" -- bash -c "curl -fsSL https://get.docker.com | sh"
echo -e "${GREEN}  Docker installiert.${NC}"

# ── Schritt 5: HAANA einrichten ───────────────────────────────────────────────
step 5 6 "HAANA installieren und konfigurieren..."
pct exec "$CTID" -- bash -c "
    set -e

    # haana user anlegen
    useradd -m -u 1000 -s /bin/bash haana 2>/dev/null || true
    usermod -aG docker haana

    # sudo-Regel fuer haana (nur Docker-Befehle)
    echo 'haana ALL=(ALL) NOPASSWD: /usr/bin/docker, /usr/local/bin/docker' > /etc/sudoers.d/haana
    chmod 0440 /etc/sudoers.d/haana

    # HAANA Repo klonen
    if [ -d /opt/haana/.git ]; then
        echo '  Repo bereits vorhanden — git pull...'
        cd /opt/haana && git pull
    else
        git clone https://github.com/alicezone/haana /opt/haana
    fi
    chown -R haana:haana /opt/haana

    # Daten-Verzeichnisse anlegen
    mkdir -p /data/config /data/logs /media/haana
    chown -R haana:haana /data /media/haana

    # .env aus Example kopieren (falls noch nicht vorhanden)
    if [ ! -f /opt/haana/.env ]; then
        cp /opt/haana/.env.example /opt/haana/.env
        chown haana:haana /opt/haana/.env
    fi

    # companion_token generieren und in config.json schreiben (bestehende config nicht ueberschreiben)
    TOKEN=\$(openssl rand -hex 32)
    if [ ! -f /data/config/config.json ]; then
        echo '{\"companion_token\": \"'\$TOKEN'\"}' > /data/config/config.json
        chown haana:haana /data/config/config.json
    else
        if command -v jq &>/dev/null; then
            TMP=\$(jq --arg t \"\$TOKEN\" '.companion_token = \$t' /data/config/config.json)
            echo \"\$TMP\" > /data/config/config.json
        else
            python3 -c \"
import json, sys
with open('/data/config/config.json') as f: cfg = json.load(f)
cfg['companion_token'] = sys.argv[1]
with open('/data/config/config.json', 'w') as f: json.dump(cfg, f, indent=2)
\" \"\$TOKEN\"
        fi
    fi
    chmod 600 /data/config/config.json

    # Token fuer spaetere Ausgabe sichern
    echo \"\$TOKEN\" > /tmp/haana_token
    chmod 600 /tmp/haana_token

    # Docker Compose als haana-User starten
    cd /opt/haana
    sudo -u haana docker compose up -d
"
echo -e "${GREEN}  HAANA eingerichtet und gestartet.${NC}"

# ── Schritt 6: Token und IP auslesen ─────────────────────────────────────────
step 6 6 "Abschlussinformationen ermitteln..."
sleep 3
TOKEN=$(pct exec "$CTID" -- cat /tmp/haana_token 2>/dev/null || echo "unbekannt")
IP=$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}' || echo "unbekannt")

# ── Abschlussmeldung ──────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}┌─────────────────────────────────────────────────────┐${NC}"
echo -e "${GREEN}${BOLD}│  HAANA erfolgreich installiert!                     │${NC}"
echo -e "${GREEN}${BOLD}├─────────────────────────────────────────────────────┤${NC}"
printf "${GREEN}${BOLD}│${NC}  Admin UI:    http://%-31s${GREEN}${BOLD}│${NC}\n" "$IP:8080"
printf "${GREEN}${BOLD}│${NC}  Token:       %-36s${GREEN}${BOLD}│${NC}\n" "${TOKEN:0:32}..."
echo -e "${GREEN}${BOLD}├─────────────────────────────────────────────────────┤${NC}"
echo -e "${GREEN}${BOLD}│  Naechste Schritte:                                 │${NC}"
echo -e "${GREEN}${BOLD}│  1. HAANA Companion Addon in HA installieren        │${NC}"
echo -e "${GREEN}${BOLD}│     Repository: https://github.com/alicezone/haana │${NC}"
echo -e "${GREEN}${BOLD}│  2. URL + Token in Addon-Konfiguration eintragen    │${NC}"
echo -e "${GREEN}${BOLD}│  3. API-Key in Admin UI konfigurieren               │${NC}"
echo -e "${GREEN}${BOLD}└─────────────────────────────────────────────────────┘${NC}"
echo ""
echo -e "${YELLOW}  Vollstaendiger Token (fuer Addon-Konfiguration):${NC}"
echo "  $TOKEN"
echo ""
