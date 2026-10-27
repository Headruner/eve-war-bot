# EVE War Bot — EVE Online wars (ESI) → Discord

A small Python service in Docker. It reads new war declarations directly from **CCP's official EVE Online API, ESI** ([docs](https://developers.eveonline.com/docs/services/esi/overview/)), and posts each **new** war to a Discord channel as a message with logos and a banner image. Since version 2.0, no website is scraped. The message also carries a **war report**, the same kind of content as a DOTLAN war page: timeline, score (ships killed, ISK destroyed, efficiency), defender allies, recent kills and hot systems. Since 2.1 each message also lists the **publicly known structures of both sides** (corporation war: the corporation's structures; alliance war: the structures of every member corporation). The report is kept up to date by editing the same Discord message while the war runs. It remembers what it has already posted in a SQLite database on a Docker volume, so restarting or rebuilding the container does not create duplicates.

> **Project documentation** (vision, KPIs, FRD, user stories, tests, statistics): [`docs/wiki/Home.md`](docs/wiki/Home.md).
>
> **New to servers?** Follow the step-by-step guide in [`docs/MANUAL.md`](docs/MANUAL.md): from an empty DigitalOcean droplet to a running bot, copy-and-paste only.

---

## 1. Project layout

```text
eve-war-bot/
├── Dockerfile                    # container image definition
├── docker-compose.yml            # service, volumes, restart policy
├── requirements.txt              # Python dependencies (pinned)
├── .dockerignore / .gitignore    # credentials.json is excluded from image & git
├── .env.example                  # optional: use the prebuilt image from GHCR
├── nexus.env.example             # Nexus registry settings for the publish scripts (copy to nexus.env)
├── deploy/
│   ├── docker-compose.yml        # server compose file (image from a registry, no build) - shipped in the image
│   └── DEPLOY.md                 # short server guide - shipped in the image
├── .github/workflows/docker.yml  # CI: tests + build image on GitHub -> ghcr.io
├── docs/MANUAL.md                # beginner step-by-step deployment guide
├── docs/wiki/                    # project wiki: vision, FRD, user stories, tests, statistics
├── scripts/
│   ├── setup-droplet.sh          # server prep, only adds what is missing: tools, swap, Docker (never touches firewall/ports)
│   ├── bot.sh                    # init | check | test | start | stop | restart | logs | status | update | backup | stats
│   ├── publish-nexus.sh          # build + push the image to Nexus (Linux/macOS)
│   └── publish-nexus.ps1         # same for Windows (Docker Desktop)
├── config/
│   ├── credentials.example.json  # TEMPLATE with empty fields -> copy to credentials.json
│   └── config.yaml               # non-secret settings (interval, filters, images ...)
├── app/
│   ├── main.py                   # scheduler loop: read -> store -> notify -> update reports
│   ├── config.py                 # loads config.yaml + credentials.json, validates
│   ├── source.py                 # new wars: ESI GET /wars/ + /wars/{id}/ -> War objects
│   ├── esi.py                    # CCP ESI client: version-less routes, compatibility date, Expires/ETag cache, rate limits
│   ├── report.py                 # builds the war report (score, allies, kills, systems)
│   ├── store.py                  # SQLite notification storage (dedup)
│   ├── embeds.py                 # rich Discord embed builder
│   ├── banner.py                 # "Aggressor VS Defender" PNG generator (Pillow)
│   ├── structures.py             # structures of each party: daily EVE Ref dataset (streamed) -> SQLite, per-party summary
│   ├── discord_notifier.py       # Discord webhook client: post + edit, rate limits, retries
│   ├── stats.py                  # `stats` command: wars declared on the 1st of each month (ESI + database)
│   ├── installer.py              # `install` command: unpacks the deployment bundle from the image
│   ├── healthcheck.py            # Docker HEALTHCHECK
│   └── models.py                 # War / Party data classes
└── tests/                        # pytest: fake ESI, mock ESI HTTP server, mock Discord server
```

---

## 2. Quick start

1. **Create a Discord webhook.** In Discord, open the channel → *Edit Channel* → *Integrations* → *Webhooks* → *New Webhook* → *Copy Webhook URL*.
2. **Fill in the credentials file.**
   ```bash
   cp config/credentials.example.json config/credentials.json
   # edit config/credentials.json
   ```
   > Create `credentials.json` **before** the first `docker compose up`. If the file is missing, Docker creates an empty *directory* with that name, and the bot stops with "Credentials file not found".
3. **Optionally adjust `config/config.yaml`** (polling interval, filters, banner).
4. **Start the bot.**
   ```bash
   docker compose up -d --build
   docker compose logs -f
   ```
5. **Test without posting.** Set `runtime.dry_run: true` in `config.yaml` or uncomment `DRY_RUN=true` in `docker-compose.yml`. The bot then logs the Discord payloads instead of sending them, and the webhook URL may be empty.

On the **first run**, the bot remembers the newest war ID from ESI and posts nothing (`bootstrap_silent: true`). From then on, every war with a higher ID is posted.

---

## 3. Credentials file

`config/credentials.json` is the only place secrets are kept. It is mounted read-only into the container. It is never copied into the image (`.dockerignore`) and never committed to git (`.gitignore`).

```json
{
  "discord": {
    "webhook_url": "",
    "mention_role_id": ""
  },
  "esi": {
    "contact": ""
  }
}
```

| Field | Required | Meaning |
|---|---|---|
| `discord.webhook_url` | yes (unless dry run) | Full webhook URL `https://discord.com/api/webhooks/{id}/{token}`. Anyone who has it can post to the channel, so treat it as a password. |
| `discord.mention_role_id` | no | Numeric Discord role ID to ping with each message (Developer Mode → right-click role → *Copy Role ID*). Leave empty for no ping. |
| `esi.contact` | **strongly recommended** | Your e-mail address. ESI asks every app to identify itself with a contact in the `User-Agent` ([best practices](https://developers.eveonline.com/docs/services/esi/best-practices/)). The bot sends `eve-war-bot/<version> (<contact>; +https://github.com/Headruner/eve-war-bot) python-requests/<version>`. Files from 1.x with `dotlan.contact` still work. |

The file is checked at startup. An empty webhook, a malformed URL, a non-numeric role ID or invalid JSON stops the bot with **exit code 2** and a clear log message. To check the files without starting the bot:

```bash
docker compose run --rm eve-war-bot --check-config
```

Paths can be changed with the `CREDENTIALS_FILE` and `CONFIG_FILE` environment variables.

---

## 4. How the integration works

### 4.1 Architecture

```plantuml
@startuml
title EVE War Bot - deployment & integrations
skinparam componentStyle rectangle

node "Docker host" {
  folder "./config (bind, read-only)" {
    file "credentials.json" as CR
    file "config.yaml" as CF
  }
  node "container: eve-war-bot" {
    component "main.py\nscheduler" as M
    component "source.py" as S
    component "esi.py\nreport.py" as R
    component "store.py" as ST
    component "embeds.py\nbanner.py" as E
    component "structures.py" as SR
    component "discord_notifier.py" as N
  }
  database "volume: eve-war-bot-data\n/data/wars.db" as DB
}
cloud "esi.evetech.net\n(CCP ESI, public routes)" as ESI
cloud "images.evetech.net\n(EVE Image Server)" as IMG
cloud "data.everef.net\n(EVE Ref structures dataset)" as REF
cloud "discord.com\nWebhook API" as DIS

CR --> M
CF --> M
M --> S
S --> R : EsiClient
M --> R
R --> ESI : GET /wars/, /wars/{id}/,\ncorporations, alliances,\nkillmails, POST /universe/names/
M --> ST
ST --> DB : SQLite
M --> SR
SR --> REF : GET structures-latest.v2.json\n(daily, ETag)
SR --> DB : table structures
M --> E
E --> IMG : GET logos (banner only)
M --> N
N --> DIS : POST (new) / PATCH (update)
DIS ..> IMG : Discord fetches\nlogo URLs itself
@enduml
```

### 4.2 Polling cycle

```plantuml
@startuml
title One polling cycle (every poll_interval_min)
participant "main" as M
participant "source" as S
participant "ESI" as D
database "wars.db" as DB
participant "embeds/banner" as E
participant "EVE Image Server" as I
participant "notifier" as N
participant "Discord" as X

M -> S : newest war IDs
S -> D : GET /wars/  (only after Expires; If-None-Match)
D --> S : [war IDs] or 304
S --> M : IDs above watermark, not stored yet
loop each new ID (oldest first, max_new_per_cycle)
  S -> D : GET /wars/{id}/, POST /universe/names/,\ncorporations / alliances
  M -> DB : INSERT OR IGNORE (state = pending | filtered)
end
M -> DB : watermark = highest processed ID
M -> DB : SELECT state='pending' ORDER BY declared_at
loop batches of batch_embeds
  M -> M : build war report (ESI, see 4.6)
  M -> E : build embed(s)
  E -> I : GET logo 128px (banner)
  I --> E : PNG
  M -> N : send(payload, files)
  N -> X : POST ?wait=true
  alt 200 OK
    X --> N : {id: message_id}
    N --> M : message_id
    M -> DB : state='sent', notified_at, message_id
  else 429 Too Many Requests
    X --> N : retry_after
    N -> N : sleep(retry_after) and retry
  else 5xx / network
    N -> N : exponential back-off, up to 3 tries
    M -> DB : attempts+1 (state='failed' at max_attempts)
  else 401/403/404
    N --> M : WebhookInvalid -> bot stops (exit 3)
  end
end
M -> M : refresh war reports of posted messages (see 4.7)
M -> M : write heartbeat, sleep
@enduml
```

### 4.3 Integration 1 — CCP ESI: new wars (data source)

Since 2.0 the bot reads wars only from ESI, CCP's official API. The [DOTLAN](https://evemaps.dotlan.net/wars) list that 1.x parsed is built from the same ESI data. Reading ESI directly removes the HTML parser, the dependency on a community site and its layout, and the robots.txt question.

| Aspect | Detail |
|---|---|
| Base URL | `https://esi.evetech.net` with **version-less routes** (`/wars/`, not `/latest/wars/`), as recommended in the ESI docs; configurable with `esi.base_url` |
| Version | header `X-Compatibility-Date: <esi.compatibility_date>` (default `2025-08-26`). ESI returns the behaviour of that date and rejects future dates |
| Auth | none: `/wars/`, `/wars/{id}/`, `/corporations/{id}/`, `/alliances/{id}/`, `/universe/names/` are public |
| User-Agent | `eve-war-bot/2.1.0 (<esi.contact>; +https://github.com/Headruner/eve-war-bot) python-requests/<v>` |
| Caching | a response is reused until its **`Expires`** time, so ESI is never asked earlier (`/wars/` is cached for up to 1 h). After that the request carries **`If-None-Match`** with the last `ETag`; a `304` means unchanged and costs 1 rate-limit token instead of 2 |
| Rate limits | token buckets (`X-Ratelimit-Limit` / `-Remaining`): slows down below 10 % · `429` → waits `Retry-After` · old error limit (`X-ESI-Error-Limit-Remain` / `-Reset`, `420`) honoured · `5xx` retried with back-off |
| Frequency | `source.poll_interval_min` (15). Because of the cache, a real request is only sent about once per hour |

**How new wars are found**

1. `GET /wars/` returns the newest 2000 war IDs. War IDs only grow.
2. Every ID **above the stored watermark** (`meta.watermark_war_id`) that is not yet in the database is a new war, processed **oldest first**, at most `source.max_new_per_cycle` (50) per cycle. After an outage the bot catches up in portions.
3. For each new war:

| Call | Gives |
|---|---|
| `GET /wars/{id}/` | `declared`, `mutual`, `open_for_allies`, aggressor / defender (`alliance_id` or `corporation_id`) |
| `POST /universe/names/` | names of both sides |
| `GET /corporations/{id}/` | `ticker`, `member_count` |
| `GET /alliances/{id}/` + `/alliances/{id}/corporations/` | `ticker`, number of corporations. Members = sum of the corporations' `member_count`, only for alliances with ≤ `source.alliance_member_count_max_corps` (20) corporations; for bigger alliances the members are shown as unknown |

4. The watermark is moved to the highest processed ID. A war that ESI lists but answers with 404 is recorded as `skipped` and not retried. A temporary ESI error stops the cycle, and the same war is tried again next cycle.

**First run and upgrades**

| Situation | Behaviour |
|---|---|
| New installation, `bootstrap_silent: true` | watermark = newest war ID; nothing is posted |
| New installation, `bootstrap_silent: false` | all 2000 listed wars are candidates (in portions of `max_new_per_cycle`) |
| Database from 1.x (DOTLAN) | watermark = highest war ID already stored. Wars declared since then are posted, older ones are not |

**Detection time.** ESI caches `/wars/` for up to an hour, so a new war appears in Discord within about **15–75 minutes** of its declaration. DOTLAN had the same delay, because it reads the same ESI data.

### 4.4 Integration 2 — EVE Image Server (images)

| Aspect | Detail |
|---|---|
| Alliance logo | `https://images.evetech.net/alliances/{id}/logo?size=128` |
| Corporation logo | `https://images.evetech.net/corporations/{id}/logo?size=128` |
| Auth | none (official CCP image service) |
| Fallback | none needed: the entity ID always comes from ESI |

The images are used in two ways:

1. **Embed images (URLs only).** The aggressor logo (64 px) appears as the author icon and the defender logo (128 px) as the thumbnail. Discord's servers download these images; the bot only sends the URLs.
2. **Banner (uploaded file).** `banner.py` downloads both logos and draws a 640×220 PNG: aggressor logo · red "VS" · defender logo, with names underneath. The PNG is uploaded with the message as an attachment. If a logo cannot be downloaded, the message is sent without the banner. Turn this off with `images.banner_enabled: false`.

### 4.5 Integration 3 — Discord Webhook API (notifications)

**Request (no banner)**: `POST {webhook_url}?wait=true`, `Content-Type: application/json`

```json
{
  "username": "EVE War Watch",
  "content": "<@&123456789012345678>",
  "allowed_mentions": { "roles": ["123456789012345678"] },
  "embeds": [{
    "author":   { "name": "NuKeDD. declared war", "url": "https://evemaps.dotlan.net/alliance/NuKeDD.",
                  "icon_url": "https://images.evetech.net/alliances/99010678/logo?size=64" },
    "title":    "⚔ NuKeDD. → Fraternity.",
    "url":      "https://evemaps.dotlan.net/war/763527",
    "color":    12597547,
    "thumbnail":{ "url": "https://images.evetech.net/alliances/99003581/logo?size=128" },
    "fields": [
      { "name": "Aggressor", "value": "**[NuKeDD.](…)** [NUKE]\n🛡 Alliance · 13 members · 1 corporations", "inline": true },
      { "name": "Defender",  "value": "**[Fraternity.](…)** [FRAT]\n🛡 Alliance · 154 corporations", "inline": true },
      { "name": "Status",    "value": "Standard", "inline": true },
      { "name": "Declared (EVE time)", "value": "<t:1792765500:F>\n<t:1792765500:R>", "inline": true },
      { "name": "🔗 Links", "value": "[zKillboard war](…) · [DOTLAN war report](…) · [Aggressor kills](…) · [Defender kills](…)" }
    ],
    "image":    { "url": "attachment://war_763527.png" },
    "footer":   { "text": "Source: EVE Online ESI · War #763527" },
    "timestamp":"2026-10-23T14:25:00+00:00"
  }]
}
```

**Request (with banner)**: the same JSON goes in a `multipart/form-data` field called `payload_json`, plus one field per image, `files[0]`, `files[1]`, …, plus an `attachments` list (`[{"id":0,"filename":"war_763527.png"}]`). The embed shows the uploaded file through `image.url = attachment://war_763527.png`.

**Response.** Because of `?wait=true`, Discord returns the created message object. Its `id` is saved in the database (`discord_message_id`), so a notification can be traced to its Discord message, or edited or deleted later.

**Embed elements**

| Element | Content |
|---|---|
| Colour | red = standard · orange = Open For Allies · purple = Mutual |
| `<t:unix:F>` / `<t:unix:R>` | Discord shows the date in each reader's own time zone, plus a relative time ("3 hours ago") |
| `allowed_mentions` | only the configured role can be pinged; names that contain `@everyone` cannot trigger a ping |
| Batching | `batch_embeds: 1..10` puts up to 10 wars into one message (Discord's limit) |
| Size limits | title ≤ 256 characters and field ≤ 1024 are enforced; the whole embed must stay ≤ 6000 characters |

**Rate limits and errors**

| Discord response | Bot behaviour |
|---|---|
| `2xx` | marked `sent`. If `X-RateLimit-Remaining: 0`, waits `X-RateLimit-Reset-After` before the next post. |
| `429` | sleeps for `retry_after` (from the body, or the `Retry-After` header) + 0.25 s, then retries the same message |
| `5xx` / timeout / network | retries with exponential back-off (2, 4, 8 s), up to 3 tries per cycle. Then `attempts+1`; the war stays `pending` and is tried again next cycle. |
| other `4xx` (e.g. 400 bad payload) | `attempts+1` without retrying (sending the same payload again would fail the same way) |
| `401` / `403`, or `404` on a new post | the webhook is wrong or deleted. The bot logs a CRITICAL error and **exits with code 3**, without using up any war's attempts. Docker restarts it, and it keeps failing until `credentials.json` is fixed. |
| `404` on an edit (PATCH) | the message was deleted in Discord: the bot stops updating that war, nothing else changes |
| `attempts >= max_attempts` (5) | state becomes `failed`; that war is never retried |

On top of this, the bot always waits at least `min_seconds_between_posts` (default 2 s) between posts. That keeps it under Discord's webhook limit of about 30 messages per minute, even when many wars arrive at once.

### 4.6 Integration 4 — CCP ESI (war report content)

The report uses the same ESI client as the war source (4.3): version-less routes, compatibility date, cache and rate limits. No login is needed for these routes.

| Call | Used for |
|---|---|
| `GET /wars/{war_id}/` | declared / started / finished / retracted dates, mutual, open for allies, aggressor and defender `ships_killed` + `isk_destroyed`, list of defender allies |
| `GET /wars/{war_id}/killmails/?page=N` | references to all kills in the war (`killmail_id`, `killmail_hash`), up to 2000 per page, page count in `X-Pages` |
| `GET /killmails/{id}/{hash}/` | details for the newest `kill_details_limit` kills: victim, ship type, solar system, time |
| `GET /alliances/{id}/` · `GET /corporations/{id}/` | tickers, shown as `[TICKER]` next to the names |
| `POST /universe/names/` | turns IDs into names (ships, systems, pilots, corps, alliances), up to 1000 IDs per call |

**What the bot does with it**

| Report section | Built from |
|---|---|
| 🕒 Timeline | declared, starts (wars start ~24 h after declaration), retracted, finished |
| 🔴 / 🔵 Score | ships killed and ISK destroyed per side; efficiency = own ISK destroyed ÷ ISK destroyed by both sides |
| 🤝 Defender allies | names of all allies, first `max_allies` shown, then "+N" |
| 💥 Recent kills | newest `recent_kills` kills: ship (linked to zKillboard), victim, system, relative time. 🔴 = aggressor lost the ship, 🔵 = defender side lost it |
| 📍 Hot systems | the 3 systems with the most kills among the fetched kill details |
| 🔗 Links | zKillboard war page · DOTLAN war report · zKillboard pages of both parties (links for readers; the bot never reads them) |

Kills are read only once the war has started; before that, the score shows 0. The report is stored as JSON (`wars.report_json`), so a restart does not lose it.

**Caching and limits.** Names are cached in SQLite (`names` table), so each ID is looked up only once. All other responses follow the `Expires`/`ETag` rules from 4.3. If an extra report call fails, the war is still posted without the report section, and the report is added on a later update.

**Versioning.** `esi.base_url` (default `https://esi.evetech.net`) and `esi.compatibility_date` apply to all ESI calls. To adopt newer ESI behaviour, read the ESI changelog and raise the date. Config files from 1.x with `report.esi_base_url` / `report.esi_compatibility_date` still work.

**Example message with the report** (illustrative values)

```text
⚔ NuKeDD. → Fraternity.                                     [defender logo]
Aggressor                     Defender                     Status
NuKeDD. [NUKE]                Fraternity. [FRAT]           Standard
🛡 Alliance · 13 members       🛡 Alliance · 154 corporations
🕒 Timeline
Declared: 23 October 2026 16:25 (5 hours ago)
Starts:   24 October 2026 16:25 (in 19 hours)
🔴 Aggressor score            🔵 Defender score
Ships killed: 4               Ships killed: 1
ISK destroyed: 1.50b          ISK destroyed: 250.00m
Efficiency: 86%               Efficiency: 14%
🤝 Defender allies (2)
Ally Corp, Ally Alliance
💥 Recent kills (2 total)
🔴 Hurricane · Nuke Corp · Jita · 3 hours ago
🔵 Rifter · Pilot A · Jita · 4 hours ago
📍 Hot systems
Jita (2)
🔗 Links
🏯 Aggressor structures (3)
Astrahus ×2 · Raitaru ×1
📍 Jita (2), Perimeter (1)
• Nuke Home (Astrahus)
• Nuke Factory (Raitaru)
… 1 more
🔎 Full list on Adam4EVE
🏯 Defender structures (0)
none publicly known
🔎 Adam4EVE
🔗 Links
zKillboard war · DOTLAN war report · Aggressor kills · Defender kills · Aggressor structures (Adam4EVE) · Defender structures (Adam4EVE)
[ banner: aggressor logo  VS  defender logo ]
Source: EVE Online ESI · War #763527 · report updated • today 21:30
```

### 4.7 Live report updates (editing the Discord message)

A war posted at declaration has no kills yet. Instead of posting a new message every time something changes, the bot edits the message it already posted.

```plantuml
@startuml
title Live war report update (every update_interval_min)
participant "main" as M
database "wars.db" as DB
participant "ESI" as E
participant "Discord" as X

M -> DB : messages with state='sent', live_done=0,\nposted < track_days ago, report older than interval
loop each message
  M -> E : rebuild report (4.6)
  M -> DB : save report_json, report_updated_at
  alt score / kills / allies / status / end date changed
    M -> X : PATCH {webhook}/messages/{message_id}\n(embeds, keep banner attachment)
  else unchanged
    M -> M : no edit (saves rate limit)
  end
  alt war finished or retracted
    M -> X : final edit (grey colour, "ended")
    M -> DB : live_done = 1
  else message deleted in Discord (404)
    M -> DB : live_done = 1
  end
end
@enduml
```

| Rule | Value |
|---|---|
| Request | `PATCH {webhook_url}/messages/{message_id}` with `embeds` and `attachments: [{"id": <banner id>}]` so the banner stays |
| When | every `update_interval_min` (60), only if the report really changed |
| Stops when | the war is finished or retracted (one final edit, grey colour), the message is deleted, or `track_days` (7) have passed |
| Several wars in one message | with `batch_embeds > 1`, all embeds of that message are rebuilt and edited together |
| Restarts | the message ID, banner attachment ID and last report are in SQLite, so updates continue after a restart |

Live updates edit existing messages, so they never create duplicates. Turn them off with `report.live_updates: false`, or turn the whole report off with `report.enabled: false`.

---

### 4.8 Integration 5 — structures of each party (EVE Ref dataset, since 2.1)

| | |
|---|---|
| Source | `GET https://data.everef.net/structures/structures-latest.v2.json` ([EVE Ref structures dataset](https://docs.everef.net/datasets/structures.html)): one JSON object keyed by structure ID with `owner_id` (corporation), `name`, `type_id`, `solar_system_id`, … |
| Why not adam4eve.eu | its `robots.txt` disallows bots on the structure pages (`structures.php`, `info_stations.php`). EVE Ref collects public structures from ESI and includes a backfill from Adam4EVE, so the content is comparable. |
| When | at start and then at most every `structures.refresh_hours` (24); `If-None-Match` / `If-Modified-Since` → `304` keeps the stored data |
| How | streamed with `ijson` (constant memory), entries without `owner_id` skipped, written into `structures_new` and swapped with the `structures` table in one transaction |
| Corporation war | structures with `owner_id` = the corporation |
| Alliance war | member corporations from ESI `GET /alliances/{id}/corporations/`, then structures of all of them; listed structures name their owner corporation |
| Names | type and system names through ESI `POST /universe/names/` (cached in `names`) |
| Failures | download or parse error → warning, old data kept, retry after 1 h; the message is posted without the structures field. Never blocks a post. |
| Limits | only structures visible to outsiders are known; data is about one day old |
| Adam4EVE link | each structures field and the Links field link to the Adam4EVE search for the party, e.g. `https://www.adam4eve.eu/structures.php?region=&system=&sector=&corp=&alliance=99010320&search=&location=30000142&maxJumps=999&group=&structure=&since=&market=` (`corp=<id>` for a corporation). Readers open it in the browser; the bot never requests it. |

```plantuml
@startuml
title Structures of a war party
participant "main.py" as M
participant "structures.py" as S
database "wars.db\nstructures" as DB
participant "EVE Ref" as R
participant "ESI" as E
M -> S : refresh_if_due()
alt dataset older than refresh_hours
  S -> R : GET structures-latest.v2.json\n(If-None-Match)
  R --> S : 200 (stream) / 304
  S -> DB : swap table (200 only)
end
M -> S : summarize(party)
alt alliance
  S -> E : GET /alliances/{id}/corporations/
end
S -> DB : SELECT ... WHERE owner_id IN (corps)
S -> E : POST /universe/names/ (types, systems, owners)
S --> M : total, by type, top systems, listed
@enduml
```

## 5. Notification storage (no duplicates)

### 5.1 Where

SQLite file `/data/wars.db` on the named Docker volume `eve-war-bot-data`. The volume outlives `docker compose restart`, `down`/`up`, image rebuilds and host reboots. Only `docker compose down -v` or `docker volume rm` deletes it.

### 5.2 Schema

```sql
CREATE TABLE wars (
  war_id             INTEGER PRIMARY KEY,   -- CCP war id = dedup key
  declared_at        TEXT,
  payload            TEXT NOT NULL,         -- parsed War as JSON (resend after restart)
  state              TEXT NOT NULL,         -- pending | sent | skipped | filtered | failed
  attempts           INTEGER NOT NULL DEFAULT 0,
  last_error         TEXT,
  first_seen_at      TEXT NOT NULL,
  notified_at        TEXT,
  discord_message_id TEXT,
  report_json        TEXT,                  -- last war report from ESI (v1.1)
  report_updated_at  TEXT,
  attachments_json   TEXT,                  -- Discord attachment ids (banner) for edits
  live_done          INTEGER NOT NULL DEFAULT 0   -- 1 = message no longer updated
);
CREATE TABLE meta  (key TEXT PRIMARY KEY, value TEXT NOT NULL);  -- bootstrapped_at, watermark_war_id
CREATE TABLE names (id INTEGER PRIMARY KEY, name TEXT, category TEXT, updated_at TEXT);  -- ESI name cache
```

Databases from older versions are upgraded automatically on start: missing columns are added and existing rows are kept. A 1.x database (DOTLAN) gets its watermark from the highest stored war ID (see 4.3).

### 5.3 State machine

```plantuml
@startuml
title War notification state
[*] --> skipped  : listed by ESI but 404,\nor stored by 1.x bootstrap
[*] --> filtered : first seen,\nfilters do not match
[*] --> pending  : first seen,\nmatches filters
pending --> sent    : Discord 2xx
pending --> pending : error, attempts < max
pending --> failed  : attempts >= max
sent --> sent : live report update\n(PATCH, same message)
sent --> [*]
skipped --> [*]
filtered --> [*]
failed --> [*]
@enduml
```

### 5.4 Why duplicates cannot happen

1. `war_id` is the primary key, and new wars are written with `INSERT OR IGNORE`. Reading the same ESI list again never resets a war that is already stored, and IDs at or below the watermark are never read again.
2. Only rows in state `pending` are sent. A row becomes `sent` only after Discord confirms with 2xx.
3. The database runs in WAL mode with `synchronous=FULL`, so a status change is on disk before the next message is sent.
4. Wars that are `pending` when the container stops are saved with their full data (`payload`). They are sent after restart.

**Remaining edge case.** If the container is killed in the few milliseconds between Discord accepting a message and the database saving `sent`, that one message is sent again after restart. Fully ruling this out is not possible with a webhook, because Discord webhooks have no "send only once" key. Normal stops (`docker stop` sends SIGTERM) let the current message finish before the bot exits.

### 5.5 Operations

```bash
# What is stored?
docker compose exec eve-war-bot python -c \
 "import sqlite3;c=sqlite3.connect('/data/wars.db');print(c.execute('select state,count(*) from wars group by state').fetchall())"

# Back up the database
docker run --rm -v eve-war-bot-data:/data -v "$PWD":/backup alpine cp /data/wars.db /backup/

# Retry wars that gave up
docker compose exec eve-war-bot python -c \
 "import sqlite3;c=sqlite3.connect('/data/wars.db');c.execute(\"update wars set state='pending',attempts=0 where state='failed'\");c.commit()"

# Full reset (next start bootstraps silently again)
docker compose down -v
```

---

## 6. Settings (`config/config.yaml`)

| Key | Default | Description |
|---|---|---|
| `source.poll_interval_min` | 15 | minutes between cycles (ESI's cache limits real requests to about 1/hour) |
| `source.bootstrap_silent` | true | first run remembers the newest war ID and posts nothing |
| `source.max_new_per_cycle` | 50 | new wars handled per cycle (catch-up after outages) |
| `source.alliance_member_count_max_corps` | 20 | sum member counts only for alliances up to this many corporations |
| `esi.base_url` | `https://esi.evetech.net` | ESI address (version-less routes) |
| `esi.compatibility_date` | `2025-08-26` | `X-Compatibility-Date` header |
| `discord.username` / `avatar_url` | `EVE War Watch` / – | name and picture the webhook posts as |
| `discord.batch_embeds` | 1 | wars per message (1–10) |
| `discord.min_seconds_between_posts` | 2 | pause between posts |
| `discord.max_attempts` | 5 | tries before a war is marked `failed` |
| `images.logo_size` | 128 | thumbnail size (32/64/128/256) |
| `images.banner_enabled` | true | attach the generated VS banner |
| `report.enabled` | true | add the war report (ESI) to messages |
| `report.recent_kills` | 5 | kills listed in the message |
| `report.kill_details_limit` | 25 | newest kills read in detail (for kills and hot systems) |
| `report.max_killmail_pages` | 1 | killmail pages read (2000 references each) |
| `report.max_allies` | 10 | ally names shown |
| `report.live_updates` | true | edit posted messages with a fresh report |
| `report.update_interval_min` | 60 | minutes between report refreshes |
| `report.track_days` | 7 | stop updating a message after this many days |
| `filters.watch_entity_ids` | `[]` | only wars that involve these alliance/corp IDs (empty = all wars) |
| `filters.statuses` | all | which of `none`, `open_for_allies`, `mutual` to post |
| `filters.min_defender_members` | 0 | skip wars against small defenders (unknown size, e.g. big alliances, is never skipped) |
| `structures.enabled` | true | add the publicly known structures of both parties (2.1) |
| `structures.source_url` | `https://data.everef.net/structures/structures-latest.v2.json` | structures dataset (EVE Ref) |
| `structures.refresh_hours` | 24 | how often the dataset is downloaded (ETag; a 304 costs almost nothing) |
| `structures.max_listed` | 5 | structures listed by name per side (counts per type and systems are always shown) |
| `runtime.dry_run` | false | log payloads instead of posting |
| `runtime.log_level` | INFO | DEBUG / INFO / WARNING |

Keys from 1.x (`dotlan.*`, `report.esi_*`) are still read when the new ones are missing. Wars that do not match the filters are stored as `filtered`. They will **not** be posted later, even if you change the filters afterwards.

---

## 7. Container details

| Item | Value |
|---|---|
| Base image | `python:3.12-slim` + `fonts-dejavu-core` (banner text) |
| User | non-root `bot` (uid 10001) |
| Entry point | `python -m app.main` (extra arguments: `--once`, `--check-config`; `install [--force]` unpacks the deployment bundle; `stats [--months N] [--json]`) |
| Restart | `unless-stopped` |
| Memory | `mem_limit: 256m`, `memswap_limit: 384m`, `mem_reservation: 96m` (measured use ≈ 45–80 MB) |
| CPU / processes | `cpus: 0.5`, `pids_limit: 64` |
| Python memory | `MALLOC_ARENA_MAX=2` (fewer glibc arenas → lower resident memory when idle) |
| Filesystem | `read_only: true`; writable only `/data` (volume) and `/tmp` (32 MB tmpfs); bytecode precompiled at build |
| Hardening | non-root, `cap_drop: ALL`, `no-new-privileges` |
| Image source | built on the server (default) or pulled from `ghcr.io/<owner>/eve-war-bot` (set `EVE_BOT_IMAGE` in `.env`) |
| Health check | every 5 min; *unhealthy* if no successful cycle for 2 × interval + 5 min |
| Logs | stdout, json-file driver, 3 × 5 MB rotation |
| Stop | SIGTERM → the current message finishes → database is closed → exit 0 |
| Exit codes | 0 normal · 2 configuration error · 3 webhook rejected |

### 7.1 Host recommendations (1 GB droplet)

`scripts/setup-droplet.sh` is safe on a server that already runs other applications. It only **adds what is missing**:

| Item | What the script does | Why |
|---|---|---|
| Tools | installs `curl`, `git`, `nano`, `psmisc`, `ca-certificates` only if missing; full `apt upgrade` only with `--upgrade` | no unexpected upgrades or restarts of other services |
| Swap | 1 GB `/swapfile` **only if the server has no swap** | protects a 1 GB server from out-of-memory kills |
| Docker | installs Docker + compose **only if Docker is missing**; an existing Docker is not reconfigured or restarted | other containers keep running |
| Docker logs | `/etc/docker/daemon.json` (3 × 5 MB) only on a fresh Docker install; the bot always limits its own logs in `docker-compose.yml` | the disk can't fill up with logs |
| Environment variables, kernel settings (`sysctl`) | **never touched** | the server's own configuration stays as it is |
| Firewall / ports | **never touched** | other apps on the server keep their open ports; the bot itself needs no incoming port |
| Image build | optional GitHub Actions → GHCR (`.github/workflows/docker.yml`) | the build runs on GitHub, the droplet only downloads the image |

Rough memory budget: OS ≈ 150–250 MB · Docker ≈ 80–120 MB · bot ≈ 45–80 MB (hard cap 256 MB) → about 550–700 MB stay free.

**Dry runs** (`DRY_RUN=true`, `bash scripts/bot.sh test`) use a temporary database in `/tmp`, so a test never marks real wars as "sent".


### 7.2 Delivery through Nexus (build once, install with one command)

The image carries everything a server needs, not only the program. One `install` command on the server unpacks the compose file, the config templates and the helper scripts. After that you only edit the secrets.

```plantuml
@startuml
title Delivery through a Nexus Docker registry
actor Developer as Dev
node "Developer PC\n(Docker Desktop)" as PC
database "Nexus\ndocker (hosted)" as NX
node "Linux VM" as VM
actor Operator as Op

Dev -> PC : scripts/publish-nexus.ps1 (or .sh)
PC -> PC : tests, docker buildx build\n--platform linux/amd64
PC -> NX : push <registry>/eve-war-bot:<version> + :latest
Op -> VM : docker login <registry>
VM -> NX : docker run ... eve-war-bot:latest install
NX --> VM : image
VM -> VM : writes docker-compose.yml, .env,\nconfig/*, scripts/*, DEPLOY.md
Op -> VM : nano config/credentials.json
Op -> VM : bash scripts/bot.sh start
VM -> VM : container runs (pulls :latest)
@enduml
```

**What is inside the image (`/app/deploy`)**

| File unpacked on the server | Owner | On `install --force` / `bot.sh update` |
|---|---|---|
| `docker-compose.yml` (from `deploy/`, no `build:`, image from `.env`) | app | refreshed |
| `scripts/bot.sh`, `scripts/setup-droplet.sh`, `DEPLOY.md`, `config/credentials.example.json` | app | refreshed |
| `config/config.yaml` | you | created once, **never overwritten** |
| `config/credentials.json` (empty template) | you | created once, **never overwritten** |
| `.env` (`EVE_BOT_IMAGE=<registry>/eve-war-bot:latest`, from the build arg `EVE_BOT_IMAGE_REF`) | you | created once, **never overwritten** |

#### A. One-time Nexus setup (Nexus admin)

1. **Repository:** *Administration → Repositories → Create repository → `docker (hosted)`*, e.g. `docker-hosted`.
   - **HTTP/HTTPS connector:** give it a port (e.g. `8083`). The registry address is then `nexus.example.com:8083`. Alternatively use path-based routing (`nexus.example.com/repository/docker-hosted`) if your Nexus version supports it.
   - *Deployment policy:* `Allow redeploy` (needed to overwrite `:latest`).
2. **Realm:** *Security → Realms* → move **Docker Bearer Token Realm** to *Active*.
3. **Users and roles:**
   - `eve-publisher`: privileges `nx-repository-view-docker-docker-hosted-add`, `-edit`, `-read`, `-browse` (push).
   - `eve-server`: only `-read`, `-browse` (pull) → use this one on the VM.
4. **TLS:** put the Docker connector behind HTTPS (reverse proxy or a Nexus certificate). With plain HTTP, every Docker client must list the registry in `insecure-registries` in `/etc/docker/daemon.json` (Docker Desktop: *Settings → Docker Engine*).

#### B. Publish (developer PC)

```powershell
Copy-Item nexus.env.example nexus.env      # NEXUS_REGISTRY=nexus.example.com:8083, NEXUS_USER=eve-publisher
powershell -ExecutionPolicy Bypass -File scripts\publish-nexus.ps1
```

```bash
cp nexus.env.example nexus.env && nano nexus.env
bash scripts/publish-nexus.sh
```

The script runs the tests (if pytest is installed), logs in, runs `docker buildx build --platform linux/amd64` (so it also works from ARM machines), and pushes `:<version>` (from `app/__init__.py`) and `:latest`. At the end it prints the server commands. `nexus.env` is git-ignored. Leave `NEXUS_PASSWORD` empty to be asked for it.

#### C. Install on the Linux VM (one time)

```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/Headruner/eve-war-bot/main/scripts/setup-droplet.sh)"   # optional: tools, swap, Docker if missing (public repos only)
docker login nexus.example.com:8083                              # user eve-server
mkdir -p ~/eve-war-bot && cd ~/eve-war-bot
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/out" nexus.example.com:8083/eve-war-bot:latest install
nano config/credentials.json
bash scripts/bot.sh start
```

For a private GitHub repo, the first line won't work. Install Docker with your usual method, or copy `scripts/setup-droplet.sh` to the server once. After `install`, the script is also in `scripts/` on the server.

#### D. Updates

| Where | Command | Result |
|---|---|---|
| PC | `scripts/publish-nexus.ps1` | new `:<version>` and `:latest` in Nexus |
| VM | `bash scripts/bot.sh update` | pulls `:latest`, runs `install --force` (refreshes compose/scripts, keeps config, secrets, `.env`), restarts |

To stay on a fixed version, set `EVE_BOT_IMAGE=<registry>/eve-war-bot:2.1.0` in `.env` on the VM. `bot.sh` detects a registry setup by the missing `Dockerfile` or a registry image in `.env`, and then pulls instead of building.

## 8. Tests

```bash
pip install -r requirements.txt pytest
pytest -q
```

GitHub Actions runs the same tests on every push and pull request.

The tests cover:
- **War source:** building wars from ESI (names, tickers, members, corporations, status, links), silent bootstrap with the watermark, no re-posting after restarts, catch-up in portions, upgrade from a 1.x database, retry after ESI errors, 404 handling.
- **ESI rules:** version-less route, `X-Compatibility-Date`, `User-Agent` format, `Expires` cache (no request before expiry), `ETag` / `If-None-Match` / 304, `429` with `Retry-After`. These run against a local mock ESI HTTP server.
- **Structures (2.1):** streamed download from a local mock dataset server with `ETag`/304 and refresh interval, corporation vs. alliance (all member corporations) summaries, fields in the posted message, posting continues when the dataset is unavailable, config keys.
- **Everything else:** filters, the multipart banner, the war report and live updates, dry runs, `install`, configuration (including 1.x keys and a Windows BOM), and the statistics algorithm.

They run against a fake ESI class, a mock ESI HTTP server and a mock Discord webhook server. They never call the real ESI or Discord.

## 9. Notes and open points

- Before production, check that the default `esi.compatibility_date` is accepted (the start log shows it; ESI answers with an error for unsupported dates) and consider raising it to a current date after reading the ESI changelog.
- Alliance member counts for big alliances would need one call per corporation, so they are not summed. Raise `alliance_member_count_max_corps` if needed, but watch the ESI rate limits.
- ISK value per kill is not part of ESI; it could be added from zKillboard's API if needed. ESI's per-side `isk_destroyed` totals are used for the score.
- **Structures:** adam4eve.eu is not read, because its `robots.txt` disallows bots on the structure pages. The bot uses the public [EVE Ref structures dataset](https://docs.everef.net/datasets/structures.html), which is built from ESI and includes a backfill from Adam4EVE and other sources. Only structures visible to outsiders are known (private ones are not), and the data is about one day old. The file is large; it is parsed as a stream (`ijson`) so memory stays within the 256 MiB limit, and the first download after a start takes up to a few minutes.
- War end and status changes are shown by editing the existing message; separate "war ended" messages are not in scope yet.
