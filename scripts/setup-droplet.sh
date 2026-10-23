#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Server preparation for EVE War Bot (Ubuntu 20.04 / 22.04 / 24.04, new or existing server).
# Safe on a server that already runs other apps: it only ADDS what is missing
# and never changes the firewall, open ports or running services.
#
#   sudo bash scripts/setup-droplet.sh            # install only what is missing
#   sudo bash scripts/setup-droplet.sh --upgrade  # additionally: apt upgrade of all packages
#
# What it does (safe to run again):
#   1. installs missing tools: ca-certificates, curl, git, nano, psmisc
#   2. creates a 1 GB swap file - only if the server has no swap at all
#   3. installs Docker Engine + compose plugin - only if Docker is missing
#   4. sets Docker log rotation - only when Docker was installed by this script
#      (an existing Docker setup and its containers are never restarted)
#
# What it never does:
#   - environment variables or kernel settings (no /etc/environment, profile, sysctl)
#   - firewall (ufw / iptables) changes, opening or closing ports
#   - restarting Docker or other services that were already running
#   - upgrading all packages (unless you pass --upgrade)
# -----------------------------------------------------------------------------
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root:  sudo bash $0" >&2
  exit 1
fi

UPGRADE=0
for arg in "$@"; do
  case "$arg" in
    --upgrade) UPGRADE=1 ;;
    *) echo "Unknown option: $arg (allowed: --upgrade)" >&2; exit 1 ;;
  esac
done

say() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }

# Another apt run (automatic security updates / unattended-upgrades, another
# installation, or cloud-init on a brand-new server) may hold the apt lock.
# Wait for it instead of failing with "Could not get lock /var/lib/apt/lists/lock".
wait_for_apt() {
  if command -v cloud-init >/dev/null 2>&1; then
    cloud-init status --wait >/dev/null 2>&1 || true
  fi
  local waited=0
  while fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock \
              /var/lib/apt/lists/lock /var/cache/apt/archives/lock >/dev/null 2>&1; do
    if (( waited == 0 )); then
      echo "apt is busy (another installation or automatic updates) - waiting..."
    fi
    if (( waited >= 1200 )); then
      echo "apt has been busy for 20 minutes. Check with:  ps aux | grep -E 'apt|dpkg'" >&2
      exit 1
    fi
    sleep 10; waited=$((waited + 10))
  done
}
# also let apt itself wait up to 10 min for the dpkg lock
# DEBIAN_FRONTEND is passed to apt-get only (via env), not exported to the shell/system
APT=(env DEBIAN_FRONTEND=noninteractive apt-get -y -o DPkg::Lock::Timeout=600)

say "1/4 Basic tools"
wait_for_apt
"${APT[@]}" update
if [[ $UPGRADE == 1 ]]; then
  echo "--upgrade given: upgrading all packages"
  "${APT[@]}" upgrade
fi
missing=()
for pkg in ca-certificates curl git nano psmisc; do
  dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if (( ${#missing[@]} )); then
  "${APT[@]}" install "${missing[@]}"
else
  echo "All present - nothing to install."
fi

say "2/4 Swap"
if [[ -n "$(swapon --show --noheadings)" ]]; then
  echo "Swap already configured - left unchanged:"; swapon --show
elif [[ -e /swapfile ]]; then
  echo "/swapfile exists but is not active - left unchanged (check it manually)."
else
  fallocate -l 1G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=1024
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "Created 1 GB /swapfile."
fi

say "3/4 Docker Engine + compose plugin"
DOCKER_NEW=0
if command -v docker >/dev/null 2>&1; then
  echo "Docker already installed: $(docker --version) - left unchanged."
  if ! docker compose version >/dev/null 2>&1; then
    echo "The 'docker compose' plugin is missing - installing only the plugin."
    wait_for_apt
    "${APT[@]}" install docker-compose-plugin
  fi
else
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  # shellcheck disable=SC1091
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  wait_for_apt
  "${APT[@]}" update
  "${APT[@]}" install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
  DOCKER_NEW=1
fi

# let the normal (sudo) user run docker without sudo
if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]] && ! id -nG "$SUDO_USER" | grep -qw docker; then
  usermod -aG docker "$SUDO_USER"
  echo "Added $SUDO_USER to the docker group (log out and in again to use it)."
fi

say "4/4 Docker log rotation"
if [[ $DOCKER_NEW == 1 && ! -f /etc/docker/daemon.json ]]; then
  mkdir -p /etc/docker
  cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "5m", "max-file": "3" }
}
JSON
  systemctl restart docker      # fresh install: no other containers to disturb
  echo "Set for all containers."
else
  echo "Existing Docker setup - not changed, nothing restarted."
  echo "(The bot limits its own logs in docker-compose.yml.)"
fi

say "Done."
echo "Firewall and open ports were NOT touched - the bot only makes outgoing connections."
echo "Memory:"; free -h
echo
echo "Next: cd into the eve-war-bot folder and run:  bash scripts/bot.sh init"
