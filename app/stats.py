"""`stats` command: wars declared on the 1st day of each month (UTC).

Two sources:
  * CCP ESI (history, independent of when the bot started):
        GET /wars/?max_war_id=N   -> war IDs (newest first, 2000 per call)
        GET /wars/{id}/           -> declared date, mutual, aggressor/defender
    War IDs grow with time, so the first war of a day is found by binary search
    over the ID range; the wars of that day are then read one by one.
  * the bot's own database (/data/wars.db): wars it saw / posted on those days.

    docker compose run --rm -T eve-war-bot stats --months 12 > war-stats.md
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .esi import EsiClient, EsiError

log = logging.getLogger(__name__)


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


@dataclass
class DayStats:
    day: date
    declared: int = 0
    mutual: int = 0
    open_for_allies: int = 0
    alliance_aggressor: int = 0
    corp_aggressor: int = 0
    retracted_or_finished: int = 0
    war_ids: list[int] = field(default_factory=list)
    bot_seen: int | None = None
    bot_posted: int | None = None
    error: str | None = None


class WarHistory:
    """Finds and reads wars by declaration time using ESI only."""

    def __init__(self, esi: EsiClient):
        self.esi = esi
        self._cache: dict[int, dict] = {}
        self._max_id: int | None = None

    def war(self, wid: int) -> dict:
        if wid not in self._cache:
            self._cache[wid] = self.esi.war(wid)
        return self._cache[wid]

    def max_id(self) -> int:
        if self._max_id is None:
            ids = self.esi.wars()
            if not ids:
                raise EsiError("ESI returned no wars")
            self._max_id = max(ids)
        return self._max_id

    def _existing_at_or_below(self, wid: int) -> int | None:
        ids = self.esi.wars(max_war_id=wid)
        return max(ids) if ids else None

    def first_id_declared_at_or_after(self, t: datetime) -> int | None:
        """Smallest war ID whose declaration is >= t (None if no such war yet)."""
        hi = self.max_id()
        if _dt(self.war(hi)["declared"]) < t:
            return None
        lo = 1
        while lo < hi:
            mid = (lo + hi) // 2
            real = self._existing_at_or_below(mid)
            if real is None or real < lo:
                lo = mid + 1
                continue
            if _dt(self.war(real)["declared"]) >= t:
                hi = real
            else:
                lo = mid + 1
        return hi

    def wars_between(self, start: datetime, end: datetime) -> list[dict]:
        first = self.first_id_declared_at_or_after(start)
        if first is None:
            return []
        out: list[dict] = []
        window = 200
        cursor = first
        while True:
            ids = sorted(i for i in self.esi.wars(max_war_id=cursor + window) if i >= cursor)
            if not ids:
                break
            for wid in ids:
                w = self.war(wid)
                d = _dt(w["declared"])
                if d >= end:
                    return out
                if d >= start:
                    out.append(w)
            if ids[-1] >= self.max_id():
                break
            cursor = ids[-1] + 1
        return out


def _bot_counts(db_path: str, day: date) -> tuple[int | None, int | None]:
    if not db_path or not Path(db_path).exists():
        return None, None
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        d = day.isoformat()
        seen = con.execute("SELECT COUNT(*) FROM wars WHERE substr(declared_at,1,10)=?", (d,)).fetchone()[0]
        posted = con.execute("SELECT COUNT(*) FROM wars WHERE substr(declared_at,1,10)=? "
                             "AND state='sent'", (d,)).fetchone()[0]
        first = con.execute("SELECT MIN(first_seen_at) FROM wars").fetchone()[0]
    finally:
        con.close()
    if first and day < _dt(first).date():
        return None, None          # bot was not running yet
    return seen, posted


def first_days(months: int, today: date | None = None) -> list[date]:
    today = today or datetime.now(timezone.utc).date()
    y, m = today.year, today.month
    out = []
    for _ in range(months):
        out.append(date(y, m, 1))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return sorted(out)


def collect(esi: EsiClient, months: int, db_path: str | None = None,
            today: date | None = None) -> list[DayStats]:
    hist = WarHistory(esi)
    result = []
    for day in first_days(months, today):
        st = DayStats(day=day)
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        try:
            for w in hist.wars_between(start, start + timedelta(days=1)):
                st.declared += 1
                st.war_ids.append(w.get("id"))
                st.mutual += bool(w.get("mutual"))
                st.open_for_allies += bool(w.get("open_for_allies"))
                if w.get("aggressor", {}).get("alliance_id"):
                    st.alliance_aggressor += 1
                else:
                    st.corp_aggressor += 1
                ended = [w.get(k) for k in ("finished", "retracted") if w.get(k)]
                st.retracted_or_finished += any(_dt(e) <= datetime.now(timezone.utc) for e in ended)
        except EsiError as e:
            st.error = str(e)[:120]
            log.warning("ESI error for %s: %s", day, e)
        st.bot_seen, st.bot_posted = _bot_counts(db_path or "", day)
        result.append(st)
    return result


def render_markdown(rows: list[DayStats], generated_at: datetime | None = None) -> str:
    gen = (generated_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    def n(v):
        return "—" if v is None else str(v)
    lines = [
        "| Month | Wars declared on the 1st (UTC) | Mutual | Open for allies | "
        "Aggressor alliance / corp | Ended since | Seen by bot | Posted by bot |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        if r.error:
            lines.append(f"| {r.day:%Y-%m} | ESI error: {r.error} | | | | | {n(r.bot_seen)} | {n(r.bot_posted)} |")
            continue
        lines.append(f"| {r.day:%Y-%m} | {r.declared} | {r.mutual} | {r.open_for_allies} | "
                     f"{r.alliance_aggressor} / {r.corp_aggressor} | {r.retracted_or_finished} | "
                     f"{n(r.bot_seen)} | {n(r.bot_posted)} |")
    ok = [r for r in rows if not r.error]
    total = sum(r.declared for r in ok)
    avg = total / len(ok) if ok else 0
    peak = max(ok, key=lambda r: r.declared) if ok else None
    summary = [
        f"*Generated {gen} by `eve-war-bot stats` from CCP ESI and the bot database.*",
        "",
        f"- Months covered: **{len(rows)}** · wars declared on 1st days in total: **{total}** "
        f"· average per 1st day: **{avg:.1f}**"
        + (f" · busiest: **{peak.day:%Y-%m}** ({peak.declared})" if peak else ""),
        "- *Seen/Posted by bot* = wars from that day in the bot's database. "
        "\"—\" means the bot was not running yet.",
        "",
    ]
    return "\n".join(summary + lines) + "\n"


def run(months: int, as_json: bool, esi: EsiClient, db_path: str | None) -> str:
    rows = collect(esi, months, db_path)
    if as_json:
        return json.dumps([{**r.__dict__, "day": r.day.isoformat()} for r in rows], indent=2)
    return render_markdown(rows)
