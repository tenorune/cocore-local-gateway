#!/usr/bin/env bash
set -euo pipefail
LABEL="com.cocore.local-gateway"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST_DEST"
echo "Unloaded and removed $LABEL."
