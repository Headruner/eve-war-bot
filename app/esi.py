"""Client for CCP's official EVE Swagger Interface (ESI) - public endpoints only.

Used to build the war report (the same kind of data DOTLAN shows on /war/{id}).
DOTLAN's /war/{id} pages are disallowed for bots in its robots.txt, so the bot
reads the original data source instead.

Endpoints (no authentication):
    GET  /wars/{war_id}/                      war details, score, allies, dates
    GET  /wars/{war_id}/killmails/?page=N     [{killmail_id, killmail_hash}]  (X-Pages)
    GET  /killmails/{id}/{hash}/              killmail details
    GET  /alliances/{id}/   /corporations/{id}/   ticker, member_count
    POST /universe/names/                     id -> name (ships, systems, corps...)
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

import requests

log = logging.getLogger(__name__)


class EsiError(Exception):
    pass


class EsiClient:
    def __init__(self, base_url: str, user_agent: str, timeout: int = 20,
                 compatibility_date: str = "", name_cache_get: Callable | None = None,
                 name_cache_put: Callable | None = None):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
        if compatibility_date:
            self.s.headers["X-Compatibility-Date"] = compatibility_date
        self._names: dict[int, tuple[str, str]] = {}
        self._cache_get = name_cache_get
        self._cache_put = name_cache_put

    # ---- transport --------------------------------------------------------
    def _request(self, method: str, path: str, **kw) -> requests.Response:
        url = f"{self.base}{path}"
        for attempt in range(1, 4):
            try:
                r = self.s.request(method, url, timeout=self.timeout, **kw)
            except requests.RequestException as e:
                if attempt == 3:
                    raise EsiError(f"{method} {path}: {e}") from e
                time.sleep(2 ** attempt)
                continue
            self._respect_error_limit(r)
            if r.status_code == 420:                       # ESI error-limited
                time.sleep(float(r.headers.get("X-ESI-Error-Limit-Reset", 60)))
                continue
            if r.status_code == 429:
                time.sleep(float(r.headers.get("Retry-After", 5)))
                continue
            if r.status_code >= 500 and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            if not r.ok:
                raise EsiError(f"{method} {path}: HTTP {r.status_code} {r.text[:200]}")
            return r
        raise EsiError(f"{method} {path}: retries exhausted")

    @staticmethod
    def _respect_error_limit(r: requests.Response) -> None:
        remain = r.headers.get("X-ESI-Error-Limit-Remain")
        if remain is not None and int(remain) < 10:
            reset = float(r.headers.get("X-ESI-Error-Limit-Reset", 60))
            log.warning("ESI error budget low (%s), pausing %.0fs", remain, reset)
            time.sleep(reset)

    def _get(self, path: str, **params) -> Any:
        return self._request("GET", path, params=params or None).json()

    # ---- endpoints --------------------------------------------------------
    def war(self, war_id: int) -> dict:
        return self._get(f"/wars/{war_id}/")

    def war_killmails(self, war_id: int, max_pages: int = 1) -> list[dict]:
        out: list[dict] = []
        page, pages = 1, 1
        while page <= min(pages, max_pages):
            r = self._request("GET", f"/wars/{war_id}/killmails/", params={"page": page})
            out.extend(r.json())
            pages = int(r.headers.get("X-Pages", 1))
            page += 1
        return out

    def killmail(self, killmail_id: int, killmail_hash: str) -> dict:
        return self._get(f"/killmails/{killmail_id}/{killmail_hash}/")

    def alliance(self, alliance_id: int) -> dict:
        return self._get(f"/alliances/{alliance_id}/")

    def corporation(self, corporation_id: int) -> dict:
        return self._get(f"/corporations/{corporation_id}/")

    def names(self, ids) -> dict[int, tuple[str, str]]:
        """Resolve IDs to (name, category). Cached in memory and (optionally) in SQLite."""
        ids = {int(i) for i in ids if i}
        missing = [i for i in ids if i not in self._names]
        if missing and self._cache_get:
            self._names.update(self._cache_get(missing))
            missing = [i for i in ids if i not in self._names]
        for chunk in (missing[i:i + 1000] for i in range(0, len(missing), 1000)):
            try:
                rows = self._request("POST", "/universe/names/", json=chunk).json()
            except EsiError as e:
                log.warning("name lookup failed: %s", e)
                continue
            fresh = {row["id"]: (row["name"], row["category"]) for row in rows}
            self._names.update(fresh)
            if self._cache_put:
                self._cache_put(fresh)
        return {i: self._names[i] for i in ids if i in self._names}
