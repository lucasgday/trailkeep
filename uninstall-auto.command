#!/usr/bin/env bash
# uninstall-auto.command
# Removes the daily automatic backup (launchd on macOS, cron on Linux).
# Double-click to uninstall.

LABEL="com.trailkeep.backup"
OS="$(uname -s)"

echo "== Uninstall automatic backup =="
if [ "$OS" = "Darwin" ]; then
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
  if [ -f "$PLIST" ]; then
    launchctl unload "$PLIST" 2>/dev/null
    rm -f "$PLIST"
    echo "✓ Uninstalled (launchd). The backup no longer runs on its own."
    echo "  (You can still run it by hand with update-backup.command whenever you want.)"
  else
    echo "It wasn't installed (couldn't find $PLIST)."
  fi
else
  MARKER="# $LABEL"
  if command -v crontab >/dev/null 2>&1 && crontab -l 2>/dev/null | grep -qF "$MARKER"; then
    crontab -l 2>/dev/null | grep -vF "$MARKER" | crontab -
    echo "✓ Uninstalled (cron). The backup no longer runs on its own."
    echo "  (You can still run it by hand: ./update-backup.sh)"
  else
    echo "It wasn't installed (no trailkeep cron entry found)."
  fi
fi
echo ""
read -r -p "Done. Press Enter to close."
