"""EVE War Bot - entry point.

    python -m app.main                # run forever (Docker default)
    python -m app.main --once         # single polling cycle, then exit
    python -m app.main --check-config # validate config + credentials, then exit
    python -m app.main --once --html-file tests/fixtures/wars.html   # offline parse
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .config import ConfigError, Credentials, Settings, load_credentials, load_settings
from .discord_notifier import DiscordNotifier, MessageGone, NotifyError, WebhookInvalid
from .embeds import build_embed, build_payload
from .esi import EsiClient
from .models import War
from .report import build_report, is_over
from .scraper import ScrapeError, fetch_html, parse_wars
from .store import WarStore

log = logging.getLogger("eve_war_bot")
_stop = threading.Event()


def _matches(w: War, s: Settings) -> bool:
    if w.status not in s.statuses:
        return False
    if s.min_defender_members and (w.defender.members or 0) < s.min_defender_members:
        return False
    if s.watch_entity_ids:
        ids = {w.aggressor.entity_id, w.defender.entity_id}
        if not ids & set(s.watch_entity_ids):
            return False
    return True


def user_agent(creds: Credentials) -> str:
    return f"eve-war-bot/{__version__} (+{creds.contact or 'no-contact-configured'})"


def make_esi(s: Settings, creds: Credentials, store: WarStore) -> EsiClient | None:
    if not s.report_enabled:
        return None
    return EsiClient(s.esi_base_url, user_agent(creds), s.request_timeout_s,
                     s.esi_compatibility_date, store.names_get, store.names_put)


def _report(esi: EsiClient | None, s: Settings, war_id: int) -> dict | None:
    if not esi:
        return None
    try:
        return build_report(esi, war_id, s.report_recent_kills, s.report_kill_details_limit,
                            s.report_max_killmail_pages)
    except Exception as e:                       # report is optional - never block a post
        log.warning("War report for %s unavailable: %s", war_id, e)
        return None


def _fingerprint(r: dict | None) -> tuple:
    """Parts of a report that, when changed, justify editing the Discord message."""
    if not r:
        return ()
    return (r["aggressor"]["ships_killed"], r["aggressor"]["isk_destroyed"],
            r["defender"]["ships_killed"], r["defender"]["isk_destroyed"],
            len(r.get("allies", [])), r.get("kills_total"), r.get("finished"),
            r.get("retracted"), r.get("mutual"), r.get("open_for_allies"))


def run_cycle(s: Settings, creds: Credentials, store: WarStore, notifier: DiscordNotifier,
              html_file: str | None = None, esi: EsiClient | None = None) -> None:
    ua = user_agent(creds)

    # 1) READ ----------------------------------------------------------------
    html = (Path(html_file).read_text(encoding="utf-8") if html_file
            else fetch_html(s.dotlan_base_url, s.dotlan_view, ua, s.request_timeout_s))
    wars = parse_wars(html, s.dotlan_base_url)

    # 2) STORE (dedup) -------------------------------------------------------
    silent = s.bootstrap_silent and not store.bootstrapped
    new = 0
    for w in sorted(wars, key=lambda x: (x.declared_at or datetime.min.replace(tzinfo=timezone.utc), x.war_id)):
        state = "skipped" if silent else ("pending" if _matches(w, s) else "filtered")
        new += store.add_if_new(w, state)
    if not store.bootstrapped:
        store.set_meta("bootstrapped_at", datetime.now(timezone.utc).isoformat())
        if silent:
            log.info("Bootstrap: stored %d existing wars silently (no notifications).", len(wars))
    log.info("Parsed %d wars, %d new.", len(wars), new)

    # 3) NOTIFY --------------------------------------------------------------
    pending = store.pending()
    for i in range(0, len(pending), s.batch_embeds):
        if _stop.is_set():
            break
        batch = pending[i:i + s.batch_embeds]
        embeds, files = [], []
        for w in batch:
            fname = _banner(w, s, ua, files)
            report = _report(esi, s, w.war_id)
            store.save_report(w.war_id, report)
            embeds.append(build_embed(w, s, fname, report))
        payload = build_payload(embeds, s, creds.mention_role_id)
        ids = [w.war_id for w in batch]
        try:
            msg = notifier.send(payload, files or None)
            store.mark_sent(ids, msg.get("id"), [a["id"] for a in msg.get("attachments", [])])
            log.info("Notified war(s) %s -> message %s", ids, msg.get("id"))
        except WebhookInvalid:
            raise
        except NotifyError as e:
            store.mark_failed_attempt(ids, str(e), s.max_attempts)
            log.error("Notify failed for %s: %s", ids, e)

    # 4) LIVE UPDATES of already posted messages ----------------------------
    if esi and s.live_updates:
        update_live_reports(s, creds, store, notifier, esi)


def update_live_reports(s: Settings, creds: Credentials, store: WarStore,
                        notifier: DiscordNotifier, esi: EsiClient) -> None:
    store.expire_live(s.track_days)
    for mid, item in store.live_due(s.update_interval_min, s.track_days).items():
        if _stop.is_set():
            break
        wars: list[War] = item["wars"]
        changed, embeds, finished = False, [], []
        for w in wars:
            old = store.get_report(w.war_id)
            new = _report(esi, s, w.war_id) or old
            if _fingerprint(new) != _fingerprint(old):
                changed = True
            store.save_report(w.war_id, new)
            over = is_over(new)
            if over:
                finished.append(w.war_id)
            fname = f"war_{w.war_id}.png" if item["attachments"] else None
            embeds.append(build_embed(w, s, fname, new, over=over))
        if not changed:
            log.debug("Message %s: report unchanged", mid)
        else:
            payload = build_payload(embeds, s, creds.mention_role_id)
            try:
                notifier.edit(mid, payload, item["attachments"] or None)
                log.info("Updated war report in message %s (wars %s)", mid,
                         [w.war_id for w in wars])
            except MessageGone:
                log.info("Message %s was deleted in Discord - stop updating", mid)
                store.mark_live_done([w.war_id for w in wars])
                continue
            except NotifyError as e:
                log.warning("Update of message %s failed: %s", mid, e)
                continue
        if finished and len(finished) == len(wars):
            store.mark_live_done(finished)
            log.info("War(s) %s ended - final report kept in message %s", finished, mid)


def _banner(w: War, s: Settings, ua: str, files: list) -> str | None:
    if not s.banner_enabled:
        return None
    try:
        from .banner import render_banner
        png = render_banner(w, s, ua)
        if png:
            fname = f"war_{w.war_id}.png"
            files.append((fname, png))
            return fname
    except Exception as e:
        log.warning("Banner for war %s failed: %s", w.war_id, e)
    return None


def _heartbeat(path: str) -> None:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(str(int(time.time())))
    except OSError as e:
        log.debug("heartbeat write failed: %s", e)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eve-war-bot")
    ap.add_argument("--once", action="store_true", help="run a single cycle and exit")
    ap.add_argument("--check-config", action="store_true", help="validate files and exit")
    ap.add_argument("--html-file", help="parse a saved HTML file instead of fetching DOTLAN")
    args = ap.parse_args(argv)

    try:
        s = load_settings()
        logging.basicConfig(level=s.log_level.upper(),
                            format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        creds = load_credentials(required=not s.dry_run)
    except ConfigError as e:
        logging.basicConfig()
        log.critical("Configuration error: %s", e)
        return 2

    if args.check_config:
        log.info("Configuration OK (dry_run=%s, db=%s).", s.dry_run, s.sqlite_path)
        return 0

    signal.signal(signal.SIGTERM, lambda *_: _stop.set())
    signal.signal(signal.SIGINT, lambda *_: _stop.set())

    if s.dry_run:
        # never touch the real notification storage in a test run - otherwise wars
        # "sent" in the dry run would never be posted for real
        s.sqlite_path = "/tmp/wars-dryrun.db" if Path("/tmp").is_dir() else ":memory:"
        log.info("Dry run: using temporary storage %s", s.sqlite_path)
    store = WarStore(s.sqlite_path)
    notifier = DiscordNotifier(creds.webhook_url, s.min_seconds_between_posts,
                               dry_run=s.dry_run)
    esi = make_esi(s, creds, store)
    log.info("eve-war-bot %s started (interval %d min, report=%s, live=%s, dry_run=%s, stored=%s)",
             __version__, s.poll_interval_min, s.report_enabled, s.live_updates, s.dry_run,
             store.stats())
    try:
        while not _stop.is_set():
            try:
                run_cycle(s, creds, store, notifier, args.html_file, esi)
                _heartbeat(s.heartbeat_file)
            except WebhookInvalid as e:
                log.critical("Discord webhook rejected (%s). Fix credentials.json.", e)
                return 3
            except ScrapeError as e:
                log.error("Scrape error: %s", e)
            except Exception as e:                       # keep the service alive
                log.exception("Cycle failed: %s", e)
            if args.once:
                break
            _stop.wait(s.poll_interval_min * 60)
    finally:
        store.close()
        log.info("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
