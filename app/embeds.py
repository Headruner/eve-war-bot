"""Builds the rich Discord embed for a war (images, colours, fields, war report)."""
from __future__ import annotations

from datetime import datetime

from .config import Settings
from .models import Party, War

COLORS = {"none": 0xC0392B, "open_for_allies": 0xE67E22, "mutual": 0x8E44AD, "over": 0x7F8C8D}
STATUS_TXT = {"none": "Standard", "open_for_allies": "Open For Allies", "mutual": "Mutual"}
TYPE_ICON = {"alliance": "🛡", "corporation": "🏢"}
EMBED_LIMIT = 6000


def logo_url(p: Party, s: Settings, size: int | None = None) -> str | None:
    """High-resolution logo from the official EVE Image Server (legacy 1.x fallback URL)."""
    if p.entity_id:
        kind = "alliances" if p.type == "alliance" else "corporations"
        return f"{s.image_server}/{kind}/{p.entity_id}/logo?size={size or s.logo_size}"
    return p.logo_url_small


def isk(v: float) -> str:
    for div, suf in ((1e12, "t"), (1e9, "b"), (1e6, "m"), (1e3, "k")):
        if abs(v) >= div:
            return f"{v / div:.2f}{suf}"
    return f"{v:.0f}"


def _ts(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _when(iso: str | None) -> str:
    t = _ts(iso)
    return f"<t:{t}:f> (<t:{t}:R>)" if t else "—"


ZKILL = "https://zkillboard.com"


def zkill_url(p: Party) -> str | None:
    if not p.entity_id:
        return None
    return f"{ZKILL}/{'alliance' if p.type == 'alliance' else 'corporation'}/{p.entity_id}/"


ADAM4EVE = "https://www.adam4eve.eu/structures.php"


def adam4eve_url(p: Party) -> str | None:
    """Adam4EVE structure search for a corporation or alliance (link only, never read by the bot)."""
    if not p.entity_id:
        return None
    corp, alliance = ("", p.entity_id) if p.type == "alliance" else (p.entity_id, "")
    return (f"{ADAM4EVE}?region=&system=&sector=&corp={corp}&alliance={alliance}&search="
            f"&location=30000142&maxJumps=999&group=&structure=&since=&market=")


def _party_field(label: str, p: Party, ticker: str | None = None) -> dict:
    ticker = ticker or getattr(p, "ticker", None)
    tick = f" [{ticker}]" if ticker else ""
    size = []
    if p.members is not None:
        size.append(f"{p.members:,} members")
    if getattr(p, "corporations", None):
        size.append(f"{p.corporations:,} corporations")
    return {
        "name": label,
        "value": f"**[{p.name}]({p.dotlan_url})**{tick}\n{TYPE_ICON.get(p.type, '')} "
                 f"{p.type.title()}" + (" · " + " · ".join(size) if size else ""),
        "inline": True,
    }


def _report_fields(w: War, r: dict, s: Settings) -> list[dict]:
    fields: list[dict] = []
    # ---- timeline
    lines = [f"**Declared:** {_when(r.get('declared'))}",
             f"**Starts:** {_when(r.get('started'))}"]
    if r.get("retracted"):
        lines.append(f"**Retracted:** {_when(r['retracted'])}")
    if r.get("finished"):
        lines.append(f"**Finished:** {_when(r['finished'])}")
    fields.append({"name": "🕒 Timeline", "value": "\n".join(lines)[:1024], "inline": False})

    # ---- score
    a, d = r["aggressor"], r["defender"]
    total = a["isk_destroyed"] + d["isk_destroyed"]
    eff_a = f"{a['isk_destroyed'] / total * 100:.0f}%" if total else "—"
    eff_d = f"{d['isk_destroyed'] / total * 100:.0f}%" if total else "—"
    fields.append({"name": "🔴 Aggressor score",
                   "value": f"Ships killed: **{a['ships_killed']}**\n"
                            f"ISK destroyed: **{isk(a['isk_destroyed'])}**\nEfficiency: {eff_a}",
                   "inline": True})
    fields.append({"name": "🔵 Defender score",
                   "value": f"Ships killed: **{d['ships_killed']}**\n"
                            f"ISK destroyed: **{isk(d['isk_destroyed'])}**\nEfficiency: {eff_d}",
                   "inline": True})

    # ---- allies
    allies = r.get("allies") or []
    if allies:
        shown = ", ".join(a_["name"] for a_ in allies[: s.report_max_allies])
        more = f" … +{len(allies) - s.report_max_allies}" if len(allies) > s.report_max_allies else ""
        fields.append({"name": f"🤝 Defender allies ({len(allies)})",
                       "value": (shown + more)[:1024], "inline": False})

    # ---- kills
    kills = r.get("recent_kills") or []
    if kills:
        rows = []
        for k in kills:
            who = k["victim"] or k["victim_corp"]
            mark = "🔴" if k["loss_of"] == "aggressor" else "🔵"
            t = _ts(k.get("time"))
            rows.append(f"{mark} [{k['ship']}]({k['zkill_url']}) · {who} · {k['system']}"
                        + (f" · <t:{t}:R>" if t else ""))
        total_txt = f"{r['kills_total']}{'+' if r.get('kills_total_capped') else ''}"
        fields.append({"name": f"💥 Recent kills ({total_txt} total)",
                       "value": "\n".join(rows)[:1024], "inline": False})
    if r.get("top_systems"):
        fields.append({"name": "📍 Hot systems",
                       "value": " · ".join(f"{n} ({c})" for n, c in r["top_systems"])[:1024],
                       "inline": False})
    return fields


def _structures_field(label: str, st: dict | None, p: Party | None = None) -> dict | None:
    if st is None:
        return None
    more = adam4eve_url(p) if p else None
    if not st["total"]:
        value = "none publicly known" + (f"\n🔎 [Adam4EVE]({more})" if more else "")
        return {"name": f"🏯 {label} structures", "value": value, "inline": True}
    lines = [" · ".join(f"{t} ×{n}" for t, n in st["by_type"][:6])]
    if st.get("top_systems"):
        lines.append("📍 " + " · ".join(f"{sy} ({n})" for sy, n in st["top_systems"]))
    for x in st.get("listed", []):
        owner = f" · {x['owner']}" if x.get("owner") else ""
        lines.append(f"• {x['name']} ({x['type']}){owner}")
    if st["total"] > len(st.get("listed", [])):
        lines.append(f"… {st['total'] - len(st.get('listed', []))} more")
    value = "\n".join(lines)
    if more:
        tail = f"\n🔎 [Full list on Adam4EVE]({more})"
        value = value[:1024 - len(tail)] + tail
    return {"name": f"🏯 {label} structures ({st['total']})", "value": value[:1024],
            "inline": False}


def build_embed(w: War, s: Settings, banner_filename: str | None = None,
                report: dict | None = None, over: bool = False,
                structures: dict | None = None) -> dict:
    ts = int(w.declared_at.timestamp()) if w.declared_at else None
    a_tick = report["aggressor"].get("ticker") if report else None
    d_tick = report["defender"].get("ticker") if report else None
    status = STATUS_TXT.get(w.status, w.status)
    if report:
        status = "Mutual" if report.get("mutual") else (
            "Open For Allies" if report.get("open_for_allies") else "Standard")
    if over:
        status += " · **ended**"

    links = [f"[zKillboard war](https://zkillboard.com/war/{w.war_id}/)",
             f"[DOTLAN war report]({w.report_url})"]
    for lbl, p in (("Aggressor", w.aggressor), ("Defender", w.defender)):
        if (u := zkill_url(p)):
            links.append(f"[{lbl} kills]({u})")
    for lbl, p in (("Aggressor", w.aggressor), ("Defender", w.defender)):
        if (u := adam4eve_url(p)):
            links.append(f"[{lbl} structures (Adam4EVE)]({u})")

    fields = [_party_field("Aggressor", w.aggressor, a_tick),
              _party_field("Defender", w.defender, d_tick),
              {"name": "Status", "value": status, "inline": True}]
    if report:
        fields += _report_fields(w, report, s)
    else:
        fields.append({"name": "Declared (EVE time)",
                       "value": f"<t:{ts}:F>\n<t:{ts}:R>" if ts else "n/a", "inline": True})
    if structures:
        for lbl, key, p in (("Aggressor", "aggressor", w.aggressor), ("Defender", "defender", w.defender)):
            f = _structures_field(lbl, structures.get(key), p)
            if f:
                fields.append(f)
    fields.append({"name": "🔗 Links", "value": " · ".join(links)[:1024], "inline": False})

    footer = f"Source: EVE Online ESI · War #{w.war_id}"
    if report and report.get("fetched_at"):
        footer += " · report updated"
    embed: dict = {
        "author": {"name": f"{w.aggressor.name} declared war"[:256],
                   "url": w.aggressor.dotlan_url},
        "title": f"⚔ {w.aggressor.name} → {w.defender.name}"[:256],
        "url": w.report_url,
        "color": COLORS["over"] if over else COLORS.get(w.status, COLORS["none"]),
        "fields": fields[:25],
        "footer": {"text": footer},
    }
    if (a_logo := logo_url(w.aggressor, s, 64)):
        embed["author"]["icon_url"] = a_logo
    if (d_logo := logo_url(w.defender, s)):
        embed["thumbnail"] = {"url": d_logo}
    if report and report.get("fetched_at"):
        embed["timestamp"] = report["fetched_at"]
    elif w.declared_at:
        embed["timestamp"] = w.declared_at.isoformat()
    if banner_filename:
        embed["image"] = {"url": f"attachment://{banner_filename}"}
    _fit_limit(embed)
    return embed


def _fit_limit(embed: dict) -> None:
    """Discord rejects embeds > 6000 chars: drop optional fields from the end."""
    def size(e):
        return (len(e.get("title", "")) + len(e["author"]["name"]) + len(e["footer"]["text"])
                + sum(len(f["name"]) + len(f["value"]) for f in e["fields"]))
    optional = ("🏯", "📍 Hot systems", "🤝", "💥")
    while size(embed) > EMBED_LIMIT:
        idx = next((i for i, f in enumerate(embed["fields"])
                    if f["name"].startswith(optional)), None)
        if idx is None:
            break
        embed["fields"].pop(idx)


def build_payload(embeds: list[dict], s: Settings, mention_role_id: str = "") -> dict:
    payload: dict = {"username": s.username, "embeds": embeds,
                     "allowed_mentions": {"parse": []}}
    if s.avatar_url:
        payload["avatar_url"] = s.avatar_url
    if mention_role_id:
        payload["content"] = f"<@&{mention_role_id}>"
        payload["allowed_mentions"] = {"roles": [mention_role_id]}
    return payload
