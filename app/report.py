"""Builds a war report (score, timeline, allies, kills) from ESI.

The result is a plain JSON-serialisable dict, stored in SQLite (wars.report_json)
and rendered into the Discord embed by embeds.py.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone

from .esi import EsiClient, EsiError

log = logging.getLogger(__name__)

ZKILL_KILL = "https://zkillboard.com/kill/{id}/"
ZKILL_WAR = "https://zkillboard.com/war/{id}/"


def _side_id(side: dict) -> tuple[int | None, str]:
    if side.get("alliance_id"):
        return side["alliance_id"], "alliance"
    return side.get("corporation_id"), "corporation"


def _ticker(esi: EsiClient, eid: int | None, kind: str) -> str | None:
    if not eid:
        return None
    try:
        data = esi.alliance(eid) if kind == "alliance" else esi.corporation(eid)
        return data.get("ticker")
    except EsiError as e:
        log.debug("ticker lookup failed for %s: %s", eid, e)
        return None


def build_report(esi: EsiClient, war_id: int, recent_kills: int = 5,
                 kill_details_limit: int = 25, max_killmail_pages: int = 1) -> dict:
    war = esi.war(war_id)

    a_id, a_type = _side_id(war.get("aggressor", {}))
    d_id, d_type = _side_id(war.get("defender", {}))
    allies = [_side_id(x) for x in war.get("allies", [])]

    # killmail references (newest first) + details for the newest N
    refs = esi.war_killmails(war_id, max_killmail_pages) if _started(war) else []
    refs.sort(key=lambda r: r["killmail_id"], reverse=True)
    details = []
    for ref in refs[:kill_details_limit]:
        try:
            km = esi.killmail(ref["killmail_id"], ref["killmail_hash"])
            km["killmail_hash"] = ref["killmail_hash"]
            details.append(km)
        except EsiError as e:
            log.debug("killmail %s failed: %s", ref["killmail_id"], e)

    # resolve every ID we will show in one /universe/names call
    ids = {a_id, d_id, *(i for i, _ in allies)}
    for km in details:
        v = km.get("victim", {})
        ids |= {v.get("ship_type_id"), v.get("character_id"), v.get("corporation_id"),
                km.get("solar_system_id")}
    names = esi.names(ids)
    nm = lambda i: names.get(i, (str(i) if i else "?", ""))[0]   # noqa: E731

    kills = []
    for km in details[:recent_kills]:
        v = km.get("victim", {})
        victim_side = "aggressor" if a_id in (v.get("alliance_id"), v.get("corporation_id")) \
            else "defender"
        kills.append({
            "id": km["killmail_id"],
            "time": km.get("killmail_time"),
            "ship": nm(v.get("ship_type_id")),
            "victim": nm(v.get("character_id")) if v.get("character_id") else None,
            "victim_corp": nm(v.get("corporation_id")),
            "system": nm(km.get("solar_system_id")),
            "loss_of": victim_side,
            "zkill_url": ZKILL_KILL.format(id=km["killmail_id"]),
        })
    systems = Counter(nm(km.get("solar_system_id")) for km in details).most_common(3)

    def side(eid, kind, raw):
        return {"id": eid, "type": kind, "name": nm(eid), "ticker": _ticker(esi, eid, kind),
                "ships_killed": int(raw.get("ships_killed", 0)),
                "isk_destroyed": float(raw.get("isk_destroyed", 0.0))}

    return {
        "war_id": war_id,
        "declared": war.get("declared"),
        "started": war.get("started"),
        "finished": war.get("finished"),
        "retracted": war.get("retracted"),
        "mutual": bool(war.get("mutual")),
        "open_for_allies": bool(war.get("open_for_allies")),
        "aggressor": side(a_id, a_type, war.get("aggressor", {})),
        "defender": side(d_id, d_type, war.get("defender", {})),
        "allies": [{"id": i, "type": k, "name": nm(i)} for i, k in allies],
        "kills_total": len(refs),
        "kills_total_capped": len(refs) >= 2000 * max_killmail_pages,
        "recent_kills": kills,
        "top_systems": systems,
        "zkill_war_url": ZKILL_WAR.format(id=war_id),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _started(war: dict) -> bool:
    s = war.get("started")
    if not s:
        return False
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    except ValueError:
        return True


def is_over(report: dict | None) -> bool:
    if not report:
        return False
    for key in ("finished", "retracted"):
        v = report.get(key)
        if v:
            try:
                if datetime.fromisoformat(v.replace("Z", "+00:00")) <= datetime.now(timezone.utc):
                    return True
            except ValueError:
                return True
    return False
