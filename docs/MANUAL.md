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
cloud-init status --wait
apt-get -o DPkg::Lock::Timeout=600 update && apt-get -o DPkg::Lock::Timeout=600 install -y git
git clone https://github.com/Headruner/eve-war-bot.git
cd eve-war-bot
```

> The first line waits until the new droplet has finished setting itself up. On a brand-new server Ubuntu installs updates by itself for a few minutes. Without the wait you can get `Could not get lock /var/lib/apt/lists/lock`.

When it asks for **Username**, type your GitHub user name. For **Password**, paste the **token** (again, nothing is shown while you type).

✅ You see `Cloning into 'eve-war-bot'... done.`

### 4.2 Run the setup script

```bash
sudo bash scripts/setup-droplet.sh
```

It takes 2–5 minutes. It updates the system, adds 1 GB of **swap** (emergency memory for a 1 GB server), installs **Docker**, and turns on the **firewall** (only SSH allowed in; the bot doesn't need any open ports).

✅ At the end you see green `==> Done.` and a memory table where the **Swap** line shows `1.0Gi`.

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
  "dotlan": {
    "contact": "your-mail@example.com"
  }
}
```

| Field | What to enter |
|---|---|
| `webhook_url` | the URL from step 1 (**required**) |
| `mention_role_id` | the role number from step 1, or leave `""` for no ping |
| `contact` | your e-mail or Discord name, so the DOTLAN site owner can reach you if needed |

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

✅ You see `Parsed NN wars` and lines that start with `[DRY RUN] POST`. Those are the messages the bot *would* send. Nothing reaches Discord, and nothing is saved.

### 6.3 Start the bot for real

```bash
bash scripts/bot.sh start
```

✅ You see a table with `eve-war-bot` and `Up`.

> **What happens on the first start:** the bot saves all wars **currently** listed as "already known" and posts **nothing**, so your channel isn't flooded with about 60 old wars. From then on, each **new** war appears in Discord within about 15 minutes of showing up on DOTLAN.

### 6.4 Watch it work

```bash
bash scripts/bot.sh logs
```

✅ About every 15 minutes you see a line like `Parsed 59 wars, 0 new.` When a new war appears: `Notified war(s) [763600] -> message ...`
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

1. Prepare the server as in step 4.2 (Docker, swap, firewall). If you don't have the code on the server, ask for the file `setup-droplet.sh`, or install Docker the way your admin recommends.
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
| `status` shows `unhealthy` | the bot hasn't finished a check for over 35 minutes. Look at `bash scripts/bot.sh logs` for the red ERROR lines. Usually DOTLAN or the internet was down, and it fixes itself. |
| `Scrape error: No war rows found` | DOTLAN changed its web page. The code needs an update; send the log to the developer. |
| `War report for ... unavailable` | CCP's ESI service didn't answer. The war is still posted, and the report is filled in on the next hourly update. |
| No new messages for a long time | that can be normal: some days have few new wars. Check `logs` — the line `Parsed NN wars, 0 new.` means it is working. |
| `unauthorized` or `no basic auth credentials` (Option C) | run `docker login <registry-address>` again with the Nexus user. |
| `server gave HTTP response to HTTPS client` (Option C) | Nexus uses plain HTTP. Ask the admin for HTTPS, or for the `insecure-registries` setting. |
| `Could not get lock /var/lib/apt/lists/lock … held by process … (apt-get)` | Ubuntu is installing its own updates (normal on a new droplet). **Don't delete the lock.** Wait with `cloud-init status --wait`, then run the command again. `setup-droplet.sh` waits by itself. |
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
| **DOTLAN** | evemaps.dotlan.net, the website where the bot reads new wars |
| **ESI** | CCP's official EVE Online API; the bot gets the war report (kills, allies, score) from it |
