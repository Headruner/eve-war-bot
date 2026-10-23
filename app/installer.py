"""`install` command: unpacks the deployment bundle that ships inside the image.

On the server:
    mkdir eve-war-bot && cd eve-war-bot
    docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/out" <registry>/eve-war-bot:latest install

This writes everything needed to run the bot next to you:
    docker-compose.yml, .env (image reference), config/config.yaml,
    config/credentials.json (empty template), scripts/bot.sh, DEPLOY.md

Your own files are never overwritten: config/config.yaml, config/credentials.json
and .env are only created when missing. With --force, the managed files
(docker-compose.yml, scripts, DEPLOY.md, credentials.example.json) are refreshed.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

BUNDLE = Path(os.getenv("EVE_BOT_BUNDLE", "/app/deploy"))

# refreshed on --force (the app owns them)
MANAGED = ["docker-compose.yml", "DEPLOY.md", "config/credentials.example.json",
           "scripts/bot.sh", "scripts/setup-droplet.sh"]
# the user owns them - created once, never overwritten
USER_OWNED = ["config/config.yaml"]
EXECUTABLE = {"scripts/bot.sh", "scripts/setup-droplet.sh"}


def _copy(rel: str, out: Path, overwrite: bool, done: list[str]) -> None:
    src, dst = BUNDLE / rel, out / rel
    if not src.exists():
        return
    if dst.is_dir():
        raise SystemExit(f"{dst} is a folder - remove it and run install again.")
    if dst.exists() and not overwrite:
        done.append(f"  kept     {rel}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    if rel in EXECUTABLE:
        dst.chmod(0o755)
    done.append(f"  written  {rel}")


def install(out_dir: str = "/out", force: bool = False) -> int:
    out = Path(out_dir)
    if not out.is_dir():
        print(f"Target folder {out} not found. Mount one: -v \"$PWD:/out\"", file=sys.stderr)
        return 2
    if not os.access(out, os.W_OK):
        print(f"Cannot write to {out}. Add  --user \"$(id -u):$(id -g)\"  to docker run.",
              file=sys.stderr)
        return 2
    if not BUNDLE.is_dir():
        print(f"Deployment bundle missing in image ({BUNDLE}).", file=sys.stderr)
        return 2

    done: list[str] = []
    for rel in MANAGED:
        _copy(rel, out, overwrite=force, done=done)
    for rel in USER_OWNED:
        _copy(rel, out, overwrite=False, done=done)

    # secrets file: empty template, created once
    creds = out / "config/credentials.json"
    if creds.is_dir():
        raise SystemExit(f"{creds} is a folder - remove it and run install again.")
    if not creds.exists():
        shutil.copyfile(BUNDLE / "config/credentials.example.json", creds)
        # readable by the container user (uid 10001); for stricter permissions see DEPLOY.md
        creds.chmod(0o644)
        done.append("  written  config/credentials.json   <- put your secrets here")
    else:
        done.append("  kept     config/credentials.json")

    # .env: which image docker compose should run
    env = out / ".env"
    image_ref = os.getenv("EVE_BOT_IMAGE_REF", "").strip()
    if not env.exists():
        env.write_text(
            "# Image that docker compose runs. Pin a version instead of :latest if you like.\n"
            f"EVE_BOT_IMAGE={image_ref or 'CHANGE-ME/eve-war-bot:latest'}\n", encoding="utf-8")
        done.append("  written  .env")
    else:
        done.append("  kept     .env")

    print("EVE War Bot deployment files:\n" + "\n".join(done))
    print("""
Next steps:
  1. nano config/credentials.json      (Discord webhook URL, optional role id, contact)
  2. bash scripts/bot.sh check         (validates the files)
  3. bash scripts/bot.sh start         (pulls the image and starts the bot)
  More: DEPLOY.md""")
    if not image_ref:
        print("\nNOTE: this image was built without EVE_BOT_IMAGE_REF - edit .env first.")
    return 0
