#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# One-time server preparation for EVE War Bot on a fresh Ubuntu droplet
# (DigitalOcean 1 GB RAM / 1-2 vCPU, Ubuntu 22.04 or 24.04).
#
#   sudo bash scripts/setup-droplet.sh
#
# What it does (safe to run again):
#   1. installs updates + git, curl, ufw, unattended-upgrades
#   2. creates a 1 GB swap file (protects a 1 GB server from out-of-memory kills)
#   3. installs Docker Engine + the compose plugin from Docker's official repository
#   4. sets Docker-wide log rotation
#   5. enables the firewall (only SSH allowed in - the bot needs no open ports)
# -----------------------------------------------------------------------------
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root:  sudo bash $0" >&2
  exit 1
fi

say() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }

# A fresh droplet installs updates on its own right after the first boot
# (cloud-init / unattended-upgrades) and holds the apt lock meanwhile.
# Wait for that instead of failing with "Could not get lock /var/lib/apt/lists/lock".
wait_for_apt() {
  if command -v cloud-init >/dev/null 2>&1; then
    cloud-init status --wait >/dev/null 2>&1 || true
  fi
  local waited=0
  while fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock \
              /var/lib/apt/lists/lock /var/cache/apt/archives/lock >/dev/null 2>&1; do
    if (( waited == 0 )); then
      echo "Ubuntu is still installing its own updates in the background - waiting..."
    fi
    if (( waited >= 1200 )); then
      echo "apt has been busy for 20 minutes. Check with:  ps aux | grep -E 'apt|dpkg'" >&2
      exit 1
    fi
    sleep 10; waited=$((waited + 10))
  done
}
# also let apt itself wait up to 10 min for the dpkg lock
APT=(apt-get -y -o DPkg::Lock::Timeout=600)

say "1/5 Updating system packages"
export DEBIAN_FRONTEND=noninteractive
wait_for_apt
"${APT[@]}" update
"${APT[@]}" upgrade
"${APT[@]}" install ca-certificates curl git ufw unattended-upgrades nano psmisc

say "2/5 Swap file (1 GB)"
if swapon --show | grep -q '/swapfile'; then
  echo "Swap already active - skipping."
else
  fallocate -l 1G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=1024
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
# use swap only when really needed
sysctl -w vm.swappiness=10 >/dev/null
echo 'vm.swappiness=10' > /etc/sysctl.d/99-eve-war-bot.conf

say "3/5 Docker Engine + compose plugin"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "Docker already installed: $(docker --version)"
else
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  wait_for_apt
  "${APT[@]}" update
  "${APT[@]}" install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

# let the normal (sudo) user run docker without sudo
if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  usermod -aG docker "$SUDO_USER"
  echo "Added $SUDO_USER to the docker group (log out and in again to use it)."
fi

say "4/5 Docker log rotation (all containers)"
mkdir -p /etc/docker
if [[ ! -f /etc/docker/daemon.json ]]; then
  cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "5m", "max-file": "3" }
}
JSON
  systemctl restart docker
else
  echo "/etc/docker/daemon.json exists - left unchanged."
fi

say "5/5 Firewall (allow SSH only)"
ufw allow OpenSSH >/dev/null
ufw --force enable >/dev/null
ufw status | head -5

say "Done."
echo "Memory:"; free -h
echo
echo "Next: cd into the eve-war-bot folder and run:  bash scripts/bot.sh init"
