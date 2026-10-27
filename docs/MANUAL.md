# EVE War Bot — Step-by-Step Manual (no experience needed)

This guide takes you from nothing to a running bot that posts new EVE Online war declarations into your Discord channel. You only copy and paste commands. It takes about **30 minutes**.

> **How to read this guide**
> - Grey boxes like the one below are **commands**. Copy the whole box, paste it into the terminal, and press **Enter**.
>   ```bash
>   echo "hello"
>   ```
> - Text in `<angle brackets>` is a placeholder. Replace it with your own value **and** remove the brackets.
> - ✅ marks what you should see when a step worked.

---

## 0. What you need

| You need | Why |
|---|---|
| A **Discord server** where you are admin (or have *Manage Webhooks*) | the bot posts there |
| A **DigitalOcean** account | rents the small Linux server (a "droplet") the bot runs on |
| Access to the **GitHub repository** `Headruner/eve-war-bot` | it holds the bot's code |
| A computer with a terminal: **Windows** → *Terminal* or *PowerShell* · **macOS** → *Terminal* | to connect to the server |

You don't need to install anything on your own computer.

---

## 1. Create the Discord webhook (the bot's "mailbox")

1. In Discord, hover over the channel where wars should appear → click the **⚙ gear** (*Edit Channel*).
2. Open **Integrations** → **Webhooks** → **New Webhook**.
3. Give it a name (e.g. `EVE War Watch`) and, if you like, a picture.
4. Click **Copy Webhook URL**. Paste it into a notepad for now. It looks like this:
   `https://discord.com/api/webhooks/1234567890/AbCdEf...`

> ⚠️ Treat this URL like a password. Anyone who has it can post in your channel.

**Optional — ping a role on every war:** turn on *User Settings → Advanced → Developer Mode*, then go to *Server Settings → Roles*, right-click the role → **Copy Role ID**, and keep that number too.

---

## 2. Create the server (droplet)

> **Already have a server** (for example one that runs other apps)? Skip this step and go to step 3. The setup script in step 4.2 only adds what is missing. It does not touch your firewall or restart your other apps.

1. Log in at **cloud.digitalocean.com** → **Create** → **Droplets**.
2. **Region:** any. One close to you is fine (e.g. Frankfurt or Amsterdam).
3. **Image:** **Ubuntu 24.04 (LTS) x64**.
4. **Size:** *Basic* → *Regular* → the smallest **1 GB RAM** plan. That is enough; the bot uses less than 100 MB.
5. **Authentication:**
   - **SSH key** (more secure). Click *New SSH Key* and follow DigitalOcean's on-screen help, **or**
   - **Password** (easier). Choose a long password and save it in your password manager.
6. **Hostname:** `eve-war-bot`.
7. Click **Create Droplet** and wait about a minute.
8. Copy the droplet's **IPv4 address** (e.g. `164.90.1.2`).

---

## 3. Connect to the server

Open *Terminal* (Windows: *Terminal* / *PowerShell*; macOS: *Terminal*) and type:

```bash
ssh root@<your-droplet-IP>
```

- If it asks *"Are you sure you want to continue connecting?"* → type `yes` and press Enter.
- If you chose a password, type it now. **Nothing appears while you type** — that is normal. Press Enter.

✅ The prompt changes to something like `root@eve-war-bot:~#`. You are now on the server.

> No terminal at hand? In DigitalOcean, open the droplet → **Access** → **Launch Droplet Console**. A terminal opens in your browser.

---

## 4. Prepare the server (one command)

First download the code (step 4.1), then run the setup script (step 4.2).

### 4.1 Download the code

The repository is private, so GitHub needs a **token** (a one-time password made for one purpose):

1. On github.com: your avatar → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
2. Name: `droplet-read`. Expiration: e.g. 1 year. **Repository access:** *Only select repositories* → `eve-war-bot`.
3. **Permissions** → *Repository permissions* → **Contents: Read-only**. Leave everything else as it is.
4. **Generate token** and copy it (it starts with `github_pat_`).

On the server:

```bash
apt-get -o DPkg::Lock::Timeout=600 update && apt-get -o DPkg::Lock::Timeout=600 install -y git
git clone https://github.com/Headruner/eve-war-bot.git
cd eve-war-bot
```

> `DPkg::Lock::Timeout=600` lets apt wait up to 10 minutes if Ubuntu's automatic updates are running at that moment, instead of failing with `Could not get lock /var/lib/apt/lists/lock`.

When it asks for **Username**, type your GitHub user name. For **Password**, paste the **token** (again, nothing is shown while you type).

✅ You see `Cloning into 'eve-war-bot'... done.`

### 4.2 Run the setup script

```bash
sudo bash scripts/setup-droplet.sh
```

It takes 2–5 minutes. It only **adds what is missing**: a few tools, 1 GB of **swap** (emergency memory for a 1 GB server) if the server has none, and **Docker** if it isn't installed yet. It does **not** touch the firewall or open ports, and it doesn't restart anything that is already running, so other apps on the same server are not affected. Add `--upgrade` at the end if you also want all system packages updated.

✅ At the end you see green `==> Done.` and a memory table where the **Swap** line is not `0B`.

---

## 5. Enter your Discord details

```bash
bash scripts/bot.sh init
nano config/credentials.json
```

An editor opens. Fill in the values **between the quotes**:

```json
{
  "discord": {
    "webhook_url": "https://discord.com/api/webhooks/1234567890/AbCdEf...",
    "mention_role_id": ""
  },
  "esi": {
    "contact": "your-mail@example.com"
  }
}
```

| Field | What to enter |
|---|---|
| `webhook_url` | the URL from step 1 (**required**) |
| `mention_role_id` | the role number from step 1, or leave `""` for no ping |
| `contact` | your **e-mail address**. CCP asks every app that uses its EVE Online API (ESI) to send a contact, so they can reach you instead of blocking the bot |

**Saving in nano:** press **Ctrl + O**, then **Enter** (save). Then press **Ctrl + X** (exit).

> Keep the quotes `" "` and commas exactly as they are. A missing quote is the most common mistake.

---

## 6. Check, test, start

### 6.1 Check the settings

```bash
bash scripts/bot.sh check
```

The first run builds the bot's container, which takes 1–3 minutes.
✅ The last line contains `Configuration OK`.
❌ `Configuration error: ...` tells you exactly which field is wrong. Fix it with `nano config/credentials.json` and run the check again.

### 6.2 Test run (posts nothing)

```bash
bash scripts/bot.sh test
```

✅ You see `ESI: 2000 war IDs listed, ...`. Lines that start with `[DRY RUN] POST` appear only if there are new wars. Those are the messages the bot *would* send. Nothing reaches Discord, and nothing is saved.

### 6.3 Start the bot for real

```bash
bash scripts/bot.sh start
```

✅ You see a table with `eve-war-bot` and `Up`.

> **What happens on the first start:** the bot asks EVE Online's official API (ESI) for the newest war, remembers it, and posts **nothing**, so your channel isn't flooded with old wars. From then on, each **new** war appears in Discord, usually **15–75 minutes** after it was declared. ESI itself only refreshes its war list about once an hour.

### 6.4 Watch it work

```bash
bash scripts/bot.sh logs
```

✅ About every 15 minutes you see a line like `ESI: 2000 war IDs listed, 0 new.` When a new war appears: `Notified war(s) [763600] -> message ...`
Shortly after the start you also see `Structures dataset loaded: N structures with an owner.` (the first download takes up to a few minutes; after that it is refreshed once a day). From then on, every message shows the structures of both sides.
Press **Ctrl + C** to leave the log. The bot keeps running.

**You're done.** You can close the terminal (type `exit`). The bot runs on its own, restarts by itself if it crashes, and starts again automatically when the server reboots.

---

## 7. Everyday tasks

Always run these from the `eve-war-bot` folder: after logging in, type `cd eve-war-bot` first.

| I want to… | Command |
|---|---|
| see whether it's running, memory/CPU, how many wars are stored | `bash scripts/bot.sh status` |
| read the log | `bash scripts/bot.sh logs` (Ctrl + C to leave) |
| change a setting (interval, filters, …) | `nano config/config.yaml`, then `bash scripts/bot.sh restart` |
| change the webhook / role | `nano config/credentials.json`, then `bash scripts/bot.sh restart` |
| install a new version of the bot | `bash scripts/bot.sh update` |
| back up the bot's memory (posted wars) | `bash scripts/bot.sh backup` → file in `backups/` |
| stop the bot | `bash scripts/bot.sh stop` |
| start it again | `bash scripts/bot.sh start` |

**Settings people usually change** (`config/config.yaml`):

| Setting | Meaning |
|---|---|
| `poll_interval_min: 15` | minutes between checks (please don't go below 10) |
| `watch_entity_ids: []` | only wars involving these alliance/corp IDs, e.g. `[99003581, 98230524]` |
| `statuses: [none, open_for_allies, mutual]` | which kinds of wars to post |
| `min_defender_members: 0` | skip wars against tiny defenders |
| `banner_enabled: true` | the "A VS D" picture |
| `structures: enabled: true` | list the publicly known structures (citadels, engineering complexes, refineries) of both sides; `max_listed: 5` = how many are named |
| `live_updates: true` | update the war report (kills, score) in the message every hour |

---

## 8. Option B — don't build on the server (optional)

Normally the server builds the bot itself (steps 6.1/6.3). That's fine for this small bot. If you'd rather have GitHub build it — less work and memory for the droplet — do this:

1. On GitHub, open the repository → **Actions**. After each change pushed to `main`, the workflow *test-and-build* runs and publishes the image `ghcr.io/headruner/eve-war-bot` (GitHub image names are always lowercase).
2. Create a second token like in step 4.1, but under *Personal access tokens* → **Tokens (classic)**, with only the scope **`read:packages`**.
3. On the server:
   ```bash
   echo "<classic-token>" | docker login ghcr.io -u <your-github-user> --password-stdin
   cp .env.example .env
   nano .env        # remove the "# " in front of EVE_BOT_IMAGE=..., save, exit
   bash scripts/bot.sh start
   ```
From now on, `start` and `update` download the ready-made image instead of building it.

---

## 8b. Option C — install from your Nexus (no code on the server)

Use this when someone has already uploaded the bot to your company's **Nexus** (see README → *Delivery through Nexus*). The server then needs **no git and no code**, only Docker and one command.

You need from the Nexus admin: the **registry address** (e.g. `nexus.example.com:8083`), a **user name** and a **password**.

1. Prepare the server as in step 4.2 (tools, swap, Docker — only what is missing). If you don't have the code on the server, ask for the file `setup-droplet.sh`, or install Docker the way your admin recommends.
2. Log in to Nexus once:
   ```bash
   docker login <registry-address>
   ```
   ✅ `Login Succeeded`
3. Create the bot's folder and unpack everything into it (this is the one command):
   ```bash
   mkdir -p ~/eve-war-bot && cd ~/eve-war-bot
   docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/out" <registry-address>/eve-war-bot:latest install
   ```
   ✅ A list of `written ...` files and the next steps.
4. Put in your secrets — exactly as in **step 5** (`nano config/credentials.json`).
5. Check, test and start — exactly as in **step 6** (`bash scripts/bot.sh check`, `test`, `start`).

**Updating later:** `bash scripts/bot.sh update`. It downloads the newest version from Nexus and restarts. Your secrets and settings stay as they are.

---

## 9. Something is wrong?

| What you see | What it means / what to do |
|---|---|
| `Configuration error: 'discord.webhook_url' is empty` | step 5 was skipped or not saved (Ctrl + O, Enter). |
| `Invalid JSON in ...credentials.json` | a quote or comma is missing. Compare with the example in step 5. |
| `config/credentials.json is a FOLDER` | the bot was started before step 5. Run `rmdir config/credentials.json`, then `bash scripts/bot.sh init`, then step 5 again. |
| `Discord webhook rejected (HTTP 401/404)` | the webhook was deleted or copied wrongly. Create a new one (step 1) and put it into `credentials.json`. |
| `status` shows `unhealthy` | the bot hasn't finished a check for over 35 minutes. Look at `bash scripts/bot.sh logs` for the red ERROR lines. Usually ESI or the internet was down, and it fixes itself. |
| `ESI error: ... HTTP 4xx/5xx` | EVE Online's API had a problem (often during the daily server downtime around 11:00 UTC). The bot tries again in the next cycle. If it stays for hours, check [the EVE server status](https://www.eveonline.com/) or send the log to the developer. |
| `No contact in credentials.json` warning | add your e-mail as `esi.contact` (step 5), then `bash scripts/bot.sh restart` |
| `War report for ... unavailable` | CCP's ESI service didn't answer. The war is still posted, and the report is filled in on the next hourly update. |
| No new messages for a long time | that can be normal: some days have few new wars. Check `logs` — the line `ESI: NNNN war IDs listed, 0 new.` means it is working. |
| `unauthorized` or `no basic auth credentials` (Option C) | run `docker login <registry-address>` again with the Nexus user. |
| `server gave HTTP response to HTTPS client` (Option C) | Nexus uses plain HTTP. Ask the admin for HTTPS, or for the `insecure-registries` setting. |
| The setup script seems frozen (no CPU or disk activity) | In a second SSH session run `ps -ef --forest \| grep -B2 -A4 [s]etup-droplet`. A question like `*** <file> (Y/I/N/O/D/Z)` in the first window → type **N** and Enter (keeps your config). `cloud-init status --wait` (old script version) → `sudo pkill -f "cloud-init status --wait"`. Never press Ctrl+C while `dpkg` runs. |
| `Could not get lock /var/lib/apt/lists/lock … held by process … (apt-get)` | another apt run is active: usually Ubuntu's automatic updates, sometimes another installation (or first-boot setup on a new server). See which one with `ps -fp <process number>`. **Don't delete the lock.** Wait until it finishes (`sudo fuser -v /var/lib/dpkg/lock-frontend` shows who holds it), then run the command again. `setup-droplet.sh` waits by itself. |
| `git clone` says *Authentication failed* | use the **token** as the password, not your GitHub password. Check that the token has access to `eve-war-bot`. |
| `Permission denied (publickey)` on `ssh` | you chose an SSH key in step 2 but this computer doesn't have it. Use the **Droplet Console** in the browser instead. |
| You want to start from scratch (the bot forgets all posted wars) | `docker compose down -v`, then `bash scripts/bot.sh start`. ⚠️ This deletes the bot's memory. |

---

## 10. Small glossary

| Word | Meaning |
|---|---|
| **Droplet** | DigitalOcean's name for a rented Linux server |
| **SSH** | the secure way to type commands on that server from your computer |
| **Docker / container** | a sealed box that holds the bot and everything it needs, so it runs the same everywhere |
| **Webhook** | a secret Discord address; whatever is sent to it appears in the channel |
| **Volume** | the bot's permanent storage on the server; it keeps the list of already posted wars, even after restarts |
| **Swap** | disk space used as emergency memory when RAM is full |
| **Token** | a password for one specific purpose that you can revoke at any time |
| **ESI** | EVE Swagger Interface, EVE Online's official API. The bot reads new wars and war reports from it |
| **DOTLAN** | evemaps.dotlan.net, a community website about EVE. Messages link to it, but the bot doesn't read it |
