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
#   bash scripts/bot.sh update    git pull + rebuild + restart
#   bash scripts/bot.sh backup    copy the database to ./backups/
# -----------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

CREDS=config/credentials.json
DC="docker compose"
[[ -f .env ]] && grep -q '^EVE_BOT_IMAGE=ghcr.io' .env && PULL=1 || PULL=0

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
    git pull --ff-only
    up
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
  *)
    sed -n '3,15p' "$0"
    ;;
esac
