"""EVE War Bot - entry point.

    python -m app.main                # run forever (Docker default)
    python -m app.main --once         # single polling cycle, then exit
    python -m app.main --check-config # validate config + credentials, then exit
    python -m app.main install        # unpack server files from the image
    python -m app.main stats          # wars declared on the 1st of each month
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
import requests

from .esi import EsiClient, EsiError
from .models import War
from .report import build_report, is_over
from .source import EsiWarSource
from .store import WarStore
from .structures import StructureIndex, summarize

PROJECT_URL = "https://github.com/Headruner/eve-war-bot"

log = logging.getLogger("eve_war_bot")
_stop = threading.Event()


def _matches(w: War, s: Settings) -> bool:
    if w.status not in s.statuses:
        return False
    # unknown size (alliances with many corporations) is never filtered out
    if (s.min_defender_members and w.defender.members is not None
            and w.defender.members < s.min_defender_members):
        return False
    if s.watch_entity_ids:
        ids = {w.aggressor.entity_id, w.defender.entity_id}
        if not ids & set(s.watch_entity_ids):
            return False
    return True


def user_agent(creds: Credentials) -> str:
    """ESI best practice: app/version, contact e-mail, source URL, the HTTP library."""
    parts = "; ".join(p for p in (creds.contact, f"+{PROJECT_URL}") if p)
    return f"eve-war-bot/{__version__} ({parts}) python-requests/{requests.__version__}"


def make_esi(s: Settings, creds: Credentials, store: WarStore | None = None) -> EsiClient:
    return EsiClient(s.esi_base_url, user_agent(creds), s.request_timeout_s,
                     s.esi_compatibility_date,
                     store.names_get if store else None, store.names_put if store else None)


def _report(esi: EsiClient | None, s: Settings, war_id: int) -> dict | None:
    if not esi or not s.report_enabled:
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


def _watermark(store: WarStore) -> int | None:
    v = store.get_meta("watermark_war_id")
    return int(v) if v is not None else None


def collect_new_wars(s: Settings, store: WarStore, source: EsiWarSource) -> int:
    """Read the newest war IDs from ESI and store the new wars. Returns how many."""
    ids = source.newest_war_ids()
    if not ids:
        log.warning("ESI returned no war IDs")
        return 0
    wm = _watermark(store)
    if wm is None:
        if store.bootstrapped:
            # database from 1.x (DOTLAN): continue after the newest war it knew
            wm = store.max_war_id() or ids[-1]
            log.info("Upgrade from 1.x: continuing after war %s", wm)
        elif s.bootstrap_silent:
            wm = ids[-1]
            log.info("Bootstrap: newest war ID is %s - wars declared from now on will be "
                     "posted (no old notifications).", wm)
        else:
            wm = 0
        store.set_meta("watermark_war_id", str(wm))
        if not store.bootstrapped:
            store.set_meta("bootstrapped_at", datetime.now(timezone.utc).isoformat())

    candidates = [i for i in ids if i > wm and not store.has(i)]
    todo = candidates[: s.max_new_per_cycle]                       # oldest first
    new, done = 0, 0
    for wid in todo:
        if _stop.is_set():
            break
        try:
            w = source.war(wid)
        except EsiError as e:
            log.warning("Could not read war %s from ESI (%s) - retry next cycle", wid, e)
            break                                                  # keep order, retry later
        if w is None:
            store.add_marker(wid, "skipped")
        else:
            new += store.add_if_new(w, "pending" if _matches(w, s) else "filtered")
        done += 1
    if done:
        store.set_meta("watermark_war_id", str(max(wm, todo[done - 1])))
    rest = len(candidates) - len(todo)
    log.info("ESI: %d war IDs listed, %d new%s.", len(ids), new,
             f", {rest} more next cycle" if rest > 0 else "")
    return new


def make_structures(s: Settings, creds: Credentials, store: WarStore) -> StructureIndex | None:
    if not s.structures_enabled:
        return None
    return StructureIndex(store.db, s.structures_url, user_agent(creds), s.structures_refresh_hours)


def _structures(index: StructureIndex | None, esi: EsiClient, s: Settings, w: War) -> dict | None:
    """Structures of both parties; optional - never blocks a post."""
    if not index:
        return None
    try:
        return {k: summarize(index, esi, p, s.structures_max_listed)
                for k, p in (("aggressor", w.aggressor), ("defender", w.defender))}
    except Exception as e:
        log.warning("Structures for war %s unavailable: %s", w.war_id, e)
        return None


def run_cycle(s: Settings, creds: Credentials, store: WarStore, notifier: DiscordNotifier,
              esi: EsiClient, source: EsiWarSource | None = None,
              structures: StructureIndex | None = None) -> None:
    ua = user_agent(creds)
    source = source or EsiWarSource(esi, s.alliance_member_count_max_corps)

    # 1+2) READ new wars from ESI and STORE them (dedup by war ID) -----------
    collect_new_wars(s, store, source)
    if structures:
        structures.refresh_if_due()                    # daily dataset download

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
            embeds.append(build_embed(w, s, fname, report,
                                      structures=_structures(structures, esi, s, w)))
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
    if s.report_enabled and s.live_updates:
        update_live_reports(s, creds, store, notifier, esi, structures)


def update_live_reports(s: Settings, creds: Credentials, store: WarStore,
                        notifier: DiscordNotifier, esi: EsiClient,
                        structures: StructureIndex | None = None) -> None:
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
            embeds.append(build_embed(w, s, fname, new, over=over,
                                      structures=_structures(structures, esi, s, w)))
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
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["install"]:                      # unpack deployment bundle
        ip = argparse.ArgumentParser(prog="eve-war-bot install")
        ip.add_argument("--target", default="/out", help="folder to write into (mounted)")
        ip.add_argument("--force", action="store_true",
                        help="refresh docker-compose.yml/scripts; never touches your config")
        iargs = ip.parse_args(argv[1:])
        from .installer import install
        return install(iargs.target, iargs.force)

    if argv[:1] == ["stats"]:                        # 1st-of-month war statistics
        sp = argparse.ArgumentParser(prog="eve-war-bot stats")
        sp.add_argument("--months", type=int, default=12, help="how many months back (default 12)")
        sp.add_argument("--json", action="store_true", help="JSON instead of Markdown")
        sargs = sp.parse_args(argv[1:])
        s = load_settings()
        logging.basicConfig(level="WARNING", stream=sys.stderr,
                            format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        try:
            creds = load_credentials(required=False)
        except ConfigError:
            creds = Credentials(webhook_url="")
        from .stats import run as run_stats
        esi = make_esi(s, creds)
        print(run_stats(sargs.months, sargs.json, esi, s.sqlite_path))
        return 0

    ap = argparse.ArgumentParser(prog="eve-war-bot")
    ap.add_argument("--once", action="store_true", help="run a single cycle and exit")
    ap.add_argument("--check-config", action="store_true", help="validate files and exit")
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
    structures = make_structures(s, creds, store)
    log.info("eve-war-bot %s started (source=ESI %s, compatibility date %s, interval %d min, "
             "report=%s, live=%s, dry_run=%s, stored=%s)",
             __version__, s.esi_base_url, s.esi_compatibility_date, s.poll_interval_min,
             s.report_enabled, s.live_updates, s.dry_run, store.stats())
    if not creds.contact:
        log.warning("No contact in credentials.json (esi.contact). ESI asks every app to put "
                    "an e-mail address into its User-Agent.")
    try:
        while not _stop.is_set():
            try:
                run_cycle(s, creds, store, notifier, esi, structures=structures)
                _heartbeat(s.heartbeat_file)
            except WebhookInvalid as e:
                log.critical("Discord webhook rejected (%s). Fix credentials.json.", e)
                return 3
            except EsiError as e:
                log.error("ESI error: %s", e)
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
