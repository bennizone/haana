#!/usr/bin/env bash
# HAANA Proxmox LXC Installer
# Ausfuehren auf dem Proxmox-Host:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/alicezone/haana/main/install.sh)"

set -eo pipefail

# ── Farben & Icons ─────────────────────────────────────────────────────────────
YW=$(printf '\033[33m')
BL=$(printf '\033[36m')
RD=$(printf '\033[01;31m')
GN=$(printf '\033[1;92m')
CL=$(printf '\033[m')
CM="  ✔ "
CROSS="  ✖ "
INFO="  ℹ "

msg_ok()    { echo -e "${CM}${GN}$*${CL}"; }
msg_info()  { echo -e "${INFO}${BL}$*${CL}"; }
msg_error() { echo -e "${CROSS}${RD}$*${CL}"; }
msg_warn()  { echo -e "  ⚠ ${YW}$*${CL}"; }

# ── Fehlerbehandlung ───────────────────────────────────────────────────────────
CTID=""
trap 'catch_error $LINENO' ERR

catch_error() {
    msg_error "Fehler in Zeile $1 — Installation abgebrochen."
    if [ -n "$CTID" ] && pct status "$CTID" &>/dev/null; then
        msg_warn "Container $CTID ggf. teilweise erstellt. Bereinigen mit:"
        msg_warn "  pct stop $CTID && pct destroy $CTID"
    fi
    exit 1
}

# ── Voraussetzungen ────────────────────────────────────────────────────────────
check_prerequisites() {
    if ! command -v pct &>/dev/null || ! command -v pvesh &>/dev/null; then
        msg_error "Dieses Script muss auf einem Proxmox VE Host ausgefuehrt werden."
        exit 1
    fi
    if ! command -v whiptail &>/dev/null; then
        apt-get install -y -qq whiptail 2>/dev/null || true
        command -v whiptail &>/dev/null || { msg_error "whiptail nicht verfuegbar."; exit 1; }
    fi
}

# ── IP-Validierung ─────────────────────────────────────────────────────────────
validate_ip() {
    local ip="$1" label="$2"
    if [[ ! "$ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}(/[0-9]{1,2})?$ ]]; then
        msg_error "'$ip' ist keine gueltige IP fuer $label"
        exit 1
    fi
}

# ── Storage-Detection ──────────────────────────────────────────────────────────
get_template_storage() {
    local s
    s=$(pvesm status --content vztmpl 2>/dev/null | awk 'NR>1 && $3=="active" {print $1}' | head -1)
    if [ -z "$s" ]; then
        s=$(pvesm status 2>/dev/null | awk 'NR>1 && $3=="active" && ($2=="dir"||$2=="zfspool"||$2=="cifs"||$2=="nfs") {print $1}' | head -1)
    fi
    if [ -z "$s" ]; then
        msg_error "Kein geeigneter Template-Storage gefunden."; exit 1
    fi
    echo "$s"
}

get_disk_storage() {
    local s
    s=$(pvesm status --content rootdir 2>/dev/null | awk 'NR>1 && $3=="active" {print $1}' | head -1)
    if [ -z "$s" ]; then
        s=$(pvesm status 2>/dev/null | awk 'NR>1 && $3=="active" && ($2=="dir"||$2=="zfspool"||$2=="lvm"||$2=="lvmthin") {print $1}' | head -1)
    fi
    if [ -z "$s" ]; then
        msg_error "Kein geeigneter Disk-Storage gefunden."; exit 1
    fi
    echo "$s"
}

# ── Template ermitteln ─────────────────────────────────────────────────────────
get_template() {
    local os_search="debian-12-standard"
    TMPL_STORAGE=$(get_template_storage)
    msg_info "Template-Storage: $TMPL_STORAGE"

    msg_info "Suche Debian 12 Template..."
    local local_tmpl
    local_tmpl=$(pveam list "$TMPL_STORAGE" 2>/dev/null | awk '{print $1}' | grep "$os_search" | sort -V | tail -1 || true)
    if [ -n "$local_tmpl" ]; then
        TEMPLATE=$(basename "$local_tmpl")
        msg_ok "Template lokal gefunden: $TEMPLATE"
        return
    fi

    msg_info "Aktualisiere Template-Katalog..."
    pveam update >/dev/null 2>&1 || true

    local online_tmpl
    online_tmpl=$(pveam available -section system 2>/dev/null | awk '{print $2}' | grep "$os_search" | sort -V | tail -1 || true)
    if [ -z "$online_tmpl" ]; then
        msg_warn "Kein Debian 12 gefunden — versuche Debian 13..."
        online_tmpl=$(pveam available -section system 2>/dev/null | awk '{print $2}' | grep "debian-13-standard" | sort -V | tail -1 || true)
    fi
    if [ -z "$online_tmpl" ]; then
        msg_error "Kein kompatibles Debian Template gefunden."
        exit 1
    fi

    msg_info "Lade Template herunter: $online_tmpl"
    pveam download "$TMPL_STORAGE" "$online_tmpl"
    TEMPLATE="$online_tmpl"
    msg_ok "Template heruntergeladen: $TEMPLATE"
}

# ── Interaktive Konfiguration ──────────────────────────────────────────────────
configure() {
    local BT="HAANA Proxmox LXC Installer"

    NEXT_ID=$(pvesh get /cluster/nextid 2>/dev/null || echo "200")
    CTID=$(whiptail --backtitle "$BT" --title "CONTAINER ID" \
        --inputbox "Container ID:" 10 58 "$NEXT_ID" \
        --ok-button "Weiter" --cancel-button "Abbrechen" \
        3>&1 1>&2 2>&3) || { msg_error "Abgebrochen."; exit 0; }

    HOSTNAME=$(whiptail --backtitle "$BT" --title "HOSTNAME" \
        --inputbox "Hostname:" 10 58 "haana" \
        --ok-button "Weiter" --cancel-button "Abbrechen" \
        3>&1 1>&2 2>&3) || { msg_error "Abgebrochen."; exit 0; }

    CORES=$(whiptail --backtitle "$BT" --title "CPU CORES" \
        --inputbox "CPU Cores (min. 2, empfohlen: 4):" 10 58 "4" \
        --ok-button "Weiter" --cancel-button "Abbrechen" \
        3>&1 1>&2 2>&3) || { msg_error "Abgebrochen."; exit 0; }
    [ "${CORES:-0}" -lt 2 ] 2>/dev/null && { msg_warn "Minimum 2 Cores."; CORES=2; }

    RAM=$(whiptail --backtitle "$BT" --title "RAM" \
        --inputbox "RAM in MB (min. 2048, empfohlen: 4096):" 10 58 "4096" \
        --ok-button "Weiter" --cancel-button "Abbrechen" \
        3>&1 1>&2 2>&3) || { msg_error "Abgebrochen."; exit 0; }
    [ "${RAM:-0}" -lt 2048 ] 2>/dev/null && { msg_warn "Minimum 2048 MB."; RAM=2048; }

    DISK=$(whiptail --backtitle "$BT" --title "DISK" \
        --inputbox "Disk in GB (min. 20, empfohlen: 50):" 10 58 "50" \
        --ok-button "Weiter" --cancel-button "Abbrechen" \
        3>&1 1>&2 2>&3) || { msg_error "Abgebrochen."; exit 0; }
    [ "${DISK:-0}" -lt 20 ] 2>/dev/null && { msg_warn "Minimum 20 GB."; DISK=20; }

    DISK_STORAGE=$(get_disk_storage)

    BRIDGE=$(whiptail --backtitle "$BT" --title "NETZWERK" \
        --inputbox "Bridge (z.B. vmbr0):" 10 58 "vmbr0" \
        --ok-button "Weiter" --cancel-button "Abbrechen" \
        3>&1 1>&2 2>&3) || { msg_error "Abgebrochen."; exit 0; }

    VLAN=$(whiptail --backtitle "$BT" --title "VLAN" \
        --inputbox "VLAN Tag (leer = kein VLAN):" 10 58 "" \
        --ok-button "Weiter" --cancel-button "Abbrechen" \
        3>&1 1>&2 2>&3) || { msg_error "Abgebrochen."; exit 0; }
    if [ -n "$VLAN" ]; then
        if ! [[ "$VLAN" =~ ^[0-9]+$ ]] || [ "$VLAN" -lt 1 ] || [ "$VLAN" -gt 4094 ]; then
            msg_error "VLAN Tag muss zwischen 1 und 4094 liegen."; exit 1
        fi
    fi

    IP_MODE=$(whiptail --backtitle "$BT" --title "IP KONFIGURATION" \
        --radiolist "Netzwerk-Konfiguration:" 12 58 2 \
        "dhcp"   "DHCP (automatisch)"  ON \
        "static" "Statische IP"        OFF \
        --ok-button "Weiter" --cancel-button "Abbrechen" \
        3>&1 1>&2 2>&3) || { msg_error "Abgebrochen."; exit 0; }

    if [ "$IP_MODE" = "static" ]; then
        STATIC_IP=$(whiptail --backtitle "$BT" --title "STATISCHE IP" \
            --inputbox "IP mit CIDR (z.B. 192.168.1.100/24):" 10 58 "" \
            --ok-button "Weiter" --cancel-button "Abbrechen" \
            3>&1 1>&2 2>&3) || { msg_error "Abgebrochen."; exit 0; }
        GATEWAY=$(whiptail --backtitle "$BT" --title "GATEWAY" \
            --inputbox "Gateway (z.B. 192.168.1.1):" 10 58 "" \
            --ok-button "Weiter" --cancel-button "Abbrechen" \
            3>&1 1>&2 2>&3) || { msg_error "Abgebrochen."; exit 0; }
        DNS_SERVER=$(whiptail --backtitle "$BT" --title "DNS" \
            --inputbox "DNS-Server (z.B. 192.168.1.1):" 10 58 "" \
            --ok-button "Weiter" --cancel-button "Abbrechen" \
            3>&1 1>&2 2>&3) || { msg_error "Abgebrochen."; exit 0; }
        validate_ip "$STATIC_IP" "IP-Adresse"
        validate_ip "$GATEWAY"   "Gateway"
        validate_ip "$DNS_SERVER" "DNS"
        NET_CONFIG="ip=$STATIC_IP,gw=$GATEWAY"
        NET_DISPLAY="$STATIC_IP (GW: $GATEWAY)"
    else
        NET_CONFIG="ip=dhcp"
        NET_DISPLAY="DHCP"
    fi

    # Root-Passwort
    local PW1 PW2
    PW1=$(whiptail --backtitle "$BT" --title "ROOT PASSWORT" \
        --passwordbox "Root-Passwort fuer den Container:" 10 58 \
        --ok-button "Weiter" --cancel-button "Abbrechen" \
        3>&1 1>&2 2>&3) || { msg_error "Abgebrochen."; exit 0; }
    PW2=$(whiptail --backtitle "$BT" --title "ROOT PASSWORT" \
        --passwordbox "Passwort wiederholen:" 10 58 \
        --ok-button "Weiter" --cancel-button "Abbrechen" \
        3>&1 1>&2 2>&3) || { msg_error "Abgebrochen."; exit 0; }
    if [ "$PW1" != "$PW2" ]; then
        msg_error "Passwoerter stimmen nicht ueberein."; exit 1
    fi
    ROOT_PASSWORD="$PW1"

    ANTHROPIC_KEY=$(whiptail --backtitle "$BT" --title "ANTHROPIC API-KEY (OPTIONAL)" \
        --inputbox "API-Key (leer = spaeter im Admin UI eintragen):" 10 78 "" \
        --ok-button "Weiter" --cancel-button "Ueberspringen" \
        3>&1 1>&2 2>&3) || ANTHROPIC_KEY=""

    if [ -n "$ANTHROPIC_KEY" ] && [[ ! "$ANTHROPIC_KEY" =~ ^sk-ant- ]]; then
        msg_warn "API-Key sieht ungewoehnlich aus (erwartet: sk-ant-...) — weiter auf eigene Gefahr."
    fi

    VLAN_SUFFIX=""
    [ -n "$VLAN" ] && VLAN_SUFFIX=",tag=$VLAN"

    whiptail --backtitle "$BT" --title "ZUSAMMENFASSUNG" --yesno \
"Container ID:  $CTID
Hostname:      $HOSTNAME
CPU:           $CORES Cores
RAM:           $RAM MB
Disk:          $DISK GB  (Storage: $DISK_STORAGE)
Bridge:        $BRIDGE${VLAN:+ (VLAN $VLAN)}
Netzwerk:      $NET_DISPLAY

Fortfahren?" 20 58 \
        --yes-button "Installieren" --no-button "Abbrechen" \
        3>&1 1>&2 2>&3 || { msg_error "Abgebrochen."; exit 0; }
}

# ── LXC erstellen ──────────────────────────────────────────────────────────────
create_lxc() {
    msg_info "Erstelle LXC Container $CTID..."
    pct create "$CTID" "${TMPL_STORAGE}:vztmpl/${TEMPLATE}" \
        -hostname "$HOSTNAME" \
        -cores "$CORES" \
        -memory "$RAM" \
        -rootfs "${DISK_STORAGE}:${DISK}" \
        -net0 "name=eth0,bridge=${BRIDGE}${VLAN_SUFFIX},${NET_CONFIG}" \
        -unprivileged 1 \
        -features nesting=1 \
        -ostype debian \
        -start 1
    msg_ok "Container erstellt und gestartet."

    msg_info "Warte auf Container-Netzwerk (max. 30s)..."
    local net_ok=0
    for ((i=10; i>0; i--)); do
        if pct exec "$CTID" -- hostname -I 2>/dev/null | grep -q "[0-9]"; then
            net_ok=1; break
        fi
        sleep 3
    done
    [ "$net_ok" -eq 0 ] && { msg_error "Container hat nach 30s kein Netzwerk."; exit 1; }

    if [ "$IP_MODE" = "static" ] && [ -n "$DNS_SERVER" ]; then
        pct exec "$CTID" -- bash -c "echo 'nameserver $DNS_SERVER' > /etc/resolv.conf"
    fi

    if [ -n "$ROOT_PASSWORD" ]; then
        pct exec "$CTID" -- bash -c "echo 'root:$ROOT_PASSWORD' | chpasswd"
        # Passwort-Login per SSH erlauben
        pct exec "$CTID" -- bash -c "sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config && systemctl restart ssh"
        msg_ok "Root-Passwort gesetzt."
    fi

    # SSH-Key des Proxmox-Hosts eintragen
    local HOST_PUBKEY
    HOST_PUBKEY=$(cat /root/.ssh/id_ed25519.pub 2>/dev/null || cat /root/.ssh/id_rsa.pub 2>/dev/null || true)
    if [ -n "$HOST_PUBKEY" ]; then
        pct exec "$CTID" -- bash -c "mkdir -p /root/.ssh && chmod 700 /root/.ssh && echo '$HOST_PUBKEY' >> /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys"
        msg_ok "Proxmox SSH-Key eingetragen."
    fi
}

# ── HAANA Bootstrap ────────────────────────────────────────────────────────────
bootstrap() {
    msg_info "Installiere System-Pakete..."
    pct exec "$CTID" -- bash -c "
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq curl git ca-certificates sudo openssl
        curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - 2>/dev/null
        apt-get install -y -qq nodejs
    "
    msg_ok "System-Pakete installiert."

    msg_info "Installiere Docker..."
    pct exec "$CTID" -- bash -c "curl -fsSL https://get.docker.com | sh" >/dev/null
    msg_ok "Docker installiert."

    msg_info "Installiere Claude Code CLI..."
    pct exec "$CTID" -- bash -c "npm install -g @anthropic-ai/claude-code 2>&1 | tail -3"
    msg_ok "Claude Code installiert."

    msg_info "Richte HAANA ein..."
    pct exec "$CTID" -- bash -c "
        set -e
        useradd -m -u 1000 -s /bin/bash haana 2>/dev/null || true
        usermod -aG docker haana
        echo 'haana ALL=(ALL) NOPASSWD: /usr/bin/docker, /usr/local/bin/docker' > /etc/sudoers.d/haana
        chmod 0440 /etc/sudoers.d/haana

        if [ -d /opt/haana/.git ]; then
            cd /opt/haana && git pull
        else
            git clone https://github.com/alicezone/haana /opt/haana
        fi
        chown -R haana:haana /opt/haana

        mkdir -p /data/config /data/logs /media/haana
        chown -R haana:haana /data /media/haana

        if [ ! -f /opt/haana/.env ]; then
            cp /opt/haana/.env.example /opt/haana/.env
            chown haana:haana /opt/haana/.env
        fi

        cat > /home/haana/.bash_profile << 'BPEOF'
export PATH=\$PATH:/usr/local/bin

if [[ \$- == *i* ]]; then
    cd /opt/haana
    echo ''
    echo '  HAANA Dev-Umgebung  |  exit beendet Claude Code'
    echo ''
    claude --dangerously-skip-permissions --continue
fi
BPEOF
        chown haana:haana /home/haana/.bash_profile

        # Claude Code Seed: settings + project memory
        mkdir -p /home/haana/.claude/projects/-opt-haana/memory
        cp /opt/haana/scripts/claude-seed/settings.json /home/haana/.claude/settings.json
        cp /opt/haana/scripts/claude-seed/memory/MEMORY.md \
           /home/haana/.claude/projects/-opt-haana/memory/MEMORY.md
        cp /opt/haana/scripts/claude-seed/memory/architecture.md \
           /home/haana/.claude/projects/-opt-haana/memory/architecture.md
        chown -R haana:haana /home/haana/.claude

        TOKEN=\$(openssl rand -hex 32)
        if [ ! -f /data/config/config.json ]; then
            echo '{\"companion_token\": \"'\$TOKEN'\"}' > /data/config/config.json
            chown haana:haana /data/config/config.json
        else
            python3 -c \"
import json, sys
with open('/data/config/config.json') as f: cfg = json.load(f)
cfg['companion_token'] = sys.argv[1]
with open('/data/config/config.json', 'w') as f: json.dump(cfg, f, indent=2)
\" \"\$TOKEN\"
        fi
        chmod 600 /data/config/config.json
        echo \"\$TOKEN\" > /tmp/haana_token
        chmod 600 /tmp/haana_token

        cd /opt/haana && docker compose up -d
    "
    msg_ok "HAANA eingerichtet und gestartet."
}

# ── API-Key setzen ─────────────────────────────────────────────────────────────
set_api_key() {
    [ -z "$ANTHROPIC_KEY" ] && return
    msg_info "Setze Anthropic API-Key..."
    local TMPKEY
    TMPKEY=$(mktemp)
    trap "rm -f '$TMPKEY'" EXIT
    printf '%s' "$ANTHROPIC_KEY" > "$TMPKEY"
    pct push "$CTID" "$TMPKEY" /tmp/haana_apikey
    rm -f "$TMPKEY"
    trap - EXIT
    pct exec "$CTID" -- bash -c '
        KEY=$(cat /tmp/haana_apikey); rm -f /tmp/haana_apikey
        if grep -q "ANTHROPIC_API_KEY" /opt/haana/.env 2>/dev/null; then
            sed -i "s|^#\?[[:space:]]*ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$KEY|" /opt/haana/.env
        else
            echo "ANTHROPIC_API_KEY=$KEY" >> /opt/haana/.env
        fi
        chown haana:haana /opt/haana/.env
    '
    msg_ok "API-Key gesetzt."
}

# ── Abschlussmeldung ───────────────────────────────────────────────────────────
finish() {
    local TOKEN IP ADMIN_PORT
    sleep 2
    TOKEN=$(pct exec "$CTID" -- cat /tmp/haana_token 2>/dev/null || echo "unbekannt")
    IP=$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}' || echo "unbekannt")
    ADMIN_PORT=8080

    echo ""
    msg_ok "HAANA LXC erfolgreich installiert!"
    echo ""
    echo -e "${GN}  Admin UI:   http://$IP:$ADMIN_PORT${CL}"
    echo -e "${GN}  Token:      ${TOKEN:0:16}...${CL}"
    echo ""
    echo -e "${BL}  Naechste Schritte:${CL}"
    echo "  1. HAANA Companion Addon in HA installieren"
    echo "     Repository: https://github.com/alicezone/haana"
    echo "  2. URL + Token in Addon eintragen"
    echo "  3. API-Key im Admin UI konfigurieren (falls nicht gesetzt)"
    echo "  4. Dev-Zugang: ssh root@$IP → su - haana"
    echo ""
    echo -e "${YW}  Vollstaendiger Token:${CL}"
    echo "  $TOKEN"
    echo ""
}

# ── Hauptprogramm ──────────────────────────────────────────────────────────────
clear
echo ""
echo -e "${GN}"
cat << 'EOF'
  _   _    _    _    _   _    _
 | | | |  / \  / \  | \ | |  / \
 | |_| | / _ \/ _ \ |  \| | / _ \
 |  _  |/ ___ \ ___ \| |\  |/ ___ \
 |_| |_/_/   \_\   /_|_| \_/_/   \_\
EOF
echo -e "${CL}"
echo -e "${BL}  HAANA — Home AI Assistant Network Agent${CL}"
echo -e "${BL}  Proxmox LXC Installer${CL}"
echo ""

check_prerequisites
get_template
configure
create_lxc
bootstrap
set_api_key
finish
