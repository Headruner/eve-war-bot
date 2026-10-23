"""Discord webhook client with rate-limit handling.

API:
  POST  {webhook_url}?wait=true                    create message, returns message object
  PATCH {webhook_url}/messages/{message_id}        edit message (live war report updates)

  Body: JSON (embeds only) or multipart/form-data
        payload_json = <JSON>, files[n] = <png>  (referenced as attachment://<filename>)
"""
from __future__ import annotations

import json
import logging
import time

import requests

log = logging.getLogger(__name__)


class WebhookInvalid(Exception):
    """401/403 - the webhook URL in credentials.json is wrong or was deleted."""


class MessageGone(Exception):
    """404 on edit - the message was deleted in Discord."""


class NotifyError(Exception):
    """Message could not be delivered (after retries)."""


class DiscordNotifier:
    def __init__(self, webhook_url: str, min_interval_s: float = 2.0, timeout: int = 15,
                 retries: int = 3, dry_run: bool = False):
        base, _, query = webhook_url.partition("?")      # keep e.g. ?thread_id=...
        self.url = base.rstrip("/")
        self.query = query
        self.min_interval_s = min_interval_s
        self.timeout = timeout
        self.retries = retries
        self.dry_run = dry_run
        self._last_post = 0.0
        self.session = requests.Session()
        self._dry_counter = 0

    # ---- public -----------------------------------------------------------
    def send(self, payload: dict, files: list[tuple[str, bytes]] | None = None) -> dict:
        """Create a message. Returns Discord's message object ({'id':..., 'attachments':[...]})."""
        if self.dry_run:
            self._dry_counter += 1
            log.info("[DRY RUN] POST %s (+%d file(s))",
                     json.dumps(payload, ensure_ascii=False)[:3000], len(files or []))
            return {"id": f"dry-run-{self._dry_counter}", "attachments": []}
        q = f"&{self.query}" if self.query else ""
        return self._call("POST", f"{self.url}?wait=true{q}", payload, files, creating=True)

    def edit(self, message_id: str, payload: dict, keep_attachment_ids: list[str] | None = None) -> dict:
        """Edit an existing message. Attachments listed in keep_attachment_ids are kept."""
        body = {k: v for k, v in payload.items() if k in ("content", "embeds", "allowed_mentions")}
        if keep_attachment_ids is not None:
            body["attachments"] = [{"id": a} for a in keep_attachment_ids]
        if self.dry_run or str(message_id).startswith("dry-run"):
            log.info("[DRY RUN] PATCH message %s: %s", message_id,
                     json.dumps(body, ensure_ascii=False)[:3000])
            return {"id": message_id}
        q = f"?{self.query}" if self.query else ""
        return self._call("PATCH", f"{self.url}/messages/{message_id}{q}", body, None,
                          creating=False)

    # ---- transport --------------------------------------------------------
    def _pace(self) -> None:
        wait = self.min_interval_s - (time.monotonic() - self._last_post)
        if wait > 0:
            time.sleep(wait)

    def _call(self, method: str, url: str, payload: dict,
              files: list[tuple[str, bytes]] | None, creating: bool) -> dict:
        last_err = "unknown"
        for attempt in range(1, self.retries + 1):
            self._pace()
            try:
                if files:
                    multipart = {f"files[{i}]": (name, data, "image/png")
                                 for i, (name, data) in enumerate(files)}
                    body = {**payload, "attachments": [
                        {"id": i, "filename": name} for i, (name, _) in enumerate(files)]}
                    r = self.session.request(method, url, data={"payload_json": json.dumps(body)},
                                             files=multipart, timeout=self.timeout)
                else:
                    r = self.session.request(method, url, json=payload, timeout=self.timeout)
            except requests.RequestException as e:
                last_err = f"network: {e}"
                log.warning("Discord %s attempt %d failed: %s", method, attempt, last_err)
                time.sleep(2 ** attempt)
                continue
            finally:
                self._last_post = time.monotonic()

            if r.status_code == 429:
                retry_after = _retry_after(r)
                log.warning("Discord rate limit hit, sleeping %.1fs", retry_after)
                time.sleep(retry_after)
                continue
            if r.status_code in (401, 403) or (r.status_code == 404 and creating):
                raise WebhookInvalid(f"HTTP {r.status_code}: {r.text[:200]}")
            if r.status_code == 404:
                raise MessageGone(r.text[:200])
            if 200 <= r.status_code < 300:
                _respect_bucket(r)
                try:
                    return r.json()
                except ValueError:
                    return {}
            if 500 <= r.status_code < 600:
                last_err = f"HTTP {r.status_code}"
                time.sleep(2 ** attempt)
                continue
            # other 4xx: payload problem - retrying the same payload will not help
            raise NotifyError(f"HTTP {r.status_code}: {r.text[:500]}")
        raise NotifyError(last_err)


def _retry_after(r: requests.Response) -> float:
    try:
        return float(r.json().get("retry_after", 1.0)) + 0.25
    except ValueError:
        return float(r.headers.get("Retry-After", 1.0)) + 0.25


def _respect_bucket(r: requests.Response) -> None:
    """If the bucket is exhausted, wait until it resets (X-RateLimit-* headers)."""
    if r.headers.get("X-RateLimit-Remaining") == "0":
        reset = float(r.headers.get("X-RateLimit-Reset-After", "1"))
        log.debug("Rate-limit bucket empty, waiting %.2fs", reset)
        time.sleep(reset)
