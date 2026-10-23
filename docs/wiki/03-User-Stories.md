# User stories

[Home](Home.md) › User stories

Every story has its own page. The ID is coded as **`US-<epic>.<number>`**: `US-04.03` is story 3 of epic `EP-04`. Each story belongs to one feature `F-<epic>.<n>` from the [FRD](02-FRD.md).

Status legend: **Done** = implemented in release 1.3.0 · **Planned** = in the backlog. *Field* = observed on a real installation, not only in tests.

## EP-01 War detection

*Find every new war declaration on DOTLAN reliably and exactly once.*

| ID | Story | Feature | Priority | Status | Auto tests | Manual tests | Field |
|---|---|---|---|---|---:|---:|---|
| [US-01.01](user-stories/US-01.01.md) | Scheduled polling of the DOTLAN wars list | F-01.1 | Must | Done | 0 | 2 | ◐ |
| [US-01.02](user-stories/US-01.02.md) | Parse each war row | F-01.2 | Must | Done | 2 | 2 | ◐ |
| [US-01.03](user-stories/US-01.03.md) | Use full entity names | F-01.2 | Should | Done | 1 | 1 | — |
| [US-01.04](user-stories/US-01.04.md) | Notify each war only once | F-01.3 | Must | Done | 1 | 2 | — |
| [US-01.05](user-stories/US-01.05.md) | Silent first run | F-01.4 | Must | Done | 1 | 1 | ✔ |
| [US-01.06](user-stories/US-01.06.md) | Survive DOTLAN layout changes | F-01.5 | Should | Done | 0 | 1 | — |

## EP-02 Discord delivery

*Deliver each new war to the Discord channel, reliably and within rate limits.*

| ID | Story | Feature | Priority | Status | Auto tests | Manual tests | Field |
|---|---|---|---|---|---:|---:|---|
| [US-02.01](user-stories/US-02.01.md) | Post a new war to Discord | F-02.1 | Must | Done | 2 | 2 | — |
| [US-02.02](user-stories/US-02.02.md) | Respect Discord rate limits and retry | F-02.2 | Must | Done | 0 | 1 | — |
| [US-02.03](user-stories/US-02.03.md) | Detect an invalid webhook | F-02.2 | Must | Done | 0 | 1 | — |
| [US-02.04](user-stories/US-02.04.md) | Ping a role for new wars | F-02.3 | Could | Done | 0 | 1 | — |
| [US-02.05](user-stories/US-02.05.md) | Several wars in one message | F-02.4 | Could | Done | 1 | 1 | — |
| [US-02.06](user-stories/US-02.06.md) | Filter which wars are posted | F-02.5 | Should | Done | 1 | 1 | — |

## EP-03 Rich message content

*Make each notification readable at a glance: logos, banner, colours, links.*

| ID | Story | Feature | Priority | Status | Auto tests | Manual tests | Field |
|---|---|---|---|---|---:|---:|---|
| [US-03.01](user-stories/US-03.01.md) | Show alliance/corporation logos | F-03.1 | Must | Done | 1 | 2 | — |
| [US-03.02](user-stories/US-03.02.md) | Attach a VS banner | F-03.2 | Could | Done | 1 | 2 | — |
| [US-03.03](user-stories/US-03.03.md) | Colours, local times and links | F-03.3 | Should | Done | 1 | 2 | — |

## EP-04 War report & live updates

*Show the content of a DOTLAN war report and keep it current while the war runs.*

| ID | Story | Feature | Priority | Status | Auto tests | Manual tests | Field |
|---|---|---|---|---|---:|---:|---|
| [US-04.01](user-stories/US-04.01.md) | War report: timeline, score, allies | F-04.1 | Should | Done | 2 | 2 | — |
| [US-04.02](user-stories/US-04.02.md) | Recent kills and hot systems | F-04.2 | Should | Done | 1 | 1 | — |
| [US-04.03](user-stories/US-04.03.md) | Live updates of the posted message | F-04.3 | Should | Done | 1 | 1 | — |
| [US-04.04](user-stories/US-04.04.md) | Final state when a war ends | F-04.4 | Should | Done | 1 | 1 | — |
| [US-04.05](user-stories/US-04.05.md) | Post even when ESI is down | F-04.1 | Must | Done | 0 | 1 | ◐ |

## EP-05 Configuration & secrets

*Let an operator configure the bot safely without touching code.*

| ID | Story | Feature | Priority | Status | Auto tests | Manual tests | Field |
|---|---|---|---|---|---:|---:|---|
| [US-05.01](user-stories/US-05.01.md) | Credentials in a JSON file with validation | F-05.1 | Must | Done | 1 | 4 | ✔ |
| [US-05.02](user-stories/US-05.02.md) | Settings in a YAML file | F-05.2 | Must | Done | 0 | 1 | — |
| [US-05.03](user-stories/US-05.03.md) | Dry run | F-05.3 | Should | Done | 1 | 2 | ✔ |

## EP-06 Deployment & operations

*Run unattended in Docker on a small or shared Linux server; easy to install, update, revert.*

| ID | Story | Feature | Priority | Status | Auto tests | Manual tests | Field |
|---|---|---|---|---|---:|---:|---|
| [US-06.01](user-stories/US-06.01.md) | Run in a resource-limited, hardened container | F-06.1 | Must | Done | 0 | 2 | ◐ |
| [US-06.02](user-stories/US-06.02.md) | Keep state across restarts | F-06.2 | Must | Done | 1 | 2 | — |
| [US-06.03](user-stories/US-06.03.md) | Health check and log rotation | F-06.3 | Should | Done | 0 | 2 | — |
| [US-06.04](user-stories/US-06.04.md) | Everyday operations with one script | F-06.4 | Should | Done | 0 | 2 | ◐ |
| [US-06.05](user-stories/US-06.05.md) | Safe server setup on an existing server | F-06.5 | Must | Done | 0 | 1 | — |
| [US-06.06](user-stories/US-06.06.md) | Revert an earlier setup run | F-06.5 | Must | Done | 0 | 1 | — |
| [US-06.07](user-stories/US-06.07.md) | Publish the image to Nexus | F-06.6 | Could | Done | 0 | 1 | — |
| [US-06.08](user-stories/US-06.08.md) | One-command install from the image | F-06.6 | Could | Done | 2 | 2 | — |
| [US-06.09](user-stories/US-06.09.md) | Continuous integration | F-06.7 | Could | Done | 0 | 1 | — |

## EP-07 Reporting & statistics

*Provide numbers about war activity and about the bot's own performance.*

| ID | Story | Feature | Priority | Status | Auto tests | Manual tests | Field |
|---|---|---|---|---|---:|---:|---|
| [US-07.01](user-stories/US-07.01.md) | Statistics of wars on the 1st day of each month | F-07.1 | Should | Done | 2 | 1 | — |
| [US-07.02](user-stories/US-07.02.md) | KPI report from the bot database | F-07.2 | Could | Planned | 0 | 0 | — |

## Summary

- Stories: **34** · done: **33** · planned: **1**
- With automated tests: **19** · with manual scenarios: **33**
- Field column: ✔ verified · ◐ partly or simulated · — pending
