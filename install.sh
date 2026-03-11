#!/usr/bin/env bash
source <(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/misc/build.func)

APP="HAANA"
var_tags="${var_tags:-haana;docker;ai}"
var_cpu="${var_cpu:-4}"
var_ram="${var_ram:-4096}"
var_disk="${var_disk:-50}"
var_os="${var_os:-debian}"
var_version="${var_version:-12}"
var_unprivileged="${var_unprivileged:-1}"

header_info "$APP"
variables
color
catch_errors

function update_script() {
  header_info
  check_container_storage
  check_container_resources
  msg_info "Aktualisiere HAANA Stack"
  pct exec "$CTID" -- bash -c "cd /opt/haana && bash update.sh"
  msg_ok "HAANA Stack aktualisiert"
  exit
}

function build_container() {
  create_lxc_container

  msg_info "Installiere HAANA"
  lxc-attach -n "$CTID" -- bash -c \
    "$(curl -fsSL https://raw.githubusercontent.com/alicezone/haana/main/install/haana-install.sh)"
  msg_ok "HAANA installiert"
}

start
build_container
description
