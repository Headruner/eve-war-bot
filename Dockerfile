# ---- EVE War Bot ---------------------------------------------------------
# Small single-stage image: python slim + 4 dependencies (~150-200 MB).
# The image also carries a deployment bundle (compose file, config templates,
# scripts), unpacked on a server with:  docker run ... <image> install
FROM python:3.12-slim

# Full reference the server should run, e.g. nexus.example.com:8083/eve-war-bot:latest
# (written into .env by the install command). Set by scripts/publish-nexus.*
ARG EVE_BOT_IMAGE_REF=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # fewer glibc malloc arenas -> lower resident memory for a mostly idle process
    MALLOC_ARENA_MAX=2 \
    CONFIG_FILE=/app/config/config.yaml \
    CREDENTIALS_FILE=/app/config/credentials.json \
    EVE_BOT_IMAGE_REF=${EVE_BOT_IMAGE_REF}

# DejaVu font for the "A VS D" banner text
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ ./app/
COPY config/config.yaml ./config/config.yaml

# deployment bundle for "install"
COPY deploy/docker-compose.yml deploy/DEPLOY.md ./deploy/
COPY config/config.yaml config/credentials.example.json ./deploy/config/
COPY scripts/bot.sh scripts/setup-droplet.sh ./deploy/scripts/

# pre-compile bytecode at build time (the container filesystem is read-only at runtime)
RUN python -m compileall -q /app/app

# Non-root user; /data is the persistent volume (SQLite + heartbeat)
RUN useradd --uid 10001 --create-home bot \
 && mkdir -p /data && chown -R bot:bot /data
USER bot
VOLUME ["/data"]

HEALTHCHECK --interval=5m --timeout=10s --start-period=2m --retries=2 \
  CMD python -m app.healthcheck || exit 1

LABEL org.opencontainers.image.title="eve-war-bot" \
      org.opencontainers.image.description="EVE Online war declarations (DOTLAN + ESI) to Discord"

ENTRYPOINT ["python", "-m", "app.main"]
