"""Domain model for a war declaration."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class Party:
    name: str
    type: str                 # "alliance" | "corporation"
    entity_id: int | None     # EVE alliance / corporation ID
    members: int | None       # pilots (None = unknown, e.g. very large alliances)
    dotlan_url: str           # link for readers (not read by the bot)
    logo_url_small: str | None = None   # legacy (1.x, DOTLAN 32 px logo)
    ticker: str | None = None
    corporations: int | None = None     # alliances only: number of member corporations


@dataclass
class War:
    war_id: int
    declared_at: datetime | None        # UTC (EVE time)
    aggressor: Party
    defender: Party
    status: str                         # "none" | "open_for_allies" | "mutual"
    report_url: str                     # DOTLAN war report (link for readers)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["declared_at"] = self.declared_at.isoformat() if self.declared_at else None
        return d
