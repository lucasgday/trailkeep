#!/usr/bin/env bash
# install-auto.command
# Installs (or reinstalls) the daily automatic backup.
#   macOS → a launchd agent.   Linux → a cron entry.
# Double-click to install at the default time (12:00). Or run from the terminal
# with a time and optional backup folder:
#   ./install-auto.command 22 ~/my-backups
# The backup folder defaults to ~/trailkeep-backups and is remembered locally.

cd "$(dirname "$0")" || exit 1
APP_DIR="$(pwd)"
SCRIPT="$APP_DIR/update-backup.sh"
LABEL="com.trailkeep.backup"
OS="$(uname -s)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
CONFIG_DIR="$CONFIG_HOME/trailkeep"
BACKUP_DIR_FILE="$CONFIG_DIR/backup_dir"

# ---------- pick the time (default 12:00) ----------
HOUR=12; MIN=0
case "${1:-}" in
  -h|--help)
    echo "Usage: install-auto.command [HH | HH:MM] [OUTPUT_DIR]"
    echo "Defaults: 12:00 and ~/trailkeep-backups"
    echo "Examples: install-auto.command 22   |   install-auto.command 7:30 ~/my-backups"
    exit 0;;
  "") ;;  # no argument -> default 12:00
  *)
    if [[ "$1" =~ ^([0-9]{1,2})(:([0-9]{1,2}))?$ ]]; then
      HOUR=$((10#${BASH_REMATCH[1]})); MIN=$((10#${BASH_REMATCH[3]:-0}))
    else
      echo "Invalid time: '$1'. Use HH or HH:MM (24h), e.g. 22 or 7:30."
      read -r -p "Press Enter to close."; exit 1
    fi
    if (( HOUR > 23 || MIN > 59 )); then
      echo "Out-of-range time: '$1'. Hour 0-23, minute 0-59."
      read -r -p "Press Enter to close."; exit 1
    fi;;
esac
HHMM=$(printf "%02d:%02d" "$HOUR" "$MIN")
REMEMBERED=""
if [ -f "$BACKUP_DIR_FILE" ]; then IFS= read -r REMEMBERED < "$BACKUP_DIR_FILE" || REMEMBERED=""; fi
LEGACY_BACKUP_DIR=""
if [ -z "$REMEMBERED" ] && [ -z "${TRAILKEEP_BACKUP_DIR:-}" ] && [ -z "${2:-}" ]; then
  for legacy_dir in "$APP_DIR"/markdown-*; do
    if [ -d "$legacy_dir" ]; then LEGACY_BACKUP_DIR="$APP_DIR"; break; fi
  done
fi
BACKUP_DIR="${2:-${TRAILKEEP_BACKUP_DIR:-${REMEMBERED:-${LEGACY_BACKUP_DIR:-$HOME/trailkeep-backups}}}}"
mkdir -p "$BACKUP_DIR/.sync-state" || { echo "ERROR: can't create backup folder: $BACKUP_DIR"; exit 1; }
BACKUP_DIR="$(cd "$BACKUP_DIR" && pwd)"
mkdir -p "$CONFIG_DIR"
CONFIG_TMP="$BACKUP_DIR_FILE.tmp.$$"
if ! { printf '%s\n' "$BACKUP_DIR" > "$CONFIG_TMP" && mv "$CONFIG_TMP" "$BACKUP_DIR_FILE"; }; then
  rm -f "$CONFIG_TMP"
  echo "ERROR: couldn't remember backup folder in $BACKUP_DIR_FILE"
  exit 1
fi

echo "== Install daily automatic backup ($HHMM) =="
echo "Backup folder: $BACKUP_DIR"
echo "Remembered in: $BACKUP_DIR_FILE"
[ -n "$LEGACY_BACKUP_DIR" ] && echo "Existing repo-local backups detected; keeping their legacy location."

if [ ! -f "$SCRIPT" ]; then
  echo "ERROR: can't find update-backup.sh in this folder."
  read -r -p "Press Enter to close."; exit 1
fi
chmod +x "$SCRIPT"

if [ "$OS" = "Darwin" ]; then
  # ---------- macOS: launchd ----------
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  # RunAtLoad=false so it doesn't run on install; StartCalendarInterval = chosen time.
  cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$SCRIPT</string>
        <string>$BACKUP_DIR</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>$HOUR</integer>
        <key>Minute</key>
        <integer>$MIN</integer>
    </dict>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$BACKUP_DIR/.sync-state/launchd-out.log</string>
    <key>StandardErrorPath</key>
    <string>$BACKUP_DIR/.sync-state/launchd-err.log</string>
</dict>
</plist>
PLISTEOF
  launchctl unload "$PLIST" 2>/dev/null
  if launchctl load "$PLIST" 2>/dev/null; then
    echo "✓ Installed (launchd). The backup will run every day at $HHMM (or when the Mac wakes up)."
    echo "  To see it: open the viewer and select $BACKUP_DIR, or check $BACKUP_DIR/.sync-state/log.json"
  else
    echo "There was a problem loading the task. macOS may ask for Full Disk Access."
    echo "System Settings → Privacy & Security → Full Disk Access → add 'bash' or Terminal."
    exit 1
  fi
else
  # ---------- Linux: cron ----------
  if ! command -v crontab >/dev/null 2>&1; then
    echo "ERROR: 'crontab' not found. Install cron (e.g. 'sudo apt install cron'),"
    echo "or add this line to your scheduler manually:"
    echo "  $MIN $HOUR * * * /bin/bash \"$SCRIPT\" \"$BACKUP_DIR\"  # $LABEL"
    exit 1
  fi
  MARKER="# $LABEL"
  CRONLINE="$MIN $HOUR * * * /bin/bash \"$SCRIPT\" \"$BACKUP_DIR\" >> \"$BACKUP_DIR/.sync-state/cron.log\" 2>&1  $MARKER"
  # replace any previous trailkeep line, then add the new one
  ( crontab -l 2>/dev/null | grep -vF "$MARKER"; echo "$CRONLINE" ) | crontab -
  echo "✓ Installed (cron). The backup will run every day at $HHMM."
  echo "  Note: unlike macOS, cron does NOT catch up missed runs while the machine is off."
  echo "  To see it: open the viewer and select $BACKUP_DIR, or check $BACKUP_DIR/.sync-state/log.json"
fi
echo ""
if [ -t 0 ]; then read -r -p "Done. Press Enter to close."; else echo "Done."; fi
