"""Loads settings (config.yaml) and secrets (credentials.json).

Secrets live ONLY in credentials.json; config.yaml holds non-secret behaviour.
File locations can be overridden with the CONFIG_FILE / CREDENTIALS_FILE env vars.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG = "/app/config/config.yaml"
DEFAULT_CREDENTIALS = "/app/config/credentials.json"


class ConfigError(Exception):
    pass


@dataclass
class Credentials:
    webhook_url: str
    mention_role_id: str = ""
    contact: str = ""


@dataclass
class Settings:
    # dotlan
    dotlan_base_url: str = "https://evemaps.dotlan.net"
    dotlan_view: str = ""
    poll_interval_min: int = 15
    request_timeout_s: int = 20
    bootstrap_silent: bool = True
    # discord
    username: str = "EVE War Watch"
    avatar_url: str = ""
    batch_embeds: int = 1
    min_seconds_between_posts: float = 2.0
    max_attempts: int = 5
    # images
    image_server: str = "https://images.evetech.net"
    logo_size: int = 128
    banner_enabled: bool = True
    # war report (ESI) + live message updates
    report_enabled: bool = True
    esi_base_url: str = "https://esi.evetech.net/latest"
    esi_compatibility_date: str = "2025-08-26"
    report_recent_kills: int = 5
    report_kill_details_limit: int = 25
    report_max_killmail_pages: int = 1
    report_max_allies: int = 10
    live_updates: bool = True
    update_interval_min: int = 60
    track_days: int = 7
    # filters
    watch_entity_ids: list[int] = field(default_factory=list)
    statuses: list[str] = field(default_factory=lambda: ["none", "open_for_allies", "mutual"])
    min_defender_members: int = 0
    # storage / runtime
    sqlite_path: str = "/data/wars.db"
    heartbeat_file: str = "/data/heartbeat"
    log_level: str = "INFO"
    dry_run: bool = False


def _get(d: dict, path: str, default):
    cur = d
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return default if cur is None else cur


def load_settings(path: str | None = None) -> Settings:
    path = path or os.getenv("CONFIG_FILE", DEFAULT_CONFIG)
    raw: dict = {}
    if Path(path).exists():
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    s = Settings()
    s.dotlan_base_url = _get(raw, "dotlan.base_url", s.dotlan_base_url).rstrip("/")
    s.dotlan_view = _get(raw, "dotlan.view", s.dotlan_view)
    s.poll_interval_min = int(_get(raw, "dotlan.poll_interval_min", s.poll_interval_min))
    s.request_timeout_s = int(_get(raw, "dotlan.request_timeout_s", s.request_timeout_s))
    s.bootstrap_silent = bool(_get(raw, "dotlan.bootstrap_silent", s.bootstrap_silent))
    s.username = _get(raw, "discord.username", s.username)
    s.avatar_url = _get(raw, "discord.avatar_url", s.avatar_url)
    s.batch_embeds = max(1, min(10, int(_get(raw, "discord.batch_embeds", s.batch_embeds))))
    s.min_seconds_between_posts = float(_get(raw, "discord.min_seconds_between_posts",
                                             s.min_seconds_between_posts))
    s.max_attempts = int(_get(raw, "discord.max_attempts", s.max_attempts))
    s.image_server = _get(raw, "images.image_server", s.image_server).rstrip("/")
    s.logo_size = int(_get(raw, "images.logo_size", s.logo_size))
    s.banner_enabled = bool(_get(raw, "images.banner_enabled", s.banner_enabled))
    s.report_enabled = bool(_get(raw, "report.enabled", s.report_enabled))
    s.esi_base_url = _get(raw, "report.esi_base_url", s.esi_base_url).rstrip("/")
    s.esi_compatibility_date = str(_get(raw, "report.esi_compatibility_date",
                                        s.esi_compatibility_date))
    s.report_recent_kills = int(_get(raw, "report.recent_kills", s.report_recent_kills))
    s.report_kill_details_limit = int(_get(raw, "report.kill_details_limit",
                                           s.report_kill_details_limit))
    s.report_max_killmail_pages = int(_get(raw, "report.max_killmail_pages",
                                           s.report_max_killmail_pages))
    s.report_max_allies = int(_get(raw, "report.max_allies", s.report_max_allies))
    s.live_updates = bool(_get(raw, "report.live_updates", s.live_updates))
    s.update_interval_min = int(_get(raw, "report.update_interval_min", s.update_interval_min))
    s.track_days = int(_get(raw, "report.track_days", s.track_days))
    s.watch_entity_ids = [int(x) for x in _get(raw, "filters.watch_entity_ids", [])]
    s.statuses = list(_get(raw, "filters.statuses", s.statuses))
    s.min_defender_members = int(_get(raw, "filters.min_defender_members", s.min_defender_members))
    s.sqlite_path = _get(raw, "storage.sqlite_path", s.sqlite_path)
    s.heartbeat_file = _get(raw, "storage.heartbeat_file", s.heartbeat_file)
    s.log_level = _get(raw, "runtime.log_level", s.log_level)
    s.dry_run = bool(_get(raw, "runtime.dry_run", s.dry_run))
    if os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes"):
        s.dry_run = True
    return s


def load_credentials(path: str | None = None, required: bool = True) -> Credentials:
    path = path or os.getenv("CREDENTIALS_FILE", DEFAULT_CREDENTIALS)
    p = Path(path)
    if not p.exists():
        if required:
            raise ConfigError(
                f"Credentials file not found: {path}. "
                "Copy config/credentials.example.json to config/credentials.json and fill it in.")
        return Credentials(webhook_url="")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in {path}: {e}") from e

    creds = Credentials(
        webhook_url=str(_get(raw, "discord.webhook_url", "")).strip(),
        mention_role_id=str(_get(raw, "discord.mention_role_id", "")).strip(),
        contact=str(_get(raw, "dotlan.contact", "")).strip(),
    )
    if required:
        if not creds.webhook_url:
            raise ConfigError(f"'discord.webhook_url' is empty in {path}.")
        if not creds.webhook_url.startswith(("https://discord.com/api/webhooks/",
                                             "https://discordapp.com/api/webhooks/",
                                             "http://", "https://")):
            raise ConfigError("'discord.webhook_url' does not look like a URL.")
        if creds.mention_role_id and not creds.mention_role_id.isdigit():
            raise ConfigError("'discord.mention_role_id' must be numeric (role ID) or empty.")
    return creds
