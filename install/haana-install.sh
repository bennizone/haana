#!/usr/bin/env bash
# Läuft INNERHALB des LXC — wird von install.sh via lxc-attach aufgerufen

source <(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/misc/install.func)

msg_info "Installiere Basis-Pakete"
$STD apt-get update
$STD apt-get install -y curl git ca-certificates sudo openssl
msg_ok "Basis-Pakete installiert"

msg_info "Installiere Node.js LTS"
$STD curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -
$STD apt-get install -y nodejs
msg_ok "Node.js $(node --version) installiert"

msg_info "Installiere Docker"
$STD curl -fsSL https://get.docker.com | sh
msg_ok "Docker installiert"

msg_info "Installiere Claude Code"
$STD npm install -g @anthropic-ai/claude-code
msg_ok "Claude Code installiert"

msg_info "Richte haana User ein"
useradd -m -u 1000 -s /bin/bash haana 2>/dev/null || true
usermod -aG docker haana
echo 'haana ALL=(ALL) NOPASSWD: /usr/bin/docker, /usr/local/bin/docker' > /etc/sudoers.d/haana
chmod 0440 /etc/sudoers.d/haana
msg_ok "haana User eingerichtet"

msg_info "Klone HAANA Repository"
if [ -d /opt/haana/.git ]; then
  $STD git -C /opt/haana pull
else
  $STD git clone https://github.com/alicezone/haana /opt/haana
fi
chown -R haana:haana /opt/haana
msg_ok "HAANA Repository geklont"

msg_info "Richte Verzeichnisse ein"
mkdir -p /data/config /data/logs /data/context /media/haana
chown -R haana:haana /data /media/haana
if [ ! -f /opt/haana/.env ]; then
  cp /opt/haana/.env.example /opt/haana/.env
  chown haana:haana /opt/haana/.env
fi
msg_ok "Verzeichnisse eingerichtet"

msg_info "Generiere Companion Token"
TOKEN=$(openssl rand -hex 32)
if [ ! -f /data/config/config.json ]; then
  echo "{\"companion_token\": \"$TOKEN\"}" > /data/config/config.json
  chown haana:haana /data/config/config.json
else
  python3 -c "
import json, sys
with open('/data/config/config.json') as f: cfg = json.load(f)
cfg['companion_token'] = sys.argv[1]
with open('/data/config/config.json', 'w') as f: json.dump(cfg, f, indent=2)
" "$TOKEN"
fi
chmod 600 /data/config/config.json
echo "$TOKEN" > /tmp/haana_token
chmod 600 /tmp/haana_token
msg_ok "Companion Token generiert"

msg_info "Setze Admin-Passwort-Hash"
if [ -f /tmp/haana_rootpw ]; then
    pip3 install -q bcrypt 2>/dev/null || true
    python3 -c "
import bcrypt, json
pw = open('/tmp/haana_rootpw').read().strip()
h = bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
path = '/data/config/config.json'
try:
    with open(path) as f: cfg = json.load(f)
except Exception:
    cfg = {}
cfg['admin_password_hash'] = h
cfg.pop('admin_token', None)
with open(path, 'w') as f: json.dump(cfg, f, indent=2)
"
    rm -f /tmp/haana_rootpw
    msg_ok "Admin-Passwort-Hash gesetzt"
else
    msg_warn "Kein Root-Passwort gefunden — Admin-Passwort muss manuell gesetzt werden"
fi

cat > /home/haana/.bash_profile << 'BPEOF'
export PATH=$PATH:/usr/local/bin

if [[ $- == *i* ]]; then
  cd /opt/haana
  echo ""
  echo "  HAANA Dev-Umgebung  |  'exit' beendet Claude Code"
  echo ""
  claude --dangerously-skip-permissions --continue
fi
BPEOF
chown haana:haana /home/haana/.bash_profile

msg_info "Starte HAANA Stack"
cd /opt/haana && docker compose up -d
msg_ok "HAANA Stack gestartet"

motd_ssh
customize
