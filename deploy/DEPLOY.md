# EVE War Bot — server quick guide

These files were unpacked from the bot image by the `install` command. Edit only your secrets and settings; everything else is managed for you.

| File | You edit it? | Purpose |
|---|---|---|
| `config/credentials.json` | **yes** | Discord webhook URL, optional role ID to ping, your e-mail for ESI (`esi.contact`) |
| `config/config.yaml` | optional | interval, filters, war report, banner … |
| `.env` | rarely | which image to run (`EVE_BOT_IMAGE=…`), e.g. pin a version |
| `docker-compose.yml`, `scripts/`, `DEPLOY.md` | no | refreshed by `bash scripts/bot.sh update` |

## First start

```bash
nano config/credentials.json     # paste the Discord webhook URL; Ctrl+O, Enter, Ctrl+X
bash scripts/bot.sh check        # "Configuration OK"
bash scripts/bot.sh test         # dry run: shows the messages, posts nothing
bash scripts/bot.sh start        # runs in the background, restarts by itself
bash scripts/bot.sh logs         # Ctrl+C to leave the log
```

On the first start the wars currently listed are stored silently. After that, only new wars are posted.

## Every day

| Task | Command |
|---|---|
| state, memory, stored wars | `bash scripts/bot.sh status` |
| log | `bash scripts/bot.sh logs` |
| after editing config/credentials | `bash scripts/bot.sh restart` |
| newest version from the registry | `bash scripts/bot.sh update` |
| backup of the database | `bash scripts/bot.sh backup` |
| stop / start | `bash scripts/bot.sh stop` / `bash scripts/bot.sh start` |

`update` pulls the new image, refreshes `docker-compose.yml` and the scripts from it, and restarts the bot. Your `credentials.json`, `config.yaml`, `.env` and the database are never touched.

## Keeping the secrets file private

`config/credentials.json` must be readable by the bot's container user (uid 10001). By default it is readable by everyone on the server, which is fine for a single-user droplet. To restrict it:

```bash
sudo chown 10001 config/credentials.json && sudo chmod 600 config/credentials.json
```

(Afterwards, edit it with `sudo nano config/credentials.json`.)

## Problems

| Message | Fix |
|---|---|
| `unauthorized` / `no basic auth credentials` on pull | `docker login <registry>` with your Nexus user, then retry |
| `http: server gave HTTP response to HTTPS client` | the Nexus Docker connector is plain HTTP: use HTTPS, or add the registry to `insecure-registries` in `/etc/docker/daemon.json` |
| `Configuration error: ...` | the message names the field; fix `config/credentials.json` |
| `credentials.json is a folder` | `rmdir config/credentials.json`, then run the install command again |
