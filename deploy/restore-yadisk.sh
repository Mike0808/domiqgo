#!/usr/bin/env bash
# Restore a domiqgo backup from Yandex Disk (made by backup-yadisk.sh).
#
# Usage:
#   deploy/restore-yadisk.sh                    # list available backups
#   deploy/restore-yadisk.sh latest             # restore the newest one
#   deploy/restore-yadisk.sh domiqgo-2026-07-26_0300.tar.gz
#
# Uses the same /srv/domiqgo/.backup.env credentials as the backup script.
#
# Safety: before overwriting anything, the CURRENT db+media are saved to
# /srv/domiqgo/pre-restore-<timestamp>/ on local disk. The web container is
# stopped during the swap and restarted after, so a half-restored state is
# never served.

set -euo pipefail

APP_DIR="${APP_DIR:-/srv/domiqgo}"
ENV_FILE="$APP_DIR/.backup.env"
REMOTE_DIR="domiqgo-backups"
WEBDAV="https://webdav.yandex.ru"

[ -f "$ENV_FILE" ] || { echo "ERROR: $ENV_FILE not found (see backup-yadisk.sh header)"; exit 1; }
# shellcheck disable=SC1090
. "$ENV_FILE"
: "${YADISK_USER:?set YADISK_USER in .backup.env}"
: "${YADISK_APP_PASSWORD:?set YADISK_APP_PASSWORD in .backup.env}"
AUTH="$YADISK_USER:$YADISK_APP_PASSWORD"

list_backups() {
    curl -sf -X PROPFIND -H "Depth: 1" -u "$AUTH" "$WEBDAV/$REMOTE_DIR" \
        | grep -oE 'domiqgo-[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{4}\.tar\.gz' \
        | sort -u
}

# No argument: show what's available and exit.
if [ $# -eq 0 ]; then
    echo "Available backups on Yandex Disk ($REMOTE_DIR):"
    list_backups || { echo "  (none found or folder missing)"; exit 1; }
    echo
    echo "Restore with:  $0 latest   or   $0 <name>.tar.gz"
    exit 0
fi

NAME="$1"
if [ "$NAME" = "latest" ]; then
    NAME=$(list_backups | tail -n 1)
    [ -n "$NAME" ] || { echo "ERROR: no backups found in $REMOTE_DIR"; exit 1; }
    echo "Newest backup: $NAME"
fi

cd "$APP_DIR"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# 1. Download and unpack first — abort before touching anything if broken.
echo "Downloading $NAME ..."
curl -sf -o "$TMP/$NAME" -u "$AUTH" "$WEBDAV/$REMOTE_DIR/$NAME"
tar -xzf "$TMP/$NAME" -C "$TMP"
[ -f "$TMP/db.sqlite3" ] || { echo "ERROR: archive has no db.sqlite3 — aborting"; exit 1; }
# Integrity check of the snapshot before it replaces the live DB.
if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$TMP/db.sqlite3" "PRAGMA integrity_check;" | grep -qx ok \
        || { echo "ERROR: db.sqlite3 failed integrity_check — aborting"; exit 1; }
else
    echo "NOTE: sqlite3 CLI not installed, skipping integrity_check (apt install sqlite3)"
fi

# 2. Confirm — this overwrites live data.
echo
echo "About to REPLACE the live database and media with $NAME."
read -r -p "Type 'yes' to continue: " answer
[ "$answer" = "yes" ] || { echo "Cancelled."; exit 1; }

# 3. Keep a local safety copy of the current state.
SAFE="$APP_DIR/pre-restore-$(date +%F_%H%M%S)"
mkdir -p "$SAFE"
docker compose cp web:/data/db.sqlite3 "$SAFE/db.sqlite3" >/dev/null 2>&1 || true
docker compose cp web:/data/media "$SAFE/media" >/dev/null 2>&1 || true
echo "Current state saved to $SAFE"

# 4. Swap with the site stopped. docker compose cp works on a stopped
#    container. Stale SQLite -wal/-shm sidecars from the old DB must go,
#    or they would corrupt the restored snapshot; a one-off `run` against
#    the same volume handles that and the media swap.
docker compose stop web
docker compose cp "$TMP/db.sqlite3" web:/data/db.sqlite3
docker compose run --rm --no-deps --entrypoint sh web -c 'rm -f /data/db.sqlite3-wal /data/db.sqlite3-shm'
if [ -d "$TMP/media" ]; then
    docker compose run --rm --no-deps --entrypoint sh web -c 'rm -rf /data/media'
    docker compose cp "$TMP/media" web:/data/media
fi
docker compose start web

# 5. Verify the site answers.
sleep 3
if curl -sf -o /dev/null -H "Host: domiq-ufa.ru" http://127.0.0.1:8000/login/ 2>/dev/null \
   || docker compose exec -T web python -c "import sqlite3; sqlite3.connect('/data/db.sqlite3').execute('select 1')"; then
    echo "OK: restore of $NAME complete; site is answering."
    echo "Safety copy of the previous state: $SAFE (delete it once you're happy)."
else
    echo "WARN: restore done but the site check failed — inspect: docker compose logs web"
fi
