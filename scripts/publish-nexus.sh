#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Build the EVE War Bot image and push it to a Nexus Docker registry.
#
#   cp nexus.env.example nexus.env   # fill in NEXUS_REGISTRY, NEXUS_USER
#   bash scripts/publish-nexus.sh            # tests + build + push
#   bash scripts/publish-nexus.sh --no-tests
#
# Pushes two tags:  <registry>/<name>:<version from app/__init__.py>  and  :latest
# -----------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

RUN_TESTS=1
[[ "${1:-}" == "--no-tests" ]] && RUN_TESTS=0

# shellcheck disable=SC1091
[[ -f nexus.env ]] && set -a && . ./nexus.env && set +a

: "${NEXUS_REGISTRY:?Set NEXUS_REGISTRY in nexus.env (e.g. nexus.example.com:8083)}"
IMAGE_NAME=${IMAGE_NAME:-eve-war-bot}
PLATFORM=${PLATFORM:-linux/amd64}
REGISTRY=${NEXUS_REGISTRY%/}
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' app/__init__.py)
IMAGE="$REGISTRY/$IMAGE_NAME"

echo "==> Image:    $IMAGE:$VERSION  (+ :latest)"
echo "==> Platform: $PLATFORM"

if [[ $RUN_TESTS == 1 ]]; then
  if command -v python3 >/dev/null && python3 -c "import pytest" 2>/dev/null; then
    echo "==> Running tests"; python3 -m pytest -q
  else
    echo "==> pytest not installed - skipping tests (pip install -r requirements.txt pytest)"
  fi
fi

echo "==> Logging in to $REGISTRY"
if [[ -n "${NEXUS_USER:-}" && -n "${NEXUS_PASSWORD:-}" ]]; then
  printf '%s' "$NEXUS_PASSWORD" | docker login "${REGISTRY%%/*}" -u "$NEXUS_USER" --password-stdin
elif [[ -n "${NEXUS_USER:-}" ]]; then
  docker login "${REGISTRY%%/*}" -u "$NEXUS_USER"
else
  docker login "${REGISTRY%%/*}"
fi

echo "==> Building and pushing"
docker buildx build \
  --platform "$PLATFORM" \
  --build-arg "EVE_BOT_IMAGE_REF=$IMAGE:latest" \
  --label "org.opencontainers.image.version=$VERSION" \
  -t "$IMAGE:$VERSION" -t "$IMAGE:latest" \
  --push .

cat <<EOF

==> Done. On the Linux server run (one time):

  docker login ${REGISTRY%%/*}
  mkdir -p ~/eve-war-bot && cd ~/eve-war-bot
  docker run --rm --user "\$(id -u):\$(id -g)" -v "\$PWD:/out" $IMAGE:latest install
  nano config/credentials.json
  bash scripts/bot.sh start

Later updates on the server:  bash scripts/bot.sh update
EOF
