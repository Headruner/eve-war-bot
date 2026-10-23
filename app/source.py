"""War source: CCP ESI (replaces the DOTLAN page scraper of 1.x).

How new wars are found
    GET /wars/ returns the newest 2000 war IDs (newest first). War IDs only grow,
    so every ID above the stored "watermark" that is not yet in the database is
    a new war. ESI caches /wars/ (up to 1 h); the client reuses the cached list
    until its `Expires` time, so polling more often costs nothing.

What is read per new war
    GET /wars/{id}/                    declared, mutual, open_for_allies, both sides
    POST /universe/names/              names of both sides
    GET /corporations/{id}/            ticker, member_count            (corporation)
    GET /alliances/{id}/               ticker                          (alliance)
    GET /alliances/{id}/corporations/  number of corporations; members = sum of their
                                       member_count if the alliance has at most
                                       `alliance_member_count_max_corps` corporations
"""
from __future__ import annotations

import logging
from urllib.parse import quote

from .esi import EsiClient, EsiError, EsiNotFound, parse_esi_time
from .models import Party, War

log = logging.getLogger(__name__)

DOTLAN = "https://evemaps.dotlan.net"


def _side(raw: dict) -> tuple[int | None, str]:
    if raw.get("alliance_id"):
        return raw["alliance_id"], "alliance"
    return raw.get("corporation_id"), "corporation"


def dotlan_link(kind: str, name: str) -> str:
    seg = "alliance" if kind == "alliance" else "corp"
    return f"{DOTLAN}/{seg}/{quote(name.replace(' ', '_'), safe='._-')}"


class EsiWarSource:
    def __init__(self, esi: EsiClient, alliance_member_count_max_corps: int = 20):
        self.esi = esi
        self.max_corps = alliance_member_count_max_corps

    # ---- listing ------------------------------------------------------------
    def newest_war_ids(self) -> list[int]:
        ids = self.esi.wars()
        if not isinstance(ids, list):
            raise EsiError(f"unexpected /wars/ response: {str(ids)[:100]}")
        return sorted(int(i) for i in ids)

    # ---- details ------------------------------------------------------------
    def _party(self, raw: dict, names: dict) -> Party:
        eid, kind = _side(raw)
        name = names.get(eid, (str(eid), ""))[0] if eid else "?"
        ticker = members = corps = None
        try:
            if kind == "corporation" and eid:
                c = self.esi.corporation(eid)
                ticker, members = c.get("ticker"), c.get("member_count")
                name = c.get("name") or name
            elif eid:
                a = self.esi.alliance(eid)
                ticker, name = a.get("ticker"), a.get("name") or name
                corp_ids = self.esi.alliance_corporations(eid) or []
                corps = len(corp_ids)
                if 0 < corps <= self.max_corps:
                    members = sum(int(self.esi.corporation(c).get("member_count") or 0)
                                  for c in corp_ids)
        except EsiError as e:          # extra details are optional
            log.debug("details for %s %s failed: %s", kind, eid, e)
        return Party(name=name, type=kind, entity_id=eid, members=members,
                     dotlan_url=dotlan_link(kind, name), ticker=ticker, corporations=corps)

    def war(self, war_id: int) -> War | None:
        try:
            d = self.esi.war(war_id)
        except EsiNotFound:
            log.warning("War %s listed by ESI but not found - skipped", war_id)
            return None
        a_id, _ = _side(d.get("aggressor", {}))
        d_id, _ = _side(d.get("defender", {}))
        names = self.esi.names([a_id, d_id])
        status = ("mutual" if d.get("mutual") else
                  "open_for_allies" if d.get("open_for_allies") else "none")
        return War(
            war_id=int(d.get("id", war_id)),
            declared_at=parse_esi_time(d.get("declared")),
            aggressor=self._party(d.get("aggressor", {}), names),
            defender=self._party(d.get("defender", {}), names),
            status=status,
            report_url=f"{DOTLAN}/war/{war_id}",
        )
