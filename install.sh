#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PATH="$REPO_DIR/.env"
GATEWAY_PY="$REPO_DIR/cocore_local_gateway.py"
LABEL="com.cocore.local-gateway"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ ! -f "$ENV_PATH" ]]; then
  echo "No .env found. Copy .env.example to .env and edit it first:" >&2
  echo "  cp '$REPO_DIR/.env.example' '$ENV_PATH'" >&2
  exit 1
fi

# shellcheck disable=SC1090
LOG_PATH="$(grep -E '^LOG_PATH=' "$ENV_PATH" | head -1 | cut -d= -f2-)"
LOG_PATH="${LOG_PATH/#\~/$HOME}"
LOG_PATH="${LOG_PATH:-$HOME/.cocore/logs/local-gateway.log}"
mkdir -p "$(dirname "$LOG_PATH")"

mkdir -p "$HOME/Library/LaunchAgents"
sed -e "s#__GATEWAY_PY__#$GATEWAY_PY#g" \
    -e "s#__ENV_PATH__#$ENV_PATH#g" \
    -e "s#__LOG_PATH__#$LOG_PATH#g" \
    "$REPO_DIR/$LABEL.plist.template" > "$PLIST_DEST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"
echo "Loaded $LABEL. Logs: $LOG_PATH"
