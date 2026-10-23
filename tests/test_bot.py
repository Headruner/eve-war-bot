import os
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from app import main as bot
from app.config import Credentials, Settings
from app.discord_notifier import DiscordNotifier
from app.scraper import parse_wars
from app.store import WarStore

FIX = Path(__file__).parent / "fixtures" / "wars.html"


# ---------- scraper ----------------------------------------------------------
def test_parse_rows():
    wars = parse_wars(FIX.read_text())
    assert [w.war_id for w in wars] == [763527, 763534, 763448, 763495]
    w = wars[0]
    assert w.aggressor.name == "NuKeDD." and w.aggressor.type == "alliance"
    assert w.aggressor.entity_id == 99010678 and w.aggressor.members == 13
    assert w.defender.members == 54418
    assert w.declared_at.isoformat() == "2026-10-23T14:25:00+00:00"
    assert w.report_url == "https://evemaps.dotlan.net/war/763527"


def test_full_names_status_and_date_order():
    wars = {w.war_id: w for w in parse_wars(FIX.read_text())}
    assert wars[763448].defender.name == "From Hisec with Love Coalition"   # not truncated
    assert wars[763448].aggressor.name == "ZAP 'EM"
    assert wars[763448].status == "mutual"
    assert wars[763495].status == "open_for_allies"
    assert wars[763527].status == "none"
    assert wars[763448].declared_at.isoformat() == "2026-10-12T23:37:00+00:00"
    assert wars[763534].aggressor.type == "corporation"


# ---------- end-to-end with mock Discord -------------------------------------
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
                 min_seconds_between_posts=0)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_bootstrap_silent_then_only_new(tmp_path, hook):
    s = _settings(tmp_path)
    creds = Credentials(webhook_url=hook)
    html_all = FIX.read_text()
    # First run: the page has 3 of the 4 wars -> stored silently
    html_3 = html_all.replace('<a href="/war/763527">', '<a href="/xx/763527">')
    f = tmp_path / "p.html"
    f.write_text(html_3)
    store = WarStore(s.sqlite_path)
    bot.run_cycle(s, creds, store, DiscordNotifier(hook, 0), str(f))
    assert _Hook.received == []
    store.close()

    # "Container restart": new store object on the same file, new war appears
    f.write_text(html_all)
    store = WarStore(s.sqlite_path)
    bot.run_cycle(s, creds, store, DiscordNotifier(hook, 0), str(f))
    assert len(_Hook.received) == 1
    payload = json.loads(_Hook.received[0][1])
    assert "763527" in payload["embeds"][0]["url"]
    assert payload["embeds"][0]["thumbnail"]["url"] == \
        "https://images.evetech.net/alliances/99003581/logo?size=128"
    store.close()

    # Restart again: nothing re-sent
    store = WarStore(s.sqlite_path)
    bot.run_cycle(s, creds, store, DiscordNotifier(hook, 0), str(f))
    assert len(_Hook.received) == 1
    assert store.stats() == {"sent": 1, "skipped": 3}


def test_non_silent_sends_all_and_filters(tmp_path, hook):
    s = _settings(tmp_path, bootstrap_silent=False, statuses=["mutual", "none"])
    store = WarStore(s.sqlite_path)
    bot.run_cycle(s, Credentials(webhook_url=hook), store, DiscordNotifier(hook, 0), str(FIX))
    assert len(_Hook.received) == 3
    assert store.stats() == {"sent": 3, "filtered": 1}


def test_banner_multipart(tmp_path, hook, monkeypatch):
    import app.banner as banner
    monkeypatch.setattr(banner, "render_banner", lambda w, s, ua: b"\x89PNG fake")
    s = _settings(tmp_path, bootstrap_silent=False, banner_enabled=True, batch_embeds=10)
    store = WarStore(s.sqlite_path)
    bot.run_cycle(s, Credentials(webhook_url=hook), store, DiscordNotifier(hook, 0), str(FIX))
    ctype, body = _Hook.received[0]
    assert len(_Hook.received) == 1 and ctype.startswith("multipart/form-data")
    assert b"attachment://war_763448.png" in body and b'name="files[3]"' in body


# ---------- war report (ESI) -------------------------------------------------
from app.esi import EsiClient
from app.report import build_report
from app.embeds import build_embed

WAR = {
    "id": 763527, "declared": "2026-10-23T14:25:00Z", "started": "2026-10-24T14:25:00Z",
    "mutual": False, "open_for_allies": False,
    "aggressor": {"alliance_id": 99010678, "isk_destroyed": 1.5e9, "ships_killed": 4},
    "defender": {"alliance_id": 99003581, "isk_destroyed": 2.5e8, "ships_killed": 1},
    "allies": [{"corporation_id": 98000010}, {"alliance_id": 99000020}],
}
KMS = {
    1001: {"killmail_id": 1001, "killmail_time": "2026-10-24T15:00:00Z", "solar_system_id": 30000142,
           "victim": {"ship_type_id": 587, "character_id": 9001, "corporation_id": 98000099,
                      "alliance_id": 99003581}},
    1002: {"killmail_id": 1002, "killmail_time": "2026-10-24T16:00:00Z", "solar_system_id": 30000142,
           "victim": {"ship_type_id": 24690, "corporation_id": 98000050, "alliance_id": 99010678}},
}
NAMES = {99010678: "NuKeDD.", 99003581: "Fraternity.", 98000010: "Ally Corp",
         99000020: "Ally Alliance", 587: "Rifter", 24690: "Hurricane", 9001: "Pilot A",
         98000099: "Frat Corp", 98000050: "Nuke Corp", 30000142: "Jita"}


class FakeEsi(EsiClient):
    def __init__(self, war=None):
        super().__init__("http://esi.invalid", "test")
        self._war = war or WAR

    def war(self, war_id):
        return self._war

    def war_killmails(self, war_id, max_pages=1):
        return [{"killmail_id": k, "killmail_hash": "h"} for k in KMS]

    def killmail(self, kid, h):
        return dict(KMS[kid])

    def alliance(self, i):
        return {"ticker": "NUKE" if i == 99010678 else "FRAT"}

    def corporation(self, i):
        return {"ticker": "CORP"}

    def names(self, ids):
        return {i: (NAMES[i], "x") for i in ids if i in NAMES}


def _started_war():
    w = dict(WAR)
    w["started"] = "2026-01-01T00:00:00Z"   # in the past -> killmails are read
    return w


def test_build_report_and_embed():
    r = build_report(FakeEsi(_started_war()), 763527)
    assert r["aggressor"]["ticker"] == "NUKE" and r["defender"]["ships_killed"] == 1
    assert [a["name"] for a in r["allies"]] == ["Ally Corp", "Ally Alliance"]
    assert r["kills_total"] == 2 and r["recent_kills"][0]["ship"] == "Hurricane"   # newest first
    assert r["recent_kills"][0]["loss_of"] == "aggressor"
    assert r["recent_kills"][1]["victim"] == "Pilot A"
    assert r["top_systems"] == [("Jita", 2)]

    war = parse_wars(FIX.read_text())[0]
    e = build_embed(war, Settings(), "war_763527.png", r)
    names = [f["name"] for f in e["fields"]]
    assert "🔴 Aggressor score" in names and "🤝 Defender allies (2)" in names
    assert any(n.startswith("💥 Recent kills (2 total)") for n in names)
    score = next(f for f in e["fields"] if f["name"] == "🔴 Aggressor score")["value"]
    assert "1.50b" in score and "86%" in score
    assert "zkillboard.com/war/763527" in e["fields"][-1]["value"]
    assert e["image"]["url"] == "attachment://war_763527.png"


def test_report_before_war_start_has_no_kills():
    r = build_report(FakeEsi(), 763527)     # started in the future
    assert r["kills_total"] == 0 and r["recent_kills"] == []


def test_live_update_edits_message(tmp_path, hook):
    import app.main as m
    s = _settings(tmp_path, bootstrap_silent=False, update_interval_min=0)
    store = WarStore(s.sqlite_path)
    creds = Credentials(webhook_url=hook)
    esi = FakeEsi()
    html = FIX.read_text().split('<tr>\n <td><b>01:34:00')[0] + "</table>"   # only war 763527
    f = tmp_path / "one.html"
    f.write_text(html)
    m.run_cycle(s, creds, store, DiscordNotifier(hook, 0), str(f), esi)
    posts = [r for r in _Hook.received if r[0] != "PATCH"]
    assert len(posts) == 1
    # score changes -> next cycle edits the existing message instead of posting a new one
    esi._war = _started_war()
    m.run_cycle(s, creds, store, DiscordNotifier(hook, 0), str(f), esi)
    patches = [r for r in _Hook.received if r[0] == "PATCH"]
    assert len(patches) == 1 and len(_Hook.received) == 2
    body = json.loads(patches[0][1])
    assert any(fl["name"].startswith("💥 Recent kills") for fl in body["embeds"][0]["fields"])
    # unchanged -> no further edit
    m.run_cycle(s, creds, store, DiscordNotifier(hook, 0), str(f), esi)
    assert len(_Hook.received) == 2
    # war finished -> final edit, then tracking stops
    w = _started_war()
    w["finished"] = "2026-01-02T00:00:00Z"
    esi._war = w
    m.run_cycle(s, creds, store, DiscordNotifier(hook, 0), str(f), esi)
    m.run_cycle(s, creds, store, DiscordNotifier(hook, 0), str(f), esi)
    assert len(_Hook.received) == 3
    assert "ended" in _Hook.received[-1][1].decode()


def test_dry_run_never_touches_real_storage(tmp_path, monkeypatch):
    import app.main as m
    cfg = tmp_path / "c.yaml"
    real_db = tmp_path / "real.db"
    cfg.write_text(f"dotlan: {{bootstrap_silent: false}}\nimages: {{banner_enabled: false}}\n"
                   f"report: {{enabled: false}}\nstorage: {{sqlite_path: {real_db}, "
                   f"heartbeat_file: {tmp_path}/hb}}\nruntime: {{dry_run: true}}\n")
    monkeypatch.setenv("CONFIG_FILE", str(cfg))
    monkeypatch.setenv("CREDENTIALS_FILE", str(tmp_path / "missing.json"))
    assert m.main(["--once", "--html-file", str(FIX)]) == 0
    assert not real_db.exists()


# ---------- install command (deployment bundle inside the image) ------------
def _bundle(tmp_path):
    """Builds the bundle exactly like the Dockerfile COPY lines do."""
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
    from app import main as m
    assert m.main(["install", "--target", str(out)]) == 0
    for f in ["docker-compose.yml", ".env", "DEPLOY.md", "config/config.yaml",
              "config/credentials.json", "scripts/bot.sh"]:
        assert (out / f).is_file(), f
    assert "EVE_BOT_IMAGE=nexus.example.com:8083/eve-war-bot:latest" in (out / ".env").read_text()
    assert json.loads((out / "config/credentials.json").read_text())["discord"]["webhook_url"] == ""
    assert os.access(out / "scripts/bot.sh", os.X_OK)

    # user edits survive a second install, even with --force
    (out / "config/credentials.json").write_text('{"discord": {"webhook_url": "https://x"}}')
    (out / "config/config.yaml").write_text("dotlan: {poll_interval_min: 30}\n")
    (out / "docker-compose.yml").write_text("old")
    assert m.main(["install", "--target", str(out), "--force"]) == 0
    assert "https://x" in (out / "config/credentials.json").read_text()
    assert "30" in (out / "config/config.yaml").read_text()
    assert (out / "docker-compose.yml").read_text() != "old"      # managed file refreshed
    assert "kept     config/credentials.json" in capsys.readouterr().out


def test_install_refuses_unwritable_or_missing_target(tmp_path, monkeypatch):
    from app.installer import install
    assert install(str(tmp_path / "nope")) == 2


def test_credentials_folder_gives_clear_error(tmp_path):
    from app.config import ConfigError, load_credentials
    d = tmp_path / "credentials.json"
    d.mkdir()
    with pytest.raises(ConfigError, match="is a folder"):
        load_credentials(str(d), required=False)


# ---------- stats: wars declared on the 1st day of each month ----------------
class HistoryEsi(EsiClient):
    """Synthetic ESI: war IDs 100..(gaps every 7th id), one war every 5 hours."""
    def __init__(self):
        super().__init__("http://esi.invalid", "test")
        from datetime import datetime, timedelta, timezone
        start = datetime(2026, 6, 25, tzinfo=timezone.utc)
        self.data = {}
        wid, t = 100, start
        while t < datetime(2026, 10, 3, tzinfo=timezone.utc):
            if wid % 7:                                   # some IDs don't exist
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
    from datetime import date, datetime, timezone
    from app.stats import collect, render_markdown
    esi = HistoryEsi()
    rows = collect(esi, 4, None, today=date(2026, 10, 2))
    by_month = {r.day.strftime("%Y-%m"): r for r in rows}
    assert list(by_month) == ["2026-07", "2026-08", "2026-09", "2026-10"]
    for r in rows:      # brute-force reference count
        expected = [w for w in esi.data.values() if w["declared"].startswith(r.day.isoformat())]
        assert r.declared == len(expected), r.day
        assert r.mutual == sum(w["mutual"] for w in expected)
        assert r.alliance_aggressor + r.corp_aggressor == r.declared
    assert all(r.declared in (4, 5) for r in rows)
    assert esi.calls < 400                                # binary search, not a full scan
    md = render_markdown(rows, datetime(2026, 10, 2, tzinfo=timezone.utc))
    assert "| 2026-08 |" in md and "Months covered: **4**" in md


def test_stats_bot_columns_from_database(tmp_path):
    from datetime import date
    from app.stats import _bot_counts
    s = _settings(tmp_path, bootstrap_silent=False)
    store = WarStore(s.sqlite_path)
    for w in parse_wars(FIX.read_text()):
        store.add_if_new(w, "pending")
    store.mark_sent([763527], "m1")
    store.db.execute("UPDATE wars SET first_seen_at='2026-10-01T00:00:00+00:00'")
    store.close()
    assert _bot_counts(s.sqlite_path, date(2026, 10, 23)) == (2, 1)
    assert _bot_counts(s.sqlite_path, date(2026, 9, 1)) == (None, None)    # before bot start
