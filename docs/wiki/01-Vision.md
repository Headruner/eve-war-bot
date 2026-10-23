# Vision — EVE War Bot

| | |
|---|---|
| **Document** | Vision & goals |
| **Product** | EVE War Bot 1.3.0 |
| **Owner** | Andrii Kunitsyn (Business Analyst / Product Owner) |
| **Status** | Draft for review |
| **Updated** | 2026-10-24 |
| **Related** | [FRD](02-FRD.md) · [User stories](03-User-Stories.md) · [Statistics](06-Statistics.md) |

---

## 1. Problem

In EVE Online, any corporation or alliance can declare war on another. After a declaration, the defender's members can be attacked in high-security space. Today, members learn about new wars by looking at the [DOTLAN wars list](https://evemaps.dotlan.net/wars) or the in-game notifications. In practice:

- wars against **friends, allies or targets** are noticed late or not at all;
- the information is spread across DOTLAN, zKillboard and the game, and nobody keeps an overview in the community's own place, **Discord**;
- war progress (kills, ISK, allies) has to be looked up by hand, again and again.

## 2. Vision statement

> **Every war declaration that matters to our community appears in our Discord channel within minutes. It shows at a glance who is fighting whom, and it keeps updating with the war's progress. No one has to watch a website, and nothing on the server has to be looked after.**

## 3. Stakeholders and users

| Stakeholder | Interest | Uses |
|---|---|---|
| Discord members (pilots) | Know quickly about wars that affect them | Read the channel, follow links |
| Alliance / corporation leadership | React to threats, plan, see trends | Channel, [monthly statistics](06-Statistics.md) |
| Discord server admin | Relevant, tidy channel; role pings | Webhook, filters, role mention |
| Bot operator / server owner | Runs unattended on a small or shared server, without side effects on other apps | `scripts/bot.sh`, Docker, logs |
| Developer | Easy to change, test and ship | Repo, tests, CI, Nexus |
| External services | Fair use: DOTLAN (community site), CCP ESI, Discord | Polling limits, User-Agent, rate limits |

## 4. Goals

| ID | Goal | Measured by |
|---|---|---|
| G-1 | **Timely awareness**: new wars reach Discord shortly after DOTLAN lists them | K-1, K-2 |
| G-2 | **Trustworthy channel**: no duplicates, no spam, only relevant wars | K-3, K-4 |
| G-3 | **Understand a war at a glance**: parties, logos, status, score, kills in one message | K-5 |
| G-4 | **Zero-maintenance operation**: runs unattended in a small container and never affects other apps on the server | K-6, K-7, K-8, K-9 |
| G-5 | **Insight**: trend numbers on war activity, starting with the 1st day of each month | K-10 |

## 5. KPIs

Targets apply per calendar month unless stated otherwise. The *measure* column says where the number comes from: the bot database `/data/wars.db`, logs, or `docker stats`.

| ID | KPI | Target | Measure |
|---|---|---|---|
| K-1 | **Detection latency**: time from war declaration to Discord post, P95 | ≤ 30 min (poll interval 15 min) | `notified_at − declared_at` for `sent` wars |
| K-2 | **Coverage**: share of wars declared (ESI) that the bot recorded | ≥ 99 % | [`stats`](06-Statistics.md) "declared" vs "seen by bot" |
| K-3 | **Duplicate messages** | 0 | Database (`war_id` is unique) and a manual check of the channel |
| K-4 | **Delivery success**: `sent / (sent + failed)` | ≥ 99.5 % | Database |
| K-5 | **Report enrichment**: posted wars that carry a war report | ≥ 95 % | `report_json IS NOT NULL` for `sent` wars |
| K-6 | **Availability**: successful cycles / expected cycles | ≥ 99 % | Heartbeat / health check, log `Parsed` lines |
| K-7 | **Resource footprint** | RSS ≤ 100 MiB, CPU ≤ 2 % average | `docker stats` |
| K-8 | **Operator effort** for routine operation | ≤ 15 min / month | Operator estimate |
| K-9 | **Side effects on the host**: unrelated changes to firewall, ports, environment, sysctl or other containers | 0 | [MT-R-21](07-Manual-Test-Scenarios.md#mt-r-21), change review |
| K-10 | **Statistics freshness**: 1st-of-month report available | by the 2nd of each month | [Statistics](06-Statistics.md) page |

KPI definitions for an automated report ([US-07.02](user-stories/US-07.02.md), planned):

```yaml
kpis:
  K-1_detection_latency_p95_min:
    target: "<= 30"
    sql: |
      SELECT (julianday(notified_at) - julianday(declared_at)) * 1440 AS minutes
      FROM wars WHERE state = 'sent' AND notified_at >= date('now','start of month')
      ORDER BY minutes            -- take the value at 95 % of the rows
  K-4_delivery_success_pct:
    target: ">= 99.5"
    sql: |
      SELECT 100.0 * SUM(state='sent') / NULLIF(SUM(state IN ('sent','failed')),0)
      FROM wars WHERE first_seen_at >= date('now','start of month')
  K-5_report_enrichment_pct:
    target: ">= 95"
    sql: |
      SELECT 100.0 * SUM(report_json IS NOT NULL) / NULLIF(COUNT(*),0)
      FROM wars WHERE state = 'sent' AND notified_at >= date('now','start of month')
  K-7_memory_mib:
    target: "<= 100"
    command: docker stats --no-stream --format '{{.MemUsage}}' eve-war-bot
```

Run a query on the server:

```bash
docker compose exec eve-war-bot python -c "import sqlite3;c=sqlite3.connect('/data/wars.db');print(c.execute(\"<SQL>\").fetchall())"
```

## 6. Scope

**In scope (release 1.x)**

- reading new wars from the DOTLAN wars list ([EP-01](02-FRD.md#ep-01-war-detection));
- Discord notifications through a webhook, with filters and an optional role ping ([EP-02](02-FRD.md#ep-02-discord-delivery));
- rich messages: logos, banner, colours, links ([EP-03](02-FRD.md#ep-03-rich-message-content));
- a war report with live updates, built from CCP ESI ([EP-04](02-FRD.md#ep-04-war-report--live-updates));
- configuration through `credentials.json` and `config.yaml` ([EP-05](02-FRD.md#ep-05-configuration--secrets));
- Docker deployment on a small or shared Linux server, Nexus/GHCR delivery, CI ([EP-06](02-FRD.md#ep-06-deployment--operations));
- 1st-of-month war statistics ([EP-07](02-FRD.md#ep-07-reporting--statistics)).

**Out of scope (for now)**

- Discord slash commands or buttons (they would need an incoming HTTPS endpoint);
- in-game notifications, EVE SSO login, private (authenticated) ESI data;
- more than one Discord channel per bot instance (run several instances instead);
- a web UI or dashboard;
- reading DOTLAN `/war/{id}` pages, which DOTLAN's `robots.txt` disallows for bots. The same data comes from ESI instead.

## 7. Constraints and principles

- **Be a good citizen:** poll DOTLAN no more than every 10–15 minutes, identify the bot with a contact in its `User-Agent`, respect ESI and Discord rate limits.
- **Don't touch the host:** the bot and its scripts add only what is missing. They never change firewall rules, open ports, environment variables or sysctl, and never restart other services. This is a lesson from release 1.3.0, recorded in the [FRD](02-FRD.md#8-constraints).
- **Secrets only in `config/credentials.json`:** never in git, the image or logs.
- **Small footprint:** a 1 GB / 2 vCPU droplet that runs other apps as well.

## 8. Milestones

| Version | Content | Status |
|---|---|---|
| 1.0 | DOTLAN → Discord, rich embeds, SQLite dedup, Docker | Done |
| 1.1 | War report from ESI, live message updates | Done |
| 1.2 | Container limits and hardening, operator scripts, beginner manual, CI | Done |
| 1.3 | Nexus delivery, one-command install, safe setup, revert script, `stats` | Done, field verification ongoing |
| 1.4 (proposal) | KPI report ([US-07.02](user-stories/US-07.02.md)), closing the [automated test gaps](05-Integration-Tests.md#4-coverage-gaps) | Planned |

## 9. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| DOTLAN changes its HTML layout | No new wars detected | `ScrapeError` in the log, health check goes unhealthy, parser isolated in one module ([US-01.06](user-stories/US-01.06.md)) |
| DOTLAN restricts automated access | Feature stops | Contact in `User-Agent`, low polling rate; fall-back option: ESI `/wars/` as the source |
| CCP changes ESI (versioning) | War report or statistics missing | Base URL and compatibility date are configurable; the core function doesn't depend on ESI ([US-04.05](user-stories/US-04.05.md)) |
| Webhook URL leaks | Spam in the channel | Webhook only in `credentials.json`; regenerate the webhook in Discord |
| Changes to a shared server | Other apps disrupted | Principle "don't touch the host", [revert script](user-stories/US-06.06.md) |
