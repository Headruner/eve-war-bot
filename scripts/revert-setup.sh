#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Revert what the EARLIER scripts/setup-droplet.sh (1.2.0 and the first 1.3.0 version,
# the ones that enable the firewall) changed:
#
#   1. firewall: "ufw allow OpenSSH" + "ufw --force enable"
#   2. /etc/docker/daemon.json (log rotation) + docker restart
#   3. your user added to the "docker" group
#   4. Docker Engine installed from download.docker.com (+ apt source + key)
#   5. packages installed by its step 1 (ca-certificates curl git ufw unattended-upgrades nano)
#   6. /etc/sysctl.d/99-eve-war-bot.conf  (vm.swappiness=10)
#   7. 1 GB /swapfile + its /etc/fstab line
#   (the "apt-get upgrade" of all packages cannot be undone - Ubuntu has no rollback)
#
# It decides per item whether the original script really made the change
# (apt history log, file contents, time stamps), shows what it found and asks
# before every change. Nothing is removed without your "y".
#
#   sudo bash scripts/revert-setup.sh --dry-run   # only show what would be reverted
#   sudo bash scripts/revert-setup.sh             # revert, asking item by item
# -----------------------------------------------------------------------------
set -uo pipefail

DRY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    *) echo "Unknown option: $arg (allowed: --dry-run)" >&2; exit 1 ;;
  esac
done

if [[ $EUID -ne 0 && $DRY == 0 ]]; then
  echo "Please run as root:  sudo bash $0   (or --dry-run to only look)" >&2
  exit 1
fi

APT_HISTORY=${APT_HISTORY:-/var/log/apt/history.log}
SYSCTL_FILE=/etc/sysctl.d/99-eve-war-bot.conf
DAEMON_JSON=/etc/docker/daemon.json
DOCKER_LIST=/etc/apt/sources.list.d/docker.list
DOCKER_KEY=/etc/apt/keyrings/docker.asc
TARGET_USER=${SUDO_USER:-}

say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
info() { printf '   %s\n' "$*"; }
skip() { printf '   \033[2m- %s\033[0m\n' "$*"; }
done_(){ printf '   \033[1;32m✔ %s\033[0m\n' "$*"; }

# ask "question" -> 0 for yes. In --dry-run it never changes anything.
ask() {
  if [[ $DRY == 1 ]]; then
    printf '   \033[1;33m[dry-run] would ask: %s\033[0m\n' "$1"
    return 1
  fi
  local a
  read -r -p "   $1 [y/N] " a </dev/tty || return 1
  [[ $a == y || $a == Y || $a == yes ]]
}

# Packages that an apt run with the given command line NEWLY installed
# (read from /var/log/apt/history.log and its rotated .gz copies)
new_packages_from_history() {
  local pattern=$1
  {
    [[ -f $APT_HISTORY ]] && cat "$APT_HISTORY"
    for f in "$APT_HISTORY".*.gz; do [[ -f $f ]] && zcat "$f"; done
  } 2>/dev/null | awk -v pat="$pattern" '
    /^Start-Date:/ { cmd=""; inst="" }
    /^Commandline:/ { cmd=$0 }
    /^Install:/ { inst=$0 }
    /^End-Date:/ { if (index(cmd, pat) && inst != "") print inst }
  ' | sed 's/^Install: //' | tr -s ' ' '\n' | grep -E '^[a-z0-9][a-z0-9.+-]*:' | cut -d: -f1 | sort -u
}

if pgrep -f "setup-droplet.sh" >/dev/null 2>&1; then
  echo "setup-droplet.sh is still running. Let it finish first, then run this script." >&2
  exit 1
fi

[[ $DRY == 1 ]] && echo "DRY RUN - nothing will be changed."

# ---------------------------------------------------------------- 1. firewall
say "1/7 Firewall (ufw)"
if ! command -v ufw >/dev/null 2>&1; then
  skip "ufw not installed - nothing to revert"
elif ufw status 2>/dev/null | grep -q "Status: active"; then
  info "ufw is ACTIVE. Current rules:"
  ufw status numbered 2>/dev/null | sed 's/^/     /'
  info "Last change of /etc/ufw/ufw.conf: $(stat -c %y /etc/ufw/ufw.conf 2>/dev/null | cut -d. -f1)"
  info "The original script switched ufw on (only SSH allowed). If ufw was OFF before"
  info "the script ran, switching it off restores the old state."
  if ask "Switch the firewall OFF (ufw disable)?"; then
    ufw disable && done_ "ufw disabled - all ports work as before"
  else
    skip "kept. To allow your web app instead:  sudo ufw allow 80/tcp ; sudo ufw allow 443/tcp"
  fi
else
  skip "ufw is not active - nothing to revert"
fi

# ---------------------------------------------------------------- 2. daemon.json
say "2/7 Docker log settings ($DAEMON_JSON)"
if [[ -f $DAEMON_JSON ]] && tr -d ' \n' < "$DAEMON_JSON" | grep -qx '{"log-driver":"json-file","log-opts":{"max-size":"5m","max-file":"3"}}'; then
  info "Found exactly the file the original script writes."
  info "Removing it needs a Docker restart: running containers stop for a few seconds"
  info "and come back if they have a restart policy."
  if ask "Remove $DAEMON_JSON and restart Docker?"; then
    rm -f "$DAEMON_JSON" && systemctl restart docker && done_ "removed, Docker restarted"
  fi
elif [[ -f $DAEMON_JSON ]]; then
  skip "$DAEMON_JSON has other content - not written by the script, left unchanged"
else
  skip "not present - nothing to revert"
fi

# ---------------------------------------------------------------- 3. docker group
say "3/7 Docker group membership"
if [[ -n $TARGET_USER && $TARGET_USER != root ]] && id -nG "$TARGET_USER" 2>/dev/null | grep -qw docker; then
  info "User $TARGET_USER is in the 'docker' group (the original script adds the sudo user)."
  info "If $TARGET_USER used docker without sudo BEFORE the script, keep this."
  if ask "Remove $TARGET_USER from the docker group?"; then
    gpasswd -d "$TARGET_USER" docker && done_ "removed (takes effect at next login)"
  fi
else
  skip "no non-root sudo user in the docker group - nothing to revert"
fi

# ---------------------------------------------------------------- 4. Docker Engine
say "4/7 Docker Engine"
mapfile -t DOCKER_NEW < <(new_packages_from_history "docker-ce docker-ce-cli containerd.io")
if (( ${#DOCKER_NEW[@]} )); then
  info "The original script INSTALLED Docker. Newly installed packages:"
  info "  ${DOCKER_NEW[*]}"
  others=0
  if command -v docker >/dev/null 2>&1; then
    if ! names=$(docker ps -a --format '{{.Names}}' 2>/dev/null); then
      others=-1      # daemon not reachable: cannot prove that nobody else uses Docker
    else
      others=$(printf '%s\n' "$names" | grep -v '^$' | grep -vcx 'eve-war-bot' || true)
    fi
  fi
  if (( others < 0 )); then
    skip "Docker daemon is not reachable, so other containers can't be ruled out - NOT removing Docker."
    info "Start it (sudo systemctl start docker) and run this script again if you want to remove it."
  elif (( others > 0 )); then
    info "But there are $others other container(s) on this server:"
    docker ps -a --format '     {{.Names}}  ({{.Image}}, {{.Status}})' | grep -v ' eve-war-bot ' || true
    skip "Docker is in use by other apps - NOT removing it."
  else
    if ask "Uninstall Docker (packages only; container data in /var/lib/docker stays)?"; then
      systemctl stop docker.socket docker 2>/dev/null || true
      env DEBIAN_FRONTEND=noninteractive apt-get -y -o DPkg::Lock::Timeout=600 purge "${DOCKER_NEW[@]}" \
        && rm -f "$DOCKER_LIST" "$DOCKER_KEY" \
        && env DEBIAN_FRONTEND=noninteractive apt-get -y -o DPkg::Lock::Timeout=600 update >/dev/null \
        && done_ "Docker removed, apt source removed"
      if [[ -d /var/lib/docker ]] && ask "Also delete Docker data (/var/lib/docker, /var/lib/containerd)?"; then
        rm -rf /var/lib/docker /var/lib/containerd && done_ "Docker data deleted"
      fi
    fi
  fi
else
  skip "apt history shows no Docker installation by the script (Docker was there before, or never installed)"
  if [[ -f $DOCKER_LIST ]]; then
    info "Note: $DOCKER_LIST exists. If Docker came from this source before, keep it."
  fi
fi

# ---------------------------------------------------------------- 5. packages
say "5/7 Tools installed by the script's step 1"
mapfile -t TOOLS_NEW < <(new_packages_from_history "ca-certificates curl git ufw unattended-upgrades nano")
if (( ${#TOOLS_NEW[@]} )); then
  info "Packages that were NEW (not on the server before):"
  info "  ${TOOLS_NEW[*]}"
  if ask "Remove these packages?"; then
    env DEBIAN_FRONTEND=noninteractive apt-get -y -o DPkg::Lock::Timeout=600 remove "${TOOLS_NEW[@]}" \
      && done_ "removed"
  fi
else
  skip "all of them were already installed before - nothing to remove"
fi

# ---------------------------------------------------------------- 6. sysctl
say "6/7 Kernel setting vm.swappiness"
if [[ -f $SYSCTL_FILE ]]; then
  info "$SYSCTL_FILE exists (written by the script). Current value: $(cat /proc/sys/vm/swappiness)"
  if ask "Remove it and restore the previous swappiness?"; then
    rm -f "$SYSCTL_FILE"
    # value configured elsewhere, else the Ubuntu default 60
    prev=$(grep -hsE '^\s*vm\.swappiness\s*=' /etc/sysctl.conf /etc/sysctl.d/*.conf /usr/lib/sysctl.d/*.conf \
           | tail -1 | cut -d= -f2 | tr -d ' ')
    sysctl -w vm.swappiness="${prev:-60}" >/dev/null && done_ "vm.swappiness = ${prev:-60}"
  fi
else
  skip "not present - nothing to revert"
fi

# ---------------------------------------------------------------- 7. swap file
say "7/7 Swap file /swapfile"
if [[ -f /swapfile ]] && grep -q '^/swapfile none swap sw 0 0$' /etc/fstab; then
  info "/swapfile: $(du -h /swapfile | cut -f1), created/changed $(stat -c %y /swapfile | cut -d. -f1)"
  info "The original script creates exactly this (1 GB + this /etc/fstab line)."
  info "If /swapfile existed before the script, KEEP it."
  used_kb=$(awk '$1=="/swapfile"{print $4}' /proc/swaps)
  avail_kb=$(awk '/MemAvailable/{print $2}' /proc/meminfo)
  if [[ -n $used_kb && $used_kb -gt 0 && $avail_kb -lt $((used_kb + 102400)) ]]; then
    skip "swap is in use (${used_kb} kB) and free RAM is too low to switch it off safely - try again later"
  elif ask "Switch off and delete /swapfile, remove its /etc/fstab line?"; then
    swapoff /swapfile 2>/dev/null || true
    cp /etc/fstab /etc/fstab.bak-eve-war-bot
    sed -i '\#^/swapfile none swap sw 0 0$#d' /etc/fstab
    rm -f /swapfile && done_ "swap removed (backup of fstab: /etc/fstab.bak-eve-war-bot)"
  fi
else
  skip "no /swapfile set up the way the script does - nothing to revert"
fi

say "Finished"
info "Not reversible: the 'apt-get upgrade' of all packages (security updates stay installed)."
info "The eve-war-bot folder itself was not touched."
