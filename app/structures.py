"""Structures (Upwell citadels, engineering complexes, refineries ...) owned by each war party.

Data source
    EVE Ref structures dataset (https://docs.everef.net/datasets/structures.html):
    one JSON file, keyed by structure ID, scraped from CCP ESI
    `/universe/structures/{id}/` (+ backfill from Adam4EVE and others). Entries with
    an `owner_id` (= owning corporation) are used. Adam4EVE's own pages are not
    read: its robots.txt disallows automated access to them.

    Only structures that are publicly known (public ESI, docking access of the
    scrapers) can be in such a dataset - private structures are invisible to
    everyone outside the owning corporation.

How it works
    * The file is downloaded at most every `refresh_hours` (default 24) with
      ETag / If-Modified-Since, parsed as a stream (ijson - the file is large, the
      container has 256 MB) and stored in SQLite table `structures`.
    * Corporation war  -> structures owned by that corporation.
      Alliance war     -> structures owned by every member corporation
                          (ESI /alliances/{id}/corporations/).
    * Type and system names come from ESI /universe/names/ (cached).
"""
from __future__ import annotations

import logging
import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone

import requests

from .esi import EsiClient, EsiError
from .models import Party

log = logging.getLogger(__name__)

DEFAULT_URL = "https://data.everef.net/structures/structures-latest.v2.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS structures (
    structure_id    INTEGER PRIMARY KEY,
    owner_id        INTEGER NOT NULL,
    name            TEXT,
    type_id         INTEGER,
    solar_system_id INTEGER
);
CREATE INDEX IF NOT EXISTS ix_structures_owner ON structures(owner_id);
"""


class StructureIndex:
    def __init__(self, db: sqlite3.Connection, url: str = DEFAULT_URL, user_agent: str = "eve-war-bot",
                 refresh_hours: float = 24, timeout: int = 120, clock=time.time):
        self.db = db
        self.url = url
        self.ua = user_agent
        self.refresh_s = refresh_hours * 3600
        self.timeout = timeout
        self.clock = clock
        self.db.executescript(SCHEMA)

    # ---- meta helpers (same meta table as WarStore) ---------------------------
    def _meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    @property
    def loaded(self) -> bool:
        return self._meta("structures_loaded_at") is not None

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM structures").fetchone()[0]

    # ---- download -------------------------------------------------------------
    def refresh_if_due(self) -> bool:
        """Download the dataset when it is older than refresh_hours. Never raises."""
        last = float(self._meta("structures_checked_at") or 0)
        if self.loaded and self.clock() - last < self.refresh_s:
            return False
        try:
            return self.refresh()
        except Exception as e:                          # optional feature - never stop the bot
            log.warning("Structures dataset not updated (%s); %s", e,
                        f"keeping {self.count()} known structures" if self.loaded else "feature inactive")
            self._set_meta("structures_checked_at", str(self.clock() - self.refresh_s + 3600))
            return False

    def refresh(self) -> bool:
        import ijson                                    # streaming JSON parser

        headers = {"User-Agent": self.ua, "Accept-Encoding": "gzip"}
        if self.loaded:
            if (etag := self._meta("structures_etag")):
                headers["If-None-Match"] = etag
            if (lm := self._meta("structures_last_modified")):
                headers["If-Modified-Since"] = lm
        with requests.get(self.url, headers=headers, stream=True, timeout=self.timeout) as r:
            if r.status_code == 304:
                self._set_meta("structures_checked_at", str(self.clock()))
                log.info("Structures dataset unchanged (%d structures).", self.count())
                return False
            r.raise_for_status()
            r.raw.decode_content = True
            self.db.execute("DROP TABLE IF EXISTS structures_new")
            self.db.execute("CREATE TABLE structures_new (structure_id INTEGER PRIMARY KEY, "
                            "owner_id INTEGER NOT NULL, name TEXT, type_id INTEGER, "
                            "solar_system_id INTEGER)")
            batch, n = [], 0
            for sid, s in ijson.kvitems(r.raw, "", use_float=True):
                if not isinstance(s, dict) or not s.get("owner_id"):
                    continue
                batch.append((int(sid), int(s["owner_id"]), s.get("name"),
                              s.get("type_id"), s.get("solar_system_id")))
                if len(batch) >= 5000:
                    self.db.executemany("INSERT OR REPLACE INTO structures_new VALUES (?,?,?,?,?)", batch)
                    n += len(batch)
                    batch = []
            if batch:
                self.db.executemany("INSERT OR REPLACE INTO structures_new VALUES (?,?,?,?,?)", batch)
                n += len(batch)
            if n == 0:
                raise ValueError("dataset contained no structures with an owner")
            self.db.execute("BEGIN")
            self.db.execute("DROP TABLE structures")
            self.db.execute("ALTER TABLE structures_new RENAME TO structures")
            self.db.execute("CREATE INDEX IF NOT EXISTS ix_structures_owner ON structures(owner_id)")
            self.db.execute("COMMIT")
            now = self.clock()
            self._set_meta("structures_loaded_at",
                           datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds"))
            self._set_meta("structures_checked_at", str(now))
            self._set_meta("structures_etag", r.headers.get("ETag") or "")
            self._set_meta("structures_last_modified", r.headers.get("Last-Modified") or "")
            log.info("Structures dataset loaded: %d structures with an owner.", n)
            return True

    # ---- queries --------------------------------------------------------------
    def owned_by(self, corp_ids) -> list[tuple]:
        ids = [int(i) for i in corp_ids if i]
        if not ids:
            return []
        out = []
        for chunk in (ids[i:i + 500] for i in range(0, len(ids), 500)):
            q = ",".join("?" * len(chunk))
            out += self.db.execute(
                f"SELECT structure_id, owner_id, name, type_id, solar_system_id FROM structures "
                f"WHERE owner_id IN ({q}) ORDER BY type_id, name", chunk).fetchall()
        return out


def party_corporations(esi: EsiClient, p: Party) -> list[int]:
    """Corporation -> itself; alliance -> all member corporations (ESI)."""
    if not p.entity_id:
        return []
    if p.type == "corporation":
        return [p.entity_id]
    return list(esi.alliance_corporations(p.entity_id) or [])


def summarize(index: StructureIndex, esi: EsiClient, p: Party, max_listed: int = 5) -> dict | None:
    """Structure summary for one war party, JSON-serialisable (None if unknown)."""
    if not index.loaded:
        return None
    try:
        corps = party_corporations(esi, p)
    except EsiError as e:
        log.debug("corporations of %s unavailable: %s", p.entity_id, e)
        return None
    rows = index.owned_by(corps)
    names = esi.names({r[3] for r in rows} | {r[4] for r in rows} | {r[1] for r in rows}) if rows else {}
    nm = lambda i: names.get(i, (str(i), ""))[0] if i else "?"   # noqa: E731
    by_type = Counter(nm(r[3]) for r in rows)
    by_system = Counter(nm(r[4]) for r in rows)
    listed = [{"name": r[2] or "?", "type": nm(r[3]), "system": nm(r[4]),
               "owner": nm(r[1]) if p.type == "alliance" else None} for r in rows[:max_listed]]
    return {"total": len(rows), "corporations_checked": len(corps),
            "by_type": by_type.most_common(), "top_systems": by_system.most_common(3),
            "listed": listed}
