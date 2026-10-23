"""Client for CCP's EVE Swagger Interface (ESI) - public routes only.

Follows the official ESI documentation (developers.eveonline.com/docs/services/esi/):

* Versioning:  version-less routes (https://esi.evetech.net/wars/) plus the
               `X-Compatibility-Date: YYYY-MM-DD` header.
* User-Agent:  app name/version, contact e-mail and source URL, e.g.
               `eve-war-bot/2.0.0 (you@example.com; +https://github.com/...)`.
* Caching:     a response is reused until its `Expires` time - ESI must not be
               asked earlier. After that, the request carries `If-None-Match`
               with the last `ETag`; a 304 means "unchanged" (cheaper: 1 token).
* Rate limits: floating-window token buckets (`X-Ratelimit-Remaining`,
               `X-Ratelimit-Limit`), 429 + `Retry-After`; the older error limit
               (`X-ESI-Error-Limit-Remain/-Reset`, HTTP 420).

Routes used (no authentication):
    GET  /wars/[?max_war_id=]                 newest war IDs (2000, newest first)
    GET  /wars/{war_id}/                      war details, score, allies, dates
    GET  /wars/{war_id}/killmails/?page=N     [{killmail_id, killmail_hash}]  (X-Pages)
    GET  /killmails/{id}/{hash}/              killmail details
    GET  /alliances/{id}/, /alliances/{id}/corporations/, /corporations/{id}/
    POST /universe/names/                     id -> name (ships, systems, corps...)
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

import requests

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://esi.evetech.net"


class EsiError(Exception):
    pass


class EsiNotFound(EsiError):
    pass


def _expires_ts(r: requests.Response) -> float:
    exp = r.headers.get("Expires")
    if not exp:
        return 0.0
    try:
        dt = parsedate_to_datetime(exp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (TypeError, ValueError):
        return 0.0


class EsiClient:
    def __init__(self, base_url: str, user_agent: str, timeout: int = 20,
                 compatibility_date: str = "", name_cache_get: Callable | None = None,
                 name_cache_put: Callable | None = None, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep):
        self.base = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
        if compatibility_date:
            self.s.headers["X-Compatibility-Date"] = compatibility_date
        self._names: dict[int, tuple[str, str]] = {}
        self._cache_get = name_cache_get
        self._cache_put = name_cache_put
        # HTTP cache: url -> (expires_ts, etag, data, headers)
        self._http: dict[str, tuple[float, str | None, Any, dict]] = {}
        self._clock = clock
        self._sleep = sleep
        self.requests_sent = 0
        self.not_modified = 0

    # ---- transport --------------------------------------------------------
    def _request(self, method: str, path: str, params: dict | None = None,
                 headers: dict | None = None, **kw) -> requests.Response:
        url = f"{self.base}{path}"
        for attempt in range(1, 4):
            try:
                self.requests_sent += 1
                r = self.s.request(method, url, params=params, headers=headers,
                                   timeout=self.timeout, **kw)
            except requests.RequestException as e:
                if attempt == 3:
                    raise EsiError(f"{method} {path}: {e}") from e
                self._sleep(2 ** attempt)
                continue
            self._respect_limits(r)
            if r.status_code == 420:                       # old error limit reached
                self._sleep(float(r.headers.get("X-ESI-Error-Limit-Reset", 60)))
                continue
            if r.status_code == 429:                       # token bucket empty
                self._sleep(float(r.headers.get("Retry-After", 5)))
                continue
            if r.status_code >= 500 and attempt < 3:
                self._sleep(2 ** attempt)
                continue
            if r.status_code == 304:
                return r
            if r.status_code == 404:
                raise EsiNotFound(f"{method} {path}: HTTP 404")
            if not r.ok:
                raise EsiError(f"{method} {path}: HTTP {r.status_code} {r.text[:200]}")
            return r
        raise EsiError(f"{method} {path}: retries exhausted")

    def _respect_limits(self, r: requests.Response) -> None:
        # older error limit
        remain = r.headers.get("X-ESI-Error-Limit-Remain")
        if remain is not None and remain.isdigit() and int(remain) < 10:
            reset = float(r.headers.get("X-ESI-Error-Limit-Reset", 60))
            log.warning("ESI error budget low (%s), pausing %.0fs", remain, reset)
            self._sleep(reset)
        # token bucket: slow down when fewer than 10 % of the tokens are left
        rem, lim = r.headers.get("X-Ratelimit-Remaining"), r.headers.get("X-Ratelimit-Limit")
        if rem and lim and rem.isdigit():
            try:
                tokens = int(lim.split("/")[0])
            except ValueError:
                return
            if tokens and int(rem) < tokens * 0.1:
                log.warning("ESI rate limit group %s nearly used up (%s/%s), slowing down",
                            r.headers.get("X-Ratelimit-Group", "?"), rem, lim)
                self._sleep(5)

    def _get(self, path: str, **params) -> Any:
        """GET with Expires/ETag caching, as required by the ESI best practices."""
        key = path + ("?" + "&".join(f"{k}={v}" for k, v in sorted(params.items())) if params else "")
        cached = self._http.get(key)
        now = self._clock()
        if cached and now < cached[0]:
            return cached[2]                               # still fresh: don't ask ESI
        headers = {"If-None-Match": cached[1]} if cached and cached[1] else None
        r = self._request("GET", path, params=params or None, headers=headers)
        if r.status_code == 304 and cached:
            self.not_modified += 1
            self._http[key] = (_expires_ts(r) or now + 60, r.headers.get("ETag") or cached[1],
                               cached[2], cached[3])
            return cached[2]
        data = r.json()
        self._http[key] = (_expires_ts(r), r.headers.get("ETag"), data, dict(r.headers))
        if len(self._http) > 5000:                         # keep memory bounded
            for k in sorted(self._http, key=lambda k: self._http[k][0])[:1000]:
                self._http.pop(k, None)
        return data

    def _get_pages(self, path: str, max_pages: int) -> list:
        out: list = []
        page, pages = 1, 1
        while page <= min(pages, max_pages):
            out.extend(self._get(path, page=page))
            hdr = self._http.get(f"{path}?page={page}", (0, None, None, {}))[3]
            pages = int(hdr.get("X-Pages", 1) or 1)
            page += 1
        return out

    # ---- endpoints --------------------------------------------------------
    def war(self, war_id: int) -> dict:
        return self._get(f"/wars/{war_id}/")

    def wars(self, max_war_id: int | None = None) -> list[int]:
        """Up to 2000 war IDs, newest first (all <= max_war_id when given)."""
        return self._get("/wars/", **({"max_war_id": max_war_id} if max_war_id else {}))

    def war_killmails(self, war_id: int, max_pages: int = 1) -> list[dict]:
        return self._get_pages(f"/wars/{war_id}/killmails/", max_pages)

    def killmail(self, killmail_id: int, killmail_hash: str) -> dict:
        return self._get(f"/killmails/{killmail_id}/{killmail_hash}/")

    def alliance(self, alliance_id: int) -> dict:
        return self._get(f"/alliances/{alliance_id}/")

    def alliance_corporations(self, alliance_id: int) -> list[int]:
        return self._get(f"/alliances/{alliance_id}/corporations/")

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


def parse_esi_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
