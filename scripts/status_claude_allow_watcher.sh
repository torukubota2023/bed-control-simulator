#!/bin/bash
set -euo pipefail

LAUNCH_AGENT_ID="com.omoromachi.claude-allow-watcher"
USER_ID="$(id -u)"
LOG_FILE="/tmp/claude_allow_watcher.log"
ERROR_LOG_FILE="/tmp/claude_allow_watcher.error.log"
BINARY_FILE="$(cd "$(dirname "$0")/.." && pwd)/output/claude_allow_watcher/claude_allow_watcher"

if launchctl print "gui/$USER_ID/$LAUNCH_AGENT_ID" >/tmp/claude_allow_watcher.status 2>/dev/null; then
  RUNNING="yes"
  PID="$(awk '/pid = / {print $3; exit}' /tmp/claude_allow_watcher.status)"
else
  RUNNING="no"
  PID="-"
fi

ACCESSIBILITY="$(swift -e 'import ApplicationServices; print(AXIsProcessTrusted())' 2>/dev/null || echo unknown)"
PROBE_LOG="$(mktemp)"
PROBE_RESULT="unknown"

"$BINARY_FILE" --once --no-prompt >"$PROBE_LOG" 2>&1 &
PROBE_PID=$!
sleep 2

if kill -0 "$PROBE_PID" 2>/dev/null; then
  kill "$PROBE_PID" 2>/dev/null || true
  wait "$PROBE_PID" 2>/dev/null || true
  PROBE_RESULT="not_ready_or_blocked"
else
  wait "$PROBE_PID" 2>/dev/null || true
  if rg -q "accessibility ready" "$PROBE_LOG"; then
    PROBE_RESULT="ready"
  else
    PROBE_RESULT="completed_without_ready_marker"
  fi
fi

echo "Claude allow watcher status"
echo "running: $RUNNING"
echo "pid: $PID"
echo "accessibility_trusted: $ACCESSIBILITY"
echo "binary_probe: $PROBE_RESULT"
echo "binary: $BINARY_FILE"
echo "log: $LOG_FILE"
echo "error_log: $ERROR_LOG_FILE"
echo
echo "recent log:"
tail -10 "$LOG_FILE" 2>/dev/null || true
echo
echo "recent error log:"
tail -10 "$ERROR_LOG_FILE" 2>/dev/null || true

rm -f /tmp/claude_allow_watcher.status
rm -f "$PROBE_LOG"
