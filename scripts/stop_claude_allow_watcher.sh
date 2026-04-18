#!/bin/bash
set -euo pipefail

LAUNCH_AGENT_ID="com.omoromachi.claude-allow-watcher"
LAUNCH_AGENT_FILE="$HOME/Library/LaunchAgents/$LAUNCH_AGENT_ID.plist"
USER_ID="$(id -u)"

if launchctl bootout "gui/$USER_ID/$LAUNCH_AGENT_ID" >/dev/null 2>&1; then
  echo "Stopped Claude allow watcher."
else
  echo "Claude allow watcher was not running."
fi

rm -f "$LAUNCH_AGENT_FILE"
