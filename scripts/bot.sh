#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Everyday commands for EVE War Bot. Run from the project folder:
#
#   bash scripts/bot.sh init      create config/credentials.json from the template
#   bash scripts/bot.sh check     validate credentials.json + config.yaml
#   bash scripts/bot.sh test      one dry run (logs the message, posts nothing)
#   bash scripts/bot.sh start     build (or pull) and start in the background
#   bash scripts/bot.sh stop      stop the bot (data is kept)
#   bash scripts/bot.sh restart   restart after changing config files
#   bash scripts/bot.sh logs      follow the log (Ctrl+C to leave)
#   bash scripts/bot.sh status    container state, health, memory/CPU, stored wars
#   bash scripts/bot.sh update    get the newest version (git pull / image pull) + restart
#   bash scripts/bot.sh backup    copy the database to ./backups/
#   bash scripts/bot.sh stats [N] wars declared on the 1st of each month, last N months (default 12)
# -----------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

CREDS=config/credentials.json
DC="docker compose"
# PULL mode: ready-made image from a registry (Nexus, GHCR) instead of building here.
# Active when there is no Dockerfile (installed bundle) or .env names a registry image.
PULL=0
[[ ! -f Dockerfile ]] && PULL=1
[[ -f .env ]] && grep -qE '^EVE_BOT_IMAGE=[^#[:space:]]+/' .env && PULL=1
IMAGE=$(grep -E '^EVE_BOT_IMAGE=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)

need_creds() {
  if [[ ! -f $CREDS ]]; then
    echo "config/credentials.json is missing. Run:  bash scripts/bot.sh init" >&2
    exit 1
  fi
  if [[ -d $CREDS ]]; then
    echo "config/credentials.json is a FOLDER (Docker created it). Remove it with" >&2
    echo "  rmdir config/credentials.json   and run:  bash scripts/bot.sh init" >&2
    exit 1
  fi
}

get_image() {
  if [[ $PULL == 1 ]]; then $DC pull -q; else $DC build -q; fi
}

up() {
  if [[ $PULL == 1 ]]; then $DC pull && $DC up -d; else $DC up -d --build; fi
}

case "${1:-help}" in
  init)
    if [[ -f $CREDS ]]; then
      echo "$CREDS already exists - not overwritten."
    else
      cp config/credentials.example.json "$CREDS"
      chmod 644 "$CREDS"
      echo "Created $CREDS. Now edit it:  nano $CREDS"
    fi
    ;;
  check)
    need_creds
    get_image
    $DC run --rm eve-war-bot --check-config
    ;;
  test)
    need_creds
    get_image
    $DC run --rm -e DRY_RUN=true eve-war-bot --once
    ;;
  start)   need_creds; up; $DC ps ;;
  stop)    $DC stop ;;
  restart) need_creds; $DC up -d --force-recreate; $DC ps ;;
  logs)    $DC logs -f --tail=100 ;;
  status)
    $DC ps
    echo
    docker stats --no-stream eve-war-bot 2>/dev/null || true
    echo
    $DC exec -T eve-war-bot python -c \
      "import sqlite3;c=sqlite3.connect('/data/wars.db');print('Stored wars:',dict(c.execute('select state,count(*) from wars group by state').fetchall()))" \
      2>/dev/null || echo "(bot not running)"
    ;;
  update)
    [[ -d .git ]] && git pull --ff-only
    if [[ $PULL == 1 ]]; then
      $DC pull
      if [[ ! -f Dockerfile && -n $IMAGE ]]; then
        # refresh docker-compose.yml / scripts from the new image (config + secrets are kept)
        docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/out" "$IMAGE" install --force
      fi
      $DC up -d
    else
      up
    fi
    $DC ps
    ;;
  backup)
    mkdir -p backups
    f="backups/wars-$(date +%Y%m%d-%H%M%S).db"
    # consistent copy via SQLite's online backup API (safe while the bot runs)
    $DC exec -T eve-war-bot python -c \
      "import sqlite3;s=sqlite3.connect('/data/wars.db');d=sqlite3.connect('/data/backup.db');s.backup(d);d.close()"
    $DC cp eve-war-bot:/data/backup.db "$f"
    echo "Saved $f"
    ;;
  stats)
    need_creds
    mkdir -p reports
    f="reports/war-stats-$(date +%Y-%m-%d).md"
    echo "Reading war history from CCP ESI (a few minutes for 12 months)..."
    $DC run --rm -T eve-war-bot stats --months "${2:-12}" > "$f"
    cat "$f"
    echo
    echo "Saved $f - paste it into docs/wiki/05-Statistics.md (section 'Data')."
    ;;
  *)
    sed -n '3,16p' "$0"
    ;;
esac
