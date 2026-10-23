"""Persistent notification storage (SQLite) - guarantees no duplicates across restarts.

The database file lives on a Docker volume (/data/wars.db), so state survives
container restarts, re-creation and image upgrades.

States of a war record:
    pending   - seen, must be posted to Discord
    sent      - posted successfully (Discord returned 2xx)  -> never posted again
    skipped   - seen during the silent bootstrap run          -> never posted
    filtered  - did not match the configured filters           -> never posted
    failed    - gave up after max_attempts                     -> never posted

For 'sent' wars the Discord message ID is kept, so the war report inside the
message can be refreshed later (PATCH) instead of posting a new message.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Party, War

SCHEMA = """
CREATE TABLE IF NOT EXISTS wars (
    war_id              INTEGER PRIMARY KEY,
    declared_at         TEXT,
    payload             TEXT    NOT NULL,          -- War as JSON (to resend after restart)
    state               TEXT    NOT NULL,
    attempts            INTEGER NOT NULL DEFAULT 0,
    last_error          TEXT,
    first_seen_at       TEXT    NOT NULL,
    notified_at         TEXT,
    discord_message_id  TEXT
);
CREATE INDEX IF NOT EXISTS ix_wars_state ON wars(state, declared_at);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS names (               -- ESI id -> name cache
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    category   TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# columns added in v1.1 (war report); added to existing databases automatically
MIGRATIONS = {
    "report_json": "TEXT",              # last war report from ESI
    "report_updated_at": "TEXT",
    "attachments_json": "TEXT",         # Discord attachment ids of the message (banner)
    "live_done": "INTEGER NOT NULL DEFAULT 0",   # 1 = no more message updates
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def war_from_dict(d: dict) -> War:
    return War(
        war_id=d["war_id"],
        declared_at=datetime.fromisoformat(d["declared_at"]) if d.get("declared_at") else None,
        aggressor=Party(**d["aggressor"]),
        defender=Party(**d["defender"]),
        status=d["status"],
        report_url=d["report_url"],
    )


class WarStore:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, isolation_level=None)   # autocommit
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(SCHEMA)
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(wars)")}
        for col, ddl in MIGRATIONS.items():
            if col not in cols:
                self.db.execute(f"ALTER TABLE wars ADD COLUMN {col} {ddl}")

    # ---- meta -------------------------------------------------------------
    def get_meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    @property
    def bootstrapped(self) -> bool:
        return self.get_meta("bootstrapped_at") is not None

    # ---- wars -------------------------------------------------------------
    def add_if_new(self, war: War, state: str) -> bool:
        """Insert a war the first time it is seen. Existing records are never touched,
        which is what makes re-scraping the same page idempotent."""
        cur = self.db.execute(
            "INSERT OR IGNORE INTO wars(war_id, declared_at, payload, state, first_seen_at) "
            "VALUES (?,?,?,?,?)",
            (war.war_id, war.declared_at.isoformat() if war.declared_at else None,
             json.dumps(war.to_dict()), state, _now()))
        return cur.rowcount == 1

    def has(self, war_id: int) -> bool:
        return self.db.execute("SELECT 1 FROM wars WHERE war_id=?", (war_id,)).fetchone() is not None

    def max_war_id(self) -> int | None:
        return self.db.execute("SELECT MAX(war_id) FROM wars").fetchone()[0]

    def add_marker(self, war_id: int, state: str = "skipped") -> None:
        """Remember an ID that has no usable data (e.g. 404), so it is not retried."""
        self.db.execute(
            "INSERT OR IGNORE INTO wars(war_id, payload, state, first_seen_at) VALUES (?,?,?,?)",
            (war_id, "{}", state, _now()))

    def pending(self, limit: int = 100) -> list[War]:
        rows = self.db.execute(
            "SELECT payload FROM wars WHERE state='pending' "
            "ORDER BY declared_at IS NULL, declared_at, war_id LIMIT ?", (limit,)).fetchall()
        return [war_from_dict(json.loads(r[0])) for r in rows]

    def mark_sent(self, war_ids: list[int], message_id: str | None,
                  attachment_ids: list[str] | None = None) -> None:
        att = json.dumps(attachment_ids or [])
        self.db.executemany(
            "UPDATE wars SET state='sent', notified_at=?, discord_message_id=?, "
            "attachments_json=?, attempts=attempts+1, last_error=NULL WHERE war_id=?",
            [(_now(), message_id, att, wid) for wid in war_ids])

    def mark_failed_attempt(self, war_ids: list[int], error: str, max_attempts: int) -> None:
        self.db.executemany(
            "UPDATE wars SET attempts=attempts+1, last_error=?, "
            "state=CASE WHEN attempts+1>=? THEN 'failed' ELSE state END WHERE war_id=?",
            [(error[:500], max_attempts, wid) for wid in war_ids])

    # ---- war report / live updates ----------------------------------------
    def save_report(self, war_id: int, report: dict | None) -> None:
        self.db.execute("UPDATE wars SET report_json=?, report_updated_at=? WHERE war_id=?",
                        (json.dumps(report) if report else None, _now(), war_id))

    def get_report(self, war_id: int) -> dict | None:
        row = self.db.execute("SELECT report_json FROM wars WHERE war_id=?", (war_id,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def live_due(self, interval_min: int, track_days: int) -> dict[str, dict]:
        """Messages whose war report should be refreshed now, grouped by Discord message:
        {message_id: {"wars": [War...], "attachments": [...]}} (one message may hold
        several wars when batch_embeds > 1)."""
        now = datetime.now(timezone.utc)
        due_before = (now - timedelta(minutes=interval_min)).isoformat(timespec="seconds")
        since = (now - timedelta(days=track_days)).isoformat(timespec="seconds")
        rows = self.db.execute(
            "SELECT discord_message_id FROM wars WHERE state='sent' AND live_done=0 "
            "AND discord_message_id IS NOT NULL AND notified_at >= ? "
            "AND (report_updated_at IS NULL OR report_updated_at <= ?) "
            "GROUP BY discord_message_id", (since, due_before)).fetchall()
        out: dict[str, dict] = {}
        for (mid,) in rows:
            wars = self.db.execute(
                "SELECT payload, attachments_json FROM wars WHERE discord_message_id=? "
                "ORDER BY declared_at IS NULL, declared_at, war_id", (mid,)).fetchall()
            out[mid] = {"wars": [war_from_dict(json.loads(p)) for p, _ in wars],
                        "attachments": json.loads(wars[0][1] or "[]") if wars else []}
        return out

    def expire_live(self, track_days: int) -> None:
        since = (datetime.now(timezone.utc) - timedelta(days=track_days)).isoformat(timespec="seconds")
        self.db.execute("UPDATE wars SET live_done=1 WHERE state='sent' AND live_done=0 "
                        "AND notified_at < ?", (since,))

    def mark_live_done(self, war_ids: list[int]) -> None:
        self.db.executemany("UPDATE wars SET live_done=1 WHERE war_id=?", [(w,) for w in war_ids])

    # ---- ESI name cache ---------------------------------------------------
    def names_get(self, ids: list[int]) -> dict[int, tuple[str, str]]:
        out: dict[int, tuple[str, str]] = {}
        for chunk in (ids[i:i + 500] for i in range(0, len(ids), 500)):
            q = ",".join("?" * len(chunk))
            for i, n, c in self.db.execute(
                    f"SELECT id, name, category FROM names WHERE id IN ({q})", chunk):
                out[i] = (n, c)
        return out

    def names_put(self, names: dict[int, tuple[str, str]]) -> None:
        self.db.executemany(
            "INSERT INTO names(id,name,category,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at",
            [(i, n, c, _now()) for i, (n, c) in names.items()])

    # ---- misc -------------------------------------------------------------
    def stats(self) -> dict[str, int]:
        return dict(self.db.execute("SELECT state, COUNT(*) FROM wars GROUP BY state").fetchall())

    def close(self) -> None:
        self.db.close()
