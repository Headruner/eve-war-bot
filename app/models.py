"""Domain model for a war declaration."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class Party:
    name: str
    type: str                 # "alliance" | "corporation"
    entity_id: int | None     # EVE entity ID (from the logo URL)
    members: int | None
    dotlan_url: str
    logo_url_small: str | None = None   # 32 px logo as shown on DOTLAN


@dataclass
class War:
    war_id: int
    declared_at: datetime | None        # UTC (EVE time)
    aggressor: Party
    defender: Party
    status: str                         # "none" | "open_for_allies" | "mutual"
    report_url: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["declared_at"] = self.declared_at.isoformat() if self.declared_at else None
        return d
