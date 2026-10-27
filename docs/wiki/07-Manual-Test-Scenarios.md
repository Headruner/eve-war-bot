# Manual test scenarios

[Home](Home.md) › Manual tests

| | |
|---|---|
| **Suites** | Sanity (6 scenarios, 7 SP) · Regression (35 scenarios, 90 SP) |
| **Total** | **97 SP** |
| **Updated** | 2026-10-27 (2.1.0) |

---

## 1. Estimation and execution rules

Estimates are in **story points (SP)** for preparation + execution + recording the result, by one tester who knows the setup:

| SP | Effort (preparation + execution) |
|---:|---|
| 1 | ≤ 15 min |
| 2 | ≈ 30 min |
| 3 | ≈ 1 h |
| 5 | ≈ 2–3 h (incl. waiting time) |
| 8 | ≈ ½ day |

So the **sanity suite** takes about 1.5–2 hours (one scenario waits 16 minutes for two poll cycles). The full **regression suite** is spread over several days, because some scenarios wait for real events (a new war, kills, the end of a war).

| Suite | When | Who | Pass criterion |
|---|---|---|---|
| **Sanity** | after every install, update or configuration change | Operator | all scenarios pass; otherwise stop and roll back |
| **Regression** | before a release is accepted ([Acceptance testing](04-Acceptance-Testing.md)), after changes to parser, Docker setup or scripts | Tester / PO | all *Must* stories' scenarios pass; others pass or are deferred by the PO |

Use a **test channel** with its own webhook for every scenario that posts. Scenarios that change files say so in their preconditions: always keep a copy of `config/credentials.json`.

## 2. Sanity suite

| ID | Scenario | Stories | SP |
|---|---|---|---:|
| [MT-S-01](#mt-s-01) | Configuration check passes | [US-05.01](user-stories/US-05.01.md) | 1 |
| [MT-S-02](#mt-s-02) | Dry run shows messages and posts nothing | [US-05.03](user-stories/US-05.03.md), [US-01.02](user-stories/US-01.02.md) | 1 |
| [MT-S-03](#mt-s-03) | Bot starts and stays healthy | [US-06.01](user-stories/US-06.01.md), [US-06.03](user-stories/US-06.03.md) | 1 |
| [MT-S-04](#mt-s-04) | A war is posted with full content | [US-02.01](user-stories/US-02.01.md), [US-03.01](user-stories/US-03.01.md), [US-03.02](user-stories/US-03.02.md), [US-03.03](user-stories/US-03.03.md), [US-04.01](user-stories/US-04.01.md) | 2 |
| [MT-S-05](#mt-s-05) | No duplicate after restart | [US-01.04](user-stories/US-01.04.md), [US-06.02](user-stories/US-06.02.md) | 1 |
| [MT-S-06](#mt-s-06) | Polling runs on schedule | [US-01.01](user-stories/US-01.01.md) | 1 |
| | **Total sanity** | | **7** |

## 3. Regression suite

| ID | Scenario | Stories | SP |
|---|---|---|---:|
| [MT-R-01](#mt-r-01) | Silent bootstrap on a fresh installation | [US-01.05](user-stories/US-01.05.md) | 2 |
| [MT-R-02](#mt-r-02) | War data matches ESI and DOTLAN | [US-01.02](user-stories/US-01.02.md), [US-01.03](user-stories/US-01.03.md) | 3 |
| [MT-R-03](#mt-r-03) | A real new war is posted in time | [US-01.01](user-stories/US-01.01.md), [US-01.04](user-stories/US-01.04.md), [US-02.01](user-stories/US-02.01.md) | 5 |
| [MT-R-04](#mt-r-04) | Empty webhook is rejected | [US-05.01](user-stories/US-05.01.md) | 1 |
| [MT-R-05](#mt-r-05) | Credentials folder instead of file | [US-05.01](user-stories/US-05.01.md), [US-06.04](user-stories/US-06.04.md) | 1 |
| [MT-R-06](#mt-r-06) | Invalid JSON is rejected | [US-05.01](user-stories/US-05.01.md) | 1 |
| [MT-R-07](#mt-r-07) | Deleted webhook stops the bot clearly | [US-02.03](user-stories/US-02.03.md) | 2 |
| [MT-R-08](#mt-r-08) | Role mention pings only that role | [US-02.04](user-stories/US-02.04.md) | 2 |
| [MT-R-09](#mt-r-09) | Batching several wars | [US-02.05](user-stories/US-02.05.md) | 2 |
| [MT-R-10](#mt-r-10) | Filters | [US-02.06](user-stories/US-02.06.md) | 3 |
| [MT-R-11](#mt-r-11) | Banner off and logo fallback | [US-03.01](user-stories/US-03.01.md), [US-03.02](user-stories/US-03.02.md) | 2 |
| [MT-R-12](#mt-r-12) | Colours, times and links | [US-03.03](user-stories/US-03.03.md) | 2 |
| [MT-R-13](#mt-r-13) | War report content is correct | [US-04.01](user-stories/US-04.01.md), [US-04.02](user-stories/US-04.02.md) | 3 |
| [MT-R-14](#mt-r-14) | Live update edits the same message | [US-04.03](user-stories/US-04.03.md) | 5 |
| [MT-R-15](#mt-r-15) | End of war | [US-04.04](user-stories/US-04.04.md) | 5 |
| [MT-R-16](#mt-r-16) | ESI unavailable | [US-04.05](user-stories/US-04.05.md) | 2 |
| [MT-R-17](#mt-r-17) | Persistence across down/up and rebuild | [US-06.02](user-stories/US-06.02.md) | 2 |
| [MT-R-18](#mt-r-18) | Resource limits and hardening | [US-06.01](user-stories/US-06.01.md) | 1 |
| [MT-R-19](#mt-r-19) | Unhealthy when cycles fail | [US-06.03](user-stories/US-06.03.md) | 5 |
| [MT-R-20](#mt-r-20) | Operations commands | [US-06.04](user-stories/US-06.04.md) | 3 |
| [MT-R-21](#mt-r-21) | Setup script is safe on an existing server | [US-06.05](user-stories/US-06.05.md) | 3 |
| [MT-R-22](#mt-r-22) | Revert script | [US-06.06](user-stories/US-06.06.md) | 5 |
| [MT-R-23](#mt-r-23) | Publish to Nexus and install on a clean VM | [US-06.07](user-stories/US-06.07.md), [US-06.08](user-stories/US-06.08.md) | 5 |
| [MT-R-24](#mt-r-24) | Update from the registry keeps user files | [US-06.08](user-stories/US-06.08.md) | 2 |
| [MT-R-25](#mt-r-25) | CI workflow | [US-06.09](user-stories/US-06.09.md) | 2 |
| [MT-R-26](#mt-r-26) | 1st-of-month statistics | [US-07.01](user-stories/US-07.01.md) | 3 |
| [MT-R-27](#mt-r-27) | Settings take effect after restart | [US-05.02](user-stories/US-05.02.md) | 1 |
| [MT-R-28](#mt-r-28) | Dry run leaves real data untouched | [US-05.03](user-stories/US-05.03.md) | 1 |
| [MT-R-29](#mt-r-29) | Many wars at once (rate limit) | [US-02.02](user-stories/US-02.02.md) | 3 |
| [MT-R-30](#mt-r-30) | ESI outage and recovery | [US-01.06](user-stories/US-01.06.md), [US-01.07](user-stories/US-01.07.md) | 2 |
| [MT-R-31](#mt-r-31) | ESI request rules | [US-01.07](user-stories/US-01.07.md) | 2 |
| [MT-R-32](#mt-r-32) | Upgrade a 1.x installation | [US-01.08](user-stories/US-01.08.md) | 3 |
| [MT-R-33](#mt-r-33) | Structures in a corporation war | [US-03.04](user-stories/US-03.04.md), [US-03.06](user-stories/US-03.06.md) | 2 |
| [MT-R-34](#mt-r-34) | Structures in an alliance war | [US-03.05](user-stories/US-03.05.md) | 2 |
| [MT-R-35](#mt-r-35) | Structures dataset unavailable / disabled | [US-03.06](user-stories/US-03.06.md) | 2 |
| | **Total regression** | | **90** |

## 4. Test helpers

### Re-queue wars for a test

Puts the newest `N` stored wars back to `pending`, so the bot posts them on the next start. Use a test channel.

```bash
cd ~/eve-war-bot
N=1   # how many
docker compose exec eve-war-bot python -c "import sqlite3;c=sqlite3.connect('/data/wars.db');c.execute(\"update wars set state='pending',attempts=0 where war_id in (select war_id from wars where payload!='{}' order by war_id desc limit $N)\");c.commit();print('queued',c.total_changes)"
bash scripts/bot.sh restart
```

### Look at stored wars

```bash
docker compose exec eve-war-bot python -c "import sqlite3;c=sqlite3.connect('/data/wars.db');[print(r) for r in c.execute('select war_id,state,attempts,notified_at,last_error from wars order by war_id desc limit 10')]"
```

### Reset everything (test servers only)

```bash
docker compose down -v      # deletes the bot's memory; the next start bootstraps silently
```

## 5. Scenario details

<a id="mt-s-01"></a>
### MT-S-01 — Configuration check passes

**Suite:** Sanity · **Estimate:** 1 SP · **Stories:** [US-05.01](user-stories/US-05.01.md)

**Preconditions:** Bot installed, `config/credentials.json` filled in.

**Steps**

1. `bash scripts/bot.sh check`

**Expected result:** `Configuration OK` is printed, exit code 0.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-s-02"></a>
### MT-S-02 — Dry run shows messages and posts nothing

**Suite:** Sanity · **Estimate:** 1 SP · **Stories:** [US-05.03](user-stories/US-05.03.md), [US-01.02](user-stories/US-01.02.md)

**Preconditions:** MT-S-01 passed.

**Steps**

1. `bash scripts/bot.sh test`
2. Look at the Discord channel.

**Expected result:** Log shows `ESI: NNNN war IDs listed`; `[DRY RUN] POST` lines only if there are new wars; no message in Discord.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-s-03"></a>
### MT-S-03 — Bot starts and stays healthy

**Suite:** Sanity · **Estimate:** 1 SP · **Stories:** [US-06.01](user-stories/US-06.01.md), [US-06.03](user-stories/US-06.03.md)

**Preconditions:** MT-S-01 passed.

**Steps**

1. `bash scripts/bot.sh start`
2. Wait 3 minutes.
3. `bash scripts/bot.sh status`

**Expected result:** Container `Up` and `(healthy)`; memory well below 256 MiB.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-s-04"></a>
### MT-S-04 — A war is posted with full content

**Suite:** Sanity · **Estimate:** 2 SP · **Stories:** [US-02.01](user-stories/US-02.01.md), [US-03.01](user-stories/US-03.01.md), [US-03.02](user-stories/US-03.02.md), [US-03.03](user-stories/US-03.03.md), [US-04.01](user-stories/US-04.01.md)

**Preconditions:** Bot running (MT-S-03).

**Steps**

1. Re-queue the newest war: see [Test helpers → Re-queue wars](#re-queue-wars-for-a-test).
2. `bash scripts/bot.sh restart`
3. Open the Discord channel.

**Expected result:** One message: title with both names, logos, banner, status colour, timeline, score, links; log `Notified war(s) [...]`.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-s-05"></a>
### MT-S-05 — No duplicate after restart

**Suite:** Sanity · **Estimate:** 1 SP · **Stories:** [US-01.04](user-stories/US-01.04.md), [US-06.02](user-stories/US-06.02.md)

**Preconditions:** MT-S-04 passed.

**Steps**

1. `bash scripts/bot.sh restart`
2. Wait for the first cycle in the log.

**Expected result:** `ESI: NNNN war IDs listed, 0 new.`; no new message for the same war.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-s-06"></a>
### MT-S-06 — Polling runs on schedule

**Suite:** Sanity · **Estimate:** 1 SP · **Stories:** [US-01.01](user-stories/US-01.01.md)

**Preconditions:** Bot running.

**Steps**

1. `bash scripts/bot.sh logs`, watch for 16 minutes.

**Expected result:** An `ESI: ... war IDs listed` line every ~15 minutes; no ERROR lines.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-01"></a>
### MT-R-01 — Silent bootstrap on a fresh installation

**Suite:** Regression · **Estimate:** 2 SP · **Stories:** [US-01.05](user-stories/US-01.05.md)

**Preconditions:** Test server or `docker compose down -v` (deletes the bot's memory!).

**Steps**

1. `bash scripts/bot.sh start`
2. `bash scripts/bot.sh logs`

**Expected result:** `Bootstrap: stored NN existing wars silently`; no messages in Discord.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-02"></a>
### MT-R-02 — War data matches ESI and DOTLAN

**Suite:** Regression · **Estimate:** 3 SP · **Stories:** [US-01.02](user-stories/US-01.02.md), [US-01.03](user-stories/US-01.03.md)

**Preconditions:** Bot running with several posted wars; DOTLAN wars page open in a browser as an independent cross-check.

**Steps**

1. Pick 5 rows (incl. one long name, one Mutual, one Open For Allies).
2. Compare with `bash scripts/bot.sh status` / the database or posted messages.

**Expected result:** War ID, full names, types, member counts, declared time (UTC) and status match for all 5.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-03"></a>
### MT-R-03 — A real new war is posted in time

**Suite:** Regression · **Estimate:** 5 SP · **Stories:** [US-01.01](user-stories/US-01.01.md), [US-01.04](user-stories/US-01.04.md), [US-02.01](user-stories/US-02.01.md)

**Preconditions:** Bot running ≥ 1 cycle.

**Steps**

1. Note a new war on DOTLAN or zKillboard and its declared time.
2. Check Discord and the log.

**Expected result:** Message appears ≤ 75 min after the declaration (ESI cache up to 1 h + poll interval); exactly once.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-04"></a>
### MT-R-04 — Empty webhook is rejected

**Suite:** Regression · **Estimate:** 1 SP · **Stories:** [US-05.01](user-stories/US-05.01.md)

**Preconditions:** Copy of a valid `credentials.json` saved.

**Steps**

1. Set `webhook_url` to `""`.
2. `bash scripts/bot.sh check`
3. Restore the file.

**Expected result:** `Configuration error: 'discord.webhook_url' is empty`, exit code 2.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-05"></a>
### MT-R-05 — Credentials folder instead of file

**Suite:** Regression · **Estimate:** 1 SP · **Stories:** [US-05.01](user-stories/US-05.01.md), [US-06.04](user-stories/US-06.04.md)

**Preconditions:** Test copy of the project.

**Steps**

1. Rename `credentials.json`; create a folder with that name.
2. `bash scripts/bot.sh check`
3. Restore.

**Expected result:** Clear message that it is a folder and how to fix it.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-06"></a>
### MT-R-06 — Invalid JSON is rejected

**Suite:** Regression · **Estimate:** 1 SP · **Stories:** [US-05.01](user-stories/US-05.01.md)

**Preconditions:** Copy of a valid `credentials.json` saved.

**Steps**

1. Delete one quote in the file.
2. `bash scripts/bot.sh check`
3. Restore.

**Expected result:** `Invalid JSON in ...` with line/column, exit code 2.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-07"></a>
### MT-R-07 — Deleted webhook stops the bot clearly

**Suite:** Regression · **Estimate:** 2 SP · **Stories:** [US-02.03](user-stories/US-02.03.md)

**Preconditions:** A second, disposable webhook in a test channel.

**Steps**

1. Put the disposable webhook into `credentials.json`, restart, re-queue one war.
2. Delete the webhook in Discord, re-queue another war, restart.
3. Check logs and `docker compose ps`.

**Expected result:** CRITICAL `Discord webhook rejected (HTTP 404)`; container restarts repeatedly; war stays `pending` with unchanged attempts.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-08"></a>
### MT-R-08 — Role mention pings only that role

**Suite:** Regression · **Estimate:** 2 SP · **Stories:** [US-02.04](user-stories/US-02.04.md)

**Preconditions:** Test role and a test member.

**Steps**

1. Set `mention_role_id`, restart, re-queue one war.
2. Remove it, restart, re-queue another war.

**Expected result:** First message pings only the test role; second pings nobody.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-09"></a>
### MT-R-09 — Batching several wars

**Suite:** Regression · **Estimate:** 2 SP · **Stories:** [US-02.05](user-stories/US-02.05.md)

**Preconditions:** Test channel.

**Steps**

1. Set `batch_embeds: 10`, re-queue 3 wars, restart.

**Expected result:** One message with 3 embeds and 3 banners.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-10"></a>
### MT-R-10 — Filters

**Suite:** Regression · **Estimate:** 3 SP · **Stories:** [US-02.06](user-stories/US-02.06.md)

**Preconditions:** Test channel.

**Steps**

1. Set `watch_entity_ids` to one alliance from the list; re-queue 3 wars (1 matching).
2. Repeat with `statuses: [mutual]` and with `min_defender_members: 100`.

**Expected result:** Only matching wars are posted; others stored as `filtered`.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-11"></a>
### MT-R-11 — Banner off and logo fallback

**Suite:** Regression · **Estimate:** 2 SP · **Stories:** [US-03.01](user-stories/US-03.01.md), [US-03.02](user-stories/US-03.02.md)

**Preconditions:** Test channel.

**Steps**

1. Set `banner_enabled: false`, re-queue one war.
2. Check logo URLs in the message (right-click → open image).

**Expected result:** No banner; logos from images.evetech.net at 64/128 px.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-12"></a>
### MT-R-12 — Colours, times and links

**Suite:** Regression · **Estimate:** 2 SP · **Stories:** [US-03.03](user-stories/US-03.03.md)

**Preconditions:** Messages for a standard, a mutual and an open-for-allies war (re-queue).

**Steps**

1. Compare colours; hover the dates; click every link.

**Expected result:** Red / purple / orange; dates in your own time zone; links open the right DOTLAN, zKillboard and party pages.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-13"></a>
### MT-R-13 — War report content is correct

**Suite:** Regression · **Estimate:** 3 SP · **Stories:** [US-04.01](user-stories/US-04.01.md), [US-04.02](user-stories/US-04.02.md)

**Preconditions:** A posted war that has started and has kills.

**Steps**

1. Compare timeline, score, allies, recent kills and systems with the DOTLAN war report and zKillboard.

**Expected result:** Values match (ISK may differ slightly from zKillboard prices; ships killed must match).

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-14"></a>
### MT-R-14 — Live update edits the same message

**Suite:** Regression · **Estimate:** 5 SP · **Stories:** [US-04.03](user-stories/US-04.03.md)

**Preconditions:** `update_interval_min: 60`; a posted war that is active.

**Steps**

1. Note the message; wait until kills happen and ≥ 1 interval passes.
2. Check the channel and the log.

**Expected result:** Same message updated (footer 'report updated'), no new message; `Updated war report in message ...`.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-15"></a>
### MT-R-15 — End of war

**Suite:** Regression · **Estimate:** 5 SP · **Stories:** [US-04.04](user-stories/US-04.04.md)

**Preconditions:** A posted war that is about to finish/retract.

**Steps**

1. Wait until ESI shows `finished`/`retracted`; wait one update interval.

**Expected result:** Message turns grey and says 'ended'; no further updates in the log.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-16"></a>
### MT-R-16 — ESI unavailable

**Suite:** Regression · **Estimate:** 2 SP · **Stories:** [US-04.05](user-stories/US-04.05.md)

**Preconditions:** Test copy; set `report.esi_base_url` to an unreachable address.

**Steps**

1. Re-queue one war, restart.
2. Restore the URL.

**Expected result:** Message posted without report; warning `War report ... unavailable`.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-17"></a>
### MT-R-17 — Persistence across down/up and rebuild

**Suite:** Regression · **Estimate:** 2 SP · **Stories:** [US-06.02](user-stories/US-06.02.md)

**Preconditions:** Bot running with posted wars.

**Steps**

1. `docker compose down` then `bash scripts/bot.sh start` (rebuild).
2. Check log and Discord.

**Expected result:** `stored={...}` shows the old counts; `0 new`; no repeats.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-18"></a>
### MT-R-18 — Resource limits and hardening

**Suite:** Regression · **Estimate:** 1 SP · **Stories:** [US-06.01](user-stories/US-06.01.md)

**Preconditions:** Bot running.

**Steps**

1. `docker stats --no-stream eve-war-bot`
2. `docker inspect eve-war-bot --format '{{.Config.User}} {{.HostConfig.ReadonlyRootfs}} {{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}'`

**Expected result:** Memory limit 256 MiB, usage < 100 MiB; user 10001, read-only true, NanoCpus 500000000; no published ports.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-19"></a>
### MT-R-19 — Unhealthy when cycles fail

**Suite:** Regression · **Estimate:** 5 SP · **Stories:** [US-06.03](user-stories/US-06.03.md)

**Preconditions:** Test copy; set `esi.base_url` to an unreachable address and `poll_interval_min: 1`.

**Steps**

1. Start, wait ~10 minutes.
2. `docker compose ps`
3. Restore settings.

**Expected result:** Status becomes `unhealthy`; ERROR lines in the log; container keeps running.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-20"></a>
### MT-R-20 — Operations commands

**Suite:** Regression · **Estimate:** 3 SP · **Stories:** [US-06.04](user-stories/US-06.04.md)

**Preconditions:** Bot running.

**Steps**

1. Run `status`, `logs`, `backup`, `restart`, `update` of `scripts/bot.sh`.

**Expected result:** Each works as documented; backup file in `backups/` opens with SQLite.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-21"></a>
### MT-R-21 — Setup script is safe on an existing server

**Suite:** Regression · **Estimate:** 3 SP · **Stories:** [US-06.05](user-stories/US-06.05.md)

**Preconditions:** Test VM with a dummy web app (e.g. nginx container on port 80) and ufw inactive.

**Steps**

1. Record `ufw status`, `sysctl vm.swappiness`, `docker ps`, `env`.
2. `sudo bash scripts/setup-droplet.sh`
3. Record the same again.

**Expected result:** Everything unchanged; web app still reachable; containers not restarted (same uptime).

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-22"></a>
### MT-R-22 — Revert script

**Suite:** Regression · **Estimate:** 5 SP · **Stories:** [US-06.06](user-stories/US-06.06.md)

**Preconditions:** Test VM where the old setup script version was run.

**Steps**

1. `sudo bash scripts/revert-setup.sh --dry-run`
2. Run it for real, answer y/N per item.
3. Check ufw, swappiness, packages.

**Expected result:** Dry run changes nothing; real run reverts only confirmed items; Docker kept when other containers exist.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-23"></a>
### MT-R-23 — Publish to Nexus and install on a clean VM

**Suite:** Regression · **Estimate:** 5 SP · **Stories:** [US-06.07](user-stories/US-06.07.md), [US-06.08](user-stories/US-06.08.md)

**Preconditions:** Nexus docker (hosted) repo, publisher and reader users.

**Steps**

1. Run `publish-nexus.ps1`.
2. On a clean VM: `docker login`, `install` command, fill credentials, `bot.sh start`.

**Expected result:** Image `:<version>` and `:latest` in Nexus; bot runs on the VM from the pulled image.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-24"></a>
### MT-R-24 — Update from the registry keeps user files

**Suite:** Regression · **Estimate:** 2 SP · **Stories:** [US-06.08](user-stories/US-06.08.md)

**Preconditions:** MT-R-23 done; publish a new version.

**Steps**

1. On the VM: `bash scripts/bot.sh update`.

**Expected result:** New image running; `credentials.json`, `config.yaml`, `.env`, database unchanged.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-25"></a>
### MT-R-25 — CI workflow

**Suite:** Regression · **Estimate:** 2 SP · **Stories:** [US-06.09](user-stories/US-06.09.md)

**Preconditions:** Push access to GitHub.

**Steps**

1. Push a commit to `main`; open the Actions tab.

**Expected result:** Tests green; image in GHCR with `latest` and `sha-…` tags.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-26"></a>
### MT-R-26 — 1st-of-month statistics

**Suite:** Regression · **Estimate:** 3 SP · **Stories:** [US-07.01](user-stories/US-07.01.md)

**Preconditions:** Bot installed on the server.

**Steps**

1. `bash scripts/bot.sh stats 3`
2. Spot-check one month: count wars declared on the 1st on zKillboard/ESI.

**Expected result:** Table with 3 months; counts match the spot check; bot columns `—` before installation.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-27"></a>
### MT-R-27 — Settings take effect after restart

**Suite:** Regression · **Estimate:** 1 SP · **Stories:** [US-05.02](user-stories/US-05.02.md)

**Preconditions:** Bot running.

**Steps**

1. Change `poll_interval_min` to 10, `bash scripts/bot.sh restart`.

**Expected result:** Start log shows `interval 10 min`.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-28"></a>
### MT-R-28 — Dry run leaves real data untouched

**Suite:** Regression · **Estimate:** 1 SP · **Stories:** [US-05.03](user-stories/US-05.03.md)

**Preconditions:** Bot running with posted wars.

**Steps**

1. `bash scripts/bot.sh status` (note counts)
2. `bash scripts/bot.sh test`
3. `bash scripts/bot.sh status`

**Expected result:** Counts identical before and after.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-29"></a>
### MT-R-29 — Many wars at once (rate limit)

**Suite:** Regression · **Estimate:** 3 SP · **Stories:** [US-02.02](user-stories/US-02.02.md)

**Preconditions:** Test channel; `batch_embeds: 1`.

**Steps**

1. Re-queue 15 wars, restart.
2. Watch the log.

**Expected result:** All 15 posted, ≥ 2 s apart; any 429 is followed by a successful retry.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-30"></a>
### MT-R-30 — ESI outage and recovery

**Suite:** Regression · **Estimate:** 2 SP · **Stories:** [US-01.06](user-stories/US-01.06.md), [US-01.07](user-stories/US-01.07.md)

**Preconditions:** Test copy; bot running and bootstrapped.

**Steps**

1. Set `esi.base_url` to `https://esi.evetech.net/does-not-exist`, restart, wait one cycle.
2. Restore the URL, restart, re-queue one war.

**Expected result:** First: `ESI error: ...` in the log, container keeps running; after restoring: the war is posted, no repeats.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-31"></a>
### MT-R-31 — ESI request rules

**Suite:** Regression · **Estimate:** 2 SP · **Stories:** [US-01.07](user-stories/US-01.07.md)

**Preconditions:** Bot running with `runtime.log_level: DEBUG` on a test copy.

**Steps**

1. Watch two cycles within the same hour.
2. Check the start log for compatibility date and contact warning.

**Expected result:** Second cycle sends no `/wars/` request (cache); no `No contact` warning when `esi.contact` is set.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-32"></a>
### MT-R-32 — Upgrade a 1.x installation

**Suite:** Regression · **Estimate:** 3 SP · **Stories:** [US-01.08](user-stories/US-01.08.md)

**Preconditions:** Test server with a running 1.x bot and its database.

**Steps**

1. Update to 2.0 (`git pull` + `bash scripts/bot.sh start`).
2. Watch the log and the channel for one hour.

**Expected result:** Log `Upgrade from 1.x: continuing after war N`; only wars declared after the upgrade point are posted; no repeats.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-33"></a>
### MT-R-33 — Structures in a corporation war

**Suite:** Regression · **Estimate:** 2 SP · **Stories:** [US-03.04](user-stories/US-03.04.md), [US-03.06](user-stories/US-03.06.md)

**Preconditions:** Test channel; bot 2.1.0 running; log shows `Structures dataset loaded`.

**Steps**

1. Pick an active war with a corporation that owns public structures (check its corporation on adam4eve.eu or zKillboard).
2. Re-queue that war, restart, wait one cycle.

**Expected result:** The message has `🏯 Aggressor/Defender structures (N)` fields with types, systems and names; a side without structures shows `none publicly known`. The `Full list on Adam4EVE` link opens the Adam4EVE search for that corporation/alliance.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-34"></a>
### MT-R-34 — Structures in an alliance war

**Suite:** Regression · **Estimate:** 2 SP · **Stories:** [US-03.05](user-stories/US-03.05.md)

**Preconditions:** As MT-R-33.

**Steps**

1. Re-queue an active war against an alliance with several corporations, restart, wait one cycle.

**Expected result:** The defender field counts structures of all member corporations; each listed structure names its owner corporation.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______

<a id="mt-r-35"></a>
### MT-R-35 — Structures dataset unavailable / disabled

**Suite:** Regression · **Estimate:** 2 SP · **Stories:** [US-03.06](user-stories/US-03.06.md)

**Preconditions:** Test copy of the bot.

**Steps**

1. Set `structures.source_url` to `https://data.everef.net/does-not-exist.json`, delete the volume data of a test copy (fresh database), restart, re-queue one war.
2. Restore the URL; then set `structures.enabled: false`, restart, re-queue one war.

**Expected result:** First: warning `Structures dataset not updated`, the war is posted without structures fields. Disabled: no download in the log, no structures fields.

**Result:** ☐ Pass ☐ Fail · Date: ______ · Tester: ______ · Notes: ______
