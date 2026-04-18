#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_FILE="$ROOT_DIR/scripts/claude_allow_watcher.swift"
BUILD_DIR="$ROOT_DIR/output/claude_allow_watcher"
BINARY_FILE="$BUILD_DIR/claude_allow_watcher"
LOG_FILE="/tmp/claude_allow_watcher.log"
ERROR_LOG_FILE="/tmp/claude_allow_watcher.error.log"
LAUNCH_AGENT_ID="com.omoromachi.claude-allow-watcher"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
LAUNCH_AGENT_FILE="$LAUNCH_AGENTS_DIR/$LAUNCH_AGENT_ID.plist"
USER_ID="$(id -u)"

mkdir -p "$BUILD_DIR"
mkdir -p "$LAUNCH_AGENTS_DIR"

if [[ ! -x "$BINARY_FILE" || "$SOURCE_FILE" -nt "$BINARY_FILE" ]]; then
  swiftc -O -framework AppKit -framework ApplicationServices "$SOURCE_FILE" -o "$BINARY_FILE"
fi

cat > "$LAUNCH_AGENT_FILE" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LAUNCH_AGENT_ID</string>
  <key>ProgramArguments</key>
  <array>
    <string>$BINARY_FILE</string>
    <string>--no-prompt</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ProcessType</key>
  <string>Interactive</string>
  <key>StandardOutPath</key>
  <string>$LOG_FILE</string>
  <key>StandardErrorPath</key>
  <string>$ERROR_LOG_FILE</string>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$USER_ID/$LAUNCH_AGENT_ID" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$USER_ID" "$LAUNCH_AGENT_FILE"
launchctl kickstart -k "gui/$USER_ID/$LAUNCH_AGENT_ID"

echo "Started Claude allow watcher via LaunchAgent"
echo "LaunchAgent: $LAUNCH_AGENT_FILE"
echo "Binary: $BINARY_FILE"
echo "Log: $LOG_FILE"
echo "Error log: $ERROR_LOG_FILE"
echo "Stop: $ROOT_DIR/scripts/stop_claude_allow_watcher.sh"
