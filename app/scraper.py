"""Reads the DOTLAN wars table (https://evemaps.dotlan.net/wars).

DOTLAN has no public JSON API for wars, so the HTML table is parsed.
Each data row contains (in order): declared date/time, aggressor logo cell,
aggressor name cell, defender logo cell, defender name cell, status, report link.
The parser does not rely on column indexes (the header row has stray cells);
it identifies elements by their link/image URL patterns instead.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup

from .models import Party, War

log = logging.getLogger(__name__)

RE_WAR = re.compile(r"/war/(\d+)")
RE_PARTY = re.compile(r"/(alliance|corp)/([^/]+)")
RE_LOGO = re.compile(r"/(Alliance|Corporation)/(\d+)_\d+\.png", re.I)
RE_MEMBERS = re.compile(r"Members:\s*([\d,.\s]+)")
RE_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
RE_TIME = re.compile(r"(\d{2}:\d{2}:\d{2})")


class ScrapeError(Exception):
    pass


def fetch_html(base_url: str, view: str, user_agent: str, timeout: int) -> str:
    url = f"{base_url}/wars" + (f"/{view}" if view else "")
    r = requests.get(url, headers={"User-Agent": user_agent, "Accept": "text/html"},
                     timeout=timeout)
    r.raise_for_status()
    return r.text


def _status(text: str) -> str:
    if re.search(r"\bMutual\b", text):
        return "mutual"
    if re.search(r"Open\s+For\s+Allies", text, re.I):
        return "open_for_allies"
    return "none"


def _declared(text: str) -> datetime | None:
    d, t = RE_DATE.search(text), RE_TIME.search(text)
    if not d:
        return None
    return datetime.fromisoformat(f"{d.group(1)}T{t.group(1) if t else '00:00:00'}") \
        .replace(tzinfo=timezone.utc)


def _members(cell) -> int | None:
    m = RE_MEMBERS.search(cell.get_text(" ", strip=True))
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(1))
    return int(digits) if digits else None


def parse_wars(html: str, base_url: str = "https://evemaps.dotlan.net") -> list[War]:
    soup = BeautifulSoup(html, "html.parser")
    wars: list[War] = []
    for tr in soup.find_all("tr"):
        report = tr.find("a", href=RE_WAR)
        if not report:
            continue
        try:
            wars.append(_parse_row(tr, report, base_url))
        except Exception as e:     # one broken row must not kill the whole cycle
            log.warning("Skipping unparsable row (%s): %s", e, tr.get_text(" ", strip=True)[:200])
    if not wars and "<table" in html:
        raise ScrapeError("No war rows found - DOTLAN layout may have changed.")
    return wars


def _parse_row(tr, report, base_url: str) -> War:
    war_id = int(RE_WAR.search(report["href"]).group(1))

    # Party name links, in document order: [aggressor, defender]
    links = [a for a in tr.find_all("a", href=True) if RE_PARTY.search(a["href"])]
    # De-duplicate links pointing to the same entity inside one cell (logo + name links)
    uniq, seen = [], set()
    for a in links:
        key = (id(a.find_parent("td")), RE_PARTY.search(a["href"]).group(2))
        if key not in seen:
            seen.add(key)
            uniq.append(a)
    if len(uniq) < 2:
        raise ValueError("expected 2 party links")
    logos = [img for img in tr.find_all("img", src=True) if RE_LOGO.search(img["src"])]

    parties = []
    for idx, a in enumerate(uniq[:2]):
        href = urljoin(base_url + "/", a["href"])
        kind_raw, slug = RE_PARTY.search(href).groups()
        kind = "alliance" if kind_raw == "alliance" else "corporation"
        name = unquote(slug).replace("_", " ")
        logo = logos[idx] if idx < len(logos) else None
        entity_id, logo_url = None, None
        if logo:
            entity_id = int(RE_LOGO.search(logo["src"]).group(2))
            logo_url = urljoin(base_url + "/", logo["src"])
        cell = a.find_parent("td") or tr
        parties.append(Party(name=name, type=kind, entity_id=entity_id,
                             members=_members(cell), dotlan_url=href,
                             logo_url_small=logo_url))

    row_text = tr.get_text(" ", strip=True)
    return War(
        war_id=war_id,
        declared_at=_declared(row_text),
        aggressor=parties[0],
        defender=parties[1],
        status=_status(row_text),
        report_url=urljoin(base_url + "/", report["href"]),
    )
