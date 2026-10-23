import json
import os
import threading
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from app import main as bot
from app.config import Credentials, Settings
from app.discord_notifier import DiscordNotifier
from app.embeds import build_embed
from app.esi import EsiClient, EsiError, EsiNotFound
from app.report import build_report
from app.source import EsiWarSource
from app.store import WarStore


# =============================================================== fake ESI
def _war(wid, aggressor, defender, declared, mutual=False, open_for_allies=False, **extra):
    return {"id": wid, "declared": declared, "mutual": mutual, "open_for_allies": open_for_allies,
            "aggressor": {**aggressor, "isk_destroyed": 0.0, "ships_killed": 0},
            "defender": {**defender, "isk_destroyed": 0.0, "ships_killed": 0}, **extra}


class FakeEsi(EsiClient):
    """In-memory ESI with the public routes the bot uses."""

    def __init__(self):
        super().__init__("http://esi.invalid", "test", sleep=lambda s: None)
        self.wars_db = {
            763527: _war(763527, {"alliance_id": 99010678}, {"alliance_id": 99003581}, "2026-10-23T14:25:00Z"),
            763533: _war(763533, {"corporation_id": 98794106}, {"corporation_id": 98230524}, "2026-10-23T01:34:00Z"),
            763534: _war(763534, {"corporation_id": 98668032}, {"corporation_id": 98230524}, "2026-10-23T01:34:00Z",
                         open_for_allies=True),
            763448: _war(763448, {"corporation_id": 98000001}, {"alliance_id": 99000002}, "2026-10-12T23:37:00Z",
                         mutual=True),
        }
        self.corps = {98794106: ("Gisabelle Corporation", "GISA", 2),
                      98230524: ("Vanguard Initiative", "VANG", 8),
                      98668032: ("Les Corbeaux de New Eden", "CORB", 17),
                      98000001: ("ZAP 'EM", "ZAP", 1),
                      98000010: ("Ally Corp", "ALLY", 5), 98000099: ("Frat Corp", "FC", 40),
                      98000050: ("Nuke Corp", "NC", 13),
                      **{98100000 + i: (f"Frat member {i}", f"F{i}", 100) for i in range(30)}}
        self.alliances = {99010678: ("NuKeDD.", "NUKE", [98000050]),
                          99003581: ("Fraternity.", "FRAT", [98100000 + i for i in range(30)]),
                          99000002: ("From Hisec with Love Coalition", "LOVE", [98000010, 98000099]),
                          99000020: ("Ally Alliance", "AA", [98000010])}
        self.other_names = {587: "Rifter", 24690: "Hurricane", 9001: "Pilot A", 30000142: "Jita"}
        self.killmails = {}
        self.fail_war = set()
        self.calls = []

    # endpoints
    def wars(self, max_war_id=None):
        self.calls.append(("wars", max_war_id))
        return sorted((i for i in self.wars_db if max_war_id is None or i <= max_war_id), reverse=True)[:2000]

    def war(self, wid):
        self.calls.append(("war", wid))
        if wid in self.fail_war:
            raise EsiError("HTTP 503")
        if wid not in self.wars_db:
            raise EsiNotFound("404")
        return self.wars_db[wid]

    def corporation(self, cid):
        n, t, m = self.corps[cid]
        return {"name": n, "ticker": t, "member_count": m}

    def alliance(self, aid):
        n, t, _ = self.alliances[aid]
        return {"name": n, "ticker": t}

    def alliance_corporations(self, aid):
        return self.alliances[aid][2]

    def names(self, ids):
        out = {}
        for i in ids:
            if i in self.corps:
                out[i] = (self.corps[i][0], "corporation")
            elif i in self.alliances:
                out[i] = (self.alliances[i][0], "alliance")
            elif i in self.other_names:
                out[i] = (self.other_names[i], "x")
        return out

    def war_killmails(self, war_id, max_pages=1):
        return [{"killmail_id": k, "killmail_hash": "h"} for k in self.killmails]

    def killmail(self, kid, h):
        return dict(self.killmails[kid])


# =============================================================== mock Discord
class _Hook(BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Hook.received.append((self.headers.get("Content-Type", ""), body))
        out = json.dumps({"id": str(1000 + len(_Hook.received))}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def do_PATCH(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Hook.received.append(("PATCH", body))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"id": "x"}')

    def log_message(self, *a):
        pass


@pytest.fixture
def hook():
    _Hook.received = []
    srv = HTTPServer(("127.0.0.1", 0), _Hook)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/api/webhooks/1/x"
    srv.shutdown()


def _settings(tmp_path, **kw):
    s = Settings(sqlite_path=str(tmp_path / "wars.db"), banner_enabled=False,
                 min_seconds_between_posts=0, report_enabled=False)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def _cycle(s, store, hook, esi):
    bot.run_cycle(s, Credentials(webhook_url=hook), store, DiscordNotifier(hook, 0), esi)


def _posts():
    return [r for r in _Hook.received if r[0] != "PATCH"]


# =============================================================== source (EP-01)
def test_source_builds_war_from_esi():
    esi = FakeEsi()
    src = EsiWarSource(esi, alliance_member_count_max_corps=20)
    w = src.war(763527)
    assert w.war_id == 763527 and w.status == "none"
    assert w.declared_at == datetime(2026, 10, 23, 14, 25, tzinfo=timezone.utc)
    a, d = w.aggressor, w.defender
    assert (a.name, a.type, a.entity_id, a.ticker) == ("NuKeDD.", "alliance", 99010678, "NUKE")
    assert a.corporations == 1 and a.members == 13              # small alliance: summed
    assert d.corporations == 30 and d.members is None           # > 20 corps: not summed
    assert w.report_url == "https://evemaps.dotlan.net/war/763527"

    c = src.war(763534)
    assert c.status == "open_for_allies"
    assert (c.aggressor.type, c.aggressor.members, c.aggressor.ticker) == ("corporation", 17, "CORB")
    assert c.aggressor.dotlan_url == "https://evemaps.dotlan.net/corp/Les_Corbeaux_de_New_Eden"
    assert src.war(763448).status == "mutual"
    assert src.war(1) is None                                    # 404 -> None


def test_bootstrap_silent_then_only_new_and_no_repost_after_restart(tmp_path, hook):
    s = _settings(tmp_path)
    esi = FakeEsi()
    store = WarStore(s.sqlite_path)
    _cycle(s, store, hook, esi)                                  # first run: nothing posted
    assert _posts() == []
    assert store.get_meta("watermark_war_id") == "763534"
    store.close()

    esi.wars_db[763600] = _war(763600, {"corporation_id": 98000001}, {"alliance_id": 99010678},
                               "2026-10-24T10:00:00Z")
    store = WarStore(s.sqlite_path)                              # "container restart"
    _cycle(s, store, hook, esi)
    assert len(_posts()) == 1
    payload = json.loads(_posts()[0][1])
    e = payload["embeds"][0]
    assert "763600" in e["footer"]["text"] and "ESI" in e["footer"]["text"]
    assert e["thumbnail"]["url"] == "https://images.evetech.net/alliances/99010678/logo?size=128"
    assert "zkillboard.com/war/763600" in e["fields"][-1]["value"]
    store.close()

    store = WarStore(s.sqlite_path)                              # restart again
    _cycle(s, store, hook, esi)
    assert len(_posts()) == 1
    assert store.stats() == {"sent": 1}
    assert ("war", 763527) not in esi.calls                      # old wars never read in detail


def test_non_silent_first_run_posts_all_and_filters(tmp_path, hook):
    s = _settings(tmp_path, bootstrap_silent=False, statuses=["mutual", "none"])
    store = WarStore(s.sqlite_path)
    _cycle(s, store, hook, FakeEsi())
    assert len(_posts()) == 3
    assert store.stats() == {"sent": 3, "filtered": 1}           # open-for-allies filtered


def test_min_defender_members_and_watch_list(tmp_path, hook):
    s = _settings(tmp_path, bootstrap_silent=False, min_defender_members=10,
                  watch_entity_ids=[98230524, 99003581, 99000002])
    store = WarStore(s.sqlite_path)
    _cycle(s, store, hook, FakeEsi())
    # 763527: defender members unknown (big alliance) -> kept; 763533/763534: defender 8 -> filtered;
    # 763448: defender 45 members -> kept
    assert store.stats() == {"sent": 2, "filtered": 2}


def test_catch_up_in_portions(tmp_path, hook):
    s = _settings(tmp_path, bootstrap_silent=False, max_new_per_cycle=3)
    store = WarStore(s.sqlite_path)
    esi = FakeEsi()
    _cycle(s, store, hook, esi)
    assert len(_posts()) == 3
    _cycle(s, store, hook, esi)
    assert len(_posts()) == 4
    ids = [json.loads(b)["embeds"][0]["footer"]["text"] for _, b in _posts()]
    assert "763448" in ids[0]                                    # oldest first


def test_upgrade_from_1x_database_continues_after_known_wars(tmp_path, hook):
    s = _settings(tmp_path)
    store = WarStore(s.sqlite_path)
    src = EsiWarSource(FakeEsi())
    for wid in (763448, 763527):                                 # what DOTLAN 1.x had stored
        store.add_if_new(src.war(wid), "skipped")
    store.set_meta("bootstrapped_at", "2026-10-23T22:10:30+00:00")
    _cycle(s, store, hook, FakeEsi())
    # 763533 and 763534 are newer than 763527 and unknown -> posted; old ones are not
    assert len(_posts()) == 2
    assert store.get_meta("watermark_war_id") == "763534"


def test_esi_error_on_details_retries_next_cycle(tmp_path, hook):
    s = _settings(tmp_path, bootstrap_silent=False)
    esi = FakeEsi()
    esi.fail_war = {763527}
    store = WarStore(s.sqlite_path)
    _cycle(s, store, hook, esi)
    assert len(_posts()) == 1                                    # 763448 before the failing one
    esi.fail_war = set()
    _cycle(s, store, hook, esi)
    assert len(_posts()) == 4


def test_missing_war_is_marked_and_not_retried(tmp_path, hook):
    s = _settings(tmp_path)
    esi = FakeEsi()
    store = WarStore(s.sqlite_path)
    _cycle(s, store, hook, esi)                                  # bootstrap
    orig = esi.wars
    esi.wars = lambda max_war_id=None: [763700] + orig(max_war_id)   # listed, but 404
    _cycle(s, store, hook, esi)
    _cycle(s, store, hook, esi)
    assert esi.calls.count(("war", 763700)) == 1
    assert store.stats() == {"skipped": 1}


def test_banner_multipart(tmp_path, hook, monkeypatch):
    import app.banner as banner
    monkeypatch.setattr(banner, "render_banner", lambda w, s, ua: b"\x89PNG fake")
    s = _settings(tmp_path, bootstrap_silent=False, banner_enabled=True, batch_embeds=10)
    store = WarStore(s.sqlite_path)
    _cycle(s, store, hook, FakeEsi())
    ctype, body = _Hook.received[0]
    assert len(_Hook.received) == 1 and ctype.startswith("multipart/form-data")
    assert b"attachment://war_763448.png" in body and b'name="files[3]"' in body


def test_party_field_shows_members_and_corporations():
    src = EsiWarSource(FakeEsi())
    e = build_embed(src.war(763527), Settings())
    agg, dfn = e["fields"][0]["value"], e["fields"][1]["value"]
    assert "[NUKE]" in agg and "13 members" in agg and "1 corporations" in agg
    assert "30 corporations" in dfn and "members" not in dfn
    assert "zkillboard.com/alliance/99003581/" in e["fields"][-1]["value"]


# =============================================================== war report (EP-04)
KMS = {
    1001: {"killmail_id": 1001, "killmail_time": "2026-10-24T15:00:00Z", "solar_system_id": 30000142,
           "victim": {"ship_type_id": 587, "character_id": 9001, "corporation_id": 98000099,
                      "alliance_id": 99003581}},
    1002: {"killmail_id": 1002, "killmail_time": "2026-10-24T16:00:00Z", "solar_system_id": 30000142,
           "victim": {"ship_type_id": 24690, "corporation_id": 98000050, "alliance_id": 99010678}},
}


def _report_esi(started="2026-01-01T00:00:00Z", **extra):
    esi = FakeEsi()
    w = esi.wars_db[763527]
    w.update(started=started, allies=[{"corporation_id": 98000010}, {"alliance_id": 99000020}], **extra)
    w["aggressor"].update(isk_destroyed=1.5e9, ships_killed=4)
    w["defender"].update(isk_destroyed=2.5e8, ships_killed=1)
    esi.killmails = KMS
    return esi


def test_build_report_and_embed():
    esi = _report_esi()
    r = build_report(esi, 763527)
    assert r["aggressor"]["ticker"] == "NUKE" and r["defender"]["ships_killed"] == 1
    assert [a["name"] for a in r["allies"]] == ["Ally Corp", "Ally Alliance"]
    assert r["kills_total"] == 2 and r["recent_kills"][0]["ship"] == "Hurricane"
    assert r["recent_kills"][0]["loss_of"] == "aggressor"
    assert r["recent_kills"][1]["victim"] == "Pilot A"
    assert r["top_systems"] == [("Jita", 2)]
    e = build_embed(EsiWarSource(esi).war(763527), Settings(), "war_763527.png", r)
    names = [f["name"] for f in e["fields"]]
    assert "🔴 Aggressor score" in names and "🤝 Defender allies (2)" in names
    score = next(f for f in e["fields"] if f["name"] == "🔴 Aggressor score")["value"]
    assert "1.50b" in score and "86%" in score
    assert e["image"]["url"] == "attachment://war_763527.png"


def test_report_before_war_start_has_no_kills():
    r = build_report(_report_esi(started="2099-01-01T00:00:00Z"), 763527)
    assert r["kills_total"] == 0 and r["recent_kills"] == []


def test_live_update_edits_message(tmp_path, hook):
    s = _settings(tmp_path, bootstrap_silent=False, report_enabled=True, update_interval_min=0)
    esi = _report_esi(started="2099-01-01T00:00:00Z")
    for wid in (763533, 763534, 763448):
        esi.wars_db.pop(wid)
    store = WarStore(s.sqlite_path)
    _cycle(s, store, hook, esi)
    assert len(_posts()) == 1
    esi.wars_db[763527]["started"] = "2026-01-01T00:00:00Z"      # war starts, kills appear
    _cycle(s, store, hook, esi)
    patches = [r for r in _Hook.received if r[0] == "PATCH"]
    assert len(patches) == 1 and len(_Hook.received) == 2
    body = json.loads(patches[0][1])
    assert any(f["name"].startswith("💥 Recent kills") for f in body["embeds"][0]["fields"])
    _cycle(s, store, hook, esi)                                  # unchanged -> no edit
    assert len(_Hook.received) == 2
    esi.wars_db[763527]["finished"] = "2026-01-02T00:00:00Z"     # war ends
    _cycle(s, store, hook, esi)
    _cycle(s, store, hook, esi)
    assert len(_Hook.received) == 3 and "ended" in _Hook.received[-1][1].decode()


# =============================================================== ESI client rules (docs)
class _Esi(BaseHTTPRequestHandler):
    log: list = []
    mode = "ok"

    def do_GET(self):
        _Esi.log.append((self.path, dict(self.headers)))
        if _Esi.mode == "429" and len(_Esi.log) == 1:
            self.send_response(429)
            self.send_header("Retry-After", "7")
            self.end_headers()
            return
        if self.headers.get("If-None-Match") == '"v1"':
            self.send_response(304)
            self.send_header("ETag", '"v1"')
            self.end_headers()
            return
        body = json.dumps([3, 2, 1]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("ETag", '"v1"')
        exp = datetime.now(timezone.utc) + timedelta(seconds=3600)
        self.send_header("Expires", format_datetime(exp, usegmt=True))
        self.send_header("X-Ratelimit-Limit", "150/15m")
        self.send_header("X-Ratelimit-Remaining", "149")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def esi_server():
    _Esi.log, _Esi.mode = [], "ok"
    srv = HTTPServer(("127.0.0.1", 0), _Esi)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_esi_headers_and_expires_cache(esi_server):
    now = [1_000_000_000.0]
    c = EsiClient(esi_server, "eve-war-bot/2.0.0 (me@example.com; +https://x)",
                  compatibility_date="2025-08-26", clock=lambda: datetime.now(timezone.utc).timestamp())
    assert c.wars() == [3, 2, 1]
    assert c.wars() == [3, 2, 1]                                  # before Expires: no request
    assert len(_Esi.log) == 1
    path, hdr = _Esi.log[0]
    assert path == "/wars/"                                       # version-less route
    assert hdr["X-Compatibility-Date"] == "2025-08-26"
    assert hdr["User-Agent"].startswith("eve-war-bot/2.0.0 (me@example.com")


def test_esi_etag_304_after_expiry(esi_server):
    t = [0.0]
    c = EsiClient(esi_server, "ua", clock=lambda: t[0])
    t[0] = datetime.now(timezone.utc).timestamp()
    c.wars()
    t[0] += 4000                                                  # cache expired
    assert c.wars() == [3, 2, 1]                                  # 304 -> cached data reused
    assert _Esi.log[1][1].get("If-None-Match") == '"v1"'
    assert c.not_modified == 1


def test_esi_429_waits_retry_after(esi_server):
    _Esi.mode = "429"
    slept = []
    c = EsiClient(esi_server, "ua", sleep=slept.append)
    assert c.wars() == [3, 2, 1]
    assert slept == [7.0] and len(_Esi.log) == 2


def test_user_agent_format():
    ua = bot.user_agent(Credentials(webhook_url="", contact="me@example.com"))
    assert ua.startswith("eve-war-bot/2.0.0 (me@example.com; +https://github.com/Headruner/eve-war-bot)")
    assert "python-requests/" in ua
    assert "(+https://github.com" in bot.user_agent(Credentials(webhook_url=""))


# =============================================================== config / storage
def test_config_new_and_legacy_keys(tmp_path):
    from app.config import load_settings
    old = tmp_path / "old.yaml"
    old.write_text("dotlan: {poll_interval_min: 20, bootstrap_silent: false}\n"
                   "report: {esi_base_url: 'https://esi.evetech.net/latest', esi_compatibility_date: '2025-01-01'}\n")
    s = load_settings(str(old))
    assert (s.poll_interval_min, s.bootstrap_silent) == (20, False)
    assert (s.esi_base_url, s.esi_compatibility_date) == ("https://esi.evetech.net/latest", "2025-01-01")
    new = tmp_path / "new.yaml"
    new.write_text("source: {poll_interval_min: 30, max_new_per_cycle: 7}\n"
                   "esi: {base_url: 'https://esi.evetech.net/', compatibility_date: '2025-08-26'}\n")
    s = load_settings(str(new))
    assert (s.poll_interval_min, s.max_new_per_cycle, s.esi_base_url) == (30, 7, "https://esi.evetech.net")
    assert load_settings(str(tmp_path / "missing.yaml")).esi_base_url == "https://esi.evetech.net"


def test_credentials_bom_and_legacy_contact(tmp_path):
    from app.config import load_credentials
    f = tmp_path / "c.json"
    f.write_bytes(b"\xef\xbb\xbf" + json.dumps(
        {"discord": {"webhook_url": "https://discord.com/api/webhooks/1/x"},
         "dotlan": {"contact": "old@example.com"}}).encode())
    assert load_credentials(str(f)).contact == "old@example.com"
    f.write_text(json.dumps({"discord": {"webhook_url": "https://discord.com/api/webhooks/1/x"},
                             "esi": {"contact": "new@example.com"}}))
    assert load_credentials(str(f)).contact == "new@example.com"


def test_credentials_folder_gives_clear_error(tmp_path):
    from app.config import ConfigError, load_credentials
    d = tmp_path / "credentials.json"
    d.mkdir()
    with pytest.raises(ConfigError, match="is a folder"):
        load_credentials(str(d), required=False)


def test_dry_run_never_touches_real_storage(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    real_db = tmp_path / "real.db"
    cfg.write_text(f"source: {{bootstrap_silent: false}}\nimages: {{banner_enabled: false}}\n"
                   f"report: {{enabled: false}}\nstorage: {{sqlite_path: {real_db}, "
                   f"heartbeat_file: {tmp_path}/hb}}\nruntime: {{dry_run: true}}\n")
    monkeypatch.setenv("CONFIG_FILE", str(cfg))
    monkeypatch.setenv("CREDENTIALS_FILE", str(tmp_path / "missing.json"))
    monkeypatch.setattr(bot, "make_esi", lambda *a, **k: FakeEsi())
    assert bot.main(["--once"]) == 0
    assert not real_db.exists()


# =============================================================== install (EP-06)
def _bundle(tmp_path):
    import shutil
    root = Path(__file__).parent.parent
    b = tmp_path / "bundle"
    (b / "config").mkdir(parents=True)
    (b / "scripts").mkdir()
    for src, dst in [("deploy/docker-compose.yml", "docker-compose.yml"),
                     ("deploy/DEPLOY.md", "DEPLOY.md"),
                     ("config/config.yaml", "config/config.yaml"),
                     ("config/credentials.example.json", "config/credentials.example.json"),
                     ("scripts/bot.sh", "scripts/bot.sh"),
                     ("scripts/setup-droplet.sh", "scripts/setup-droplet.sh")]:
        shutil.copyfile(root / src, b / dst)
    return b


def test_install_unpacks_bundle_and_keeps_user_files(tmp_path, monkeypatch, capsys):
    import importlib
    import app.installer as inst
    monkeypatch.setenv("EVE_BOT_BUNDLE", str(_bundle(tmp_path)))
    monkeypatch.setenv("EVE_BOT_IMAGE_REF", "nexus.example.com:8083/eve-war-bot:latest")
    importlib.reload(inst)
    out = tmp_path / "srv"
    out.mkdir()
    assert bot.main(["install", "--target", str(out)]) == 0
    for f in ["docker-compose.yml", ".env", "DEPLOY.md", "config/config.yaml",
              "config/credentials.json", "scripts/bot.sh"]:
        assert (out / f).is_file(), f
    assert "EVE_BOT_IMAGE=nexus.example.com:8083/eve-war-bot:latest" in (out / ".env").read_text()
    assert json.loads((out / "config/credentials.json").read_text())["esi"]["contact"] == ""
    assert os.access(out / "scripts/bot.sh", os.X_OK)
    (out / "config/credentials.json").write_text('{"discord": {"webhook_url": "https://x"}}')
    (out / "config/config.yaml").write_text("source: {poll_interval_min: 30}\n")
    (out / "docker-compose.yml").write_text("old")
    assert bot.main(["install", "--target", str(out), "--force"]) == 0
    assert "https://x" in (out / "config/credentials.json").read_text()
    assert "30" in (out / "config/config.yaml").read_text()
    assert (out / "docker-compose.yml").read_text() != "old"
    assert "kept     config/credentials.json" in capsys.readouterr().out


def test_install_refuses_unwritable_or_missing_target(tmp_path):
    from app.installer import install
    assert install(str(tmp_path / "nope")) == 2


# =============================================================== stats (EP-07)
class HistoryEsi(EsiClient):
    """Synthetic ESI: war IDs 100..(gaps every 7th id), one war every 5 hours."""
    def __init__(self):
        super().__init__("http://esi.invalid", "test")
        start = datetime(2026, 6, 25, tzinfo=timezone.utc)
        self.data = {}
        wid, t = 100, start
        while t < datetime(2026, 10, 3, tzinfo=timezone.utc):
            if wid % 7:
                self.data[wid] = {"id": wid, "declared": t.isoformat().replace("+00:00", "Z"),
                                  "mutual": wid % 3 == 0,
                                  "aggressor": {"alliance_id": 1} if wid % 2 else {"corporation_id": 2}}
                t += timedelta(hours=5)
            wid += 1
        self.calls = 0

    def wars(self, max_war_id=None):
        self.calls += 1
        ids = sorted((i for i in self.data if max_war_id is None or i <= max_war_id), reverse=True)
        return ids[:2000]

    def war(self, wid):
        self.calls += 1
        return self.data[wid]


def test_stats_counts_wars_on_first_day_of_month():
    from datetime import date
    from app.stats import collect, render_markdown
    esi = HistoryEsi()
    rows = collect(esi, 4, None, today=date(2026, 10, 2))
    assert [r.day.strftime("%Y-%m") for r in rows] == ["2026-07", "2026-08", "2026-09", "2026-10"]
    for r in rows:
        expected = [w for w in esi.data.values() if w["declared"].startswith(r.day.isoformat())]
        assert r.declared == len(expected), r.day
        assert r.mutual == sum(w["mutual"] for w in expected)
        assert r.alliance_aggressor + r.corp_aggressor == r.declared
    assert esi.calls < 400
    md = render_markdown(rows, datetime(2026, 10, 2, tzinfo=timezone.utc))
    assert "| 2026-08 |" in md and "Months covered: **4**" in md


def test_stats_bot_columns_from_database(tmp_path):
    from datetime import date
    from app.stats import _bot_counts
    s = _settings(tmp_path)
    store = WarStore(s.sqlite_path)
    src = EsiWarSource(FakeEsi())
    for wid in (763527, 763533, 763448):
        store.add_if_new(src.war(wid), "pending")
    store.mark_sent([763527], "m1")
    store.db.execute("UPDATE wars SET first_seen_at='2026-10-01T00:00:00+00:00'")
    store.close()
    assert _bot_counts(s.sqlite_path, date(2026, 10, 23)) == (2, 1)
    assert _bot_counts(s.sqlite_path, date(2026, 9, 1)) == (None, None)
