#!/usr/bin/env bash
# Nightly backup of the domiqgo Docker stack to Yandex Disk (WebDAV).
#
# What it saves: an online-safe SQLite snapshot + the whole media/ directory
# (receipts, rental agreements), packed as domiqgo-YYYY-MM-DD_HHMM.tar.gz.
#
# Setup (once):
#   1. Create an app password: id.yandex.ru -> Безопасность ->
#      Пароли приложений -> «Файлы (WebDAV)».
#   2. cp deploy/.backup.env.example /srv/domiqgo/.backup.env
#      chmod 600 /srv/domiqgo/.backup.env   # holds the password
#      nano /srv/domiqgo/.backup.env
#   3. Test run:  /srv/domiqgo/deploy/backup-yadisk.sh
#   4. Cron (daily at 03:00):
#      crontab -e
#      0 3 * * * /srv/domiqgo/deploy/backup-yadisk.sh >> /var/log/domiqgo-backup.log 2>&1
#
# Restore: use deploy/restore-yadisk.sh (lists backups, verifies integrity,
# keeps a pre-restore safety copy, swaps db+media with the site stopped).

set -euo pipefail

APP_DIR="${APP_DIR:-/srv/domiqgo}"
ENV_FILE="$APP_DIR/.backup.env"
REMOTE_DIR="domiqgo-backups"
WEBDAV="https://webdav.yandex.ru"

[ -f "$ENV_FILE" ] || { echo "ERROR: $ENV_FILE not found (see header of this script)"; exit 1; }
# shellcheck disable=SC1090
. "$ENV_FILE"
: "${YADISK_USER:?set YADISK_USER in .backup.env}"
: "${YADISK_APP_PASSWORD:?set YADISK_APP_PASSWORD in .backup.env}"
KEEP="${KEEP:-14}"   # how many newest archives to keep on the Disk

AUTH="$YADISK_USER:$YADISK_APP_PASSWORD"
STAMP="$(date +%F_%H%M)"
NAME="domiqgo-$STAMP.tar.gz"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cd "$APP_DIR"

# 1. Online-safe DB snapshot: sqlite3 backup API works while the site is live.
docker compose exec -T web python - <<'PY'
import sqlite3
src = sqlite3.connect("/data/db.sqlite3")
dst = sqlite3.connect("/data/backup-tmp.sqlite3")
with dst:
    src.backup(dst)
dst.close(); src.close()
PY
docker compose cp web:/data/backup-tmp.sqlite3 "$TMP/db.sqlite3" >/dev/null
docker compose exec -T web rm -f /data/backup-tmp.sqlite3

# 2. Media (receipts, agreements).
docker compose cp web:/data/media "$TMP/media" >/dev/null 2>&1 || mkdir -p "$TMP/media"

# 3. Pack.
tar -czf "$TMP/$NAME" -C "$TMP" db.sqlite3 media

# 4. Upload. MKCOL is idempotent-ish: 201 = created, 405 = already exists.
code=$(curl -s -o /dev/null -w "%{http_code}" -X MKCOL -u "$AUTH" "$WEBDAV/$REMOTE_DIR")
case "$code" in 201|405) ;; *) echo "ERROR: MKCOL $REMOTE_DIR -> HTTP $code"; exit 1;; esac

curl -sf -T "$TMP/$NAME" -u "$AUTH" "$WEBDAV/$REMOTE_DIR/$NAME"

# 5. Verify the upload landed (HEAD must return 200 with a size).
curl -sf -o /dev/null -I -u "$AUTH" "$WEBDAV/$REMOTE_DIR/$NAME"

# 6. Retention: keep the newest $KEEP archives, delete the rest.
old=$(curl -sf -X PROPFIND -H "Depth: 1" -u "$AUTH" "$WEBDAV/$REMOTE_DIR" \
      | grep -oE 'domiqgo-[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{4}\.tar\.gz' \
      | sort -u | head -n -"$KEEP" || true)
for f in $old; do
    curl -sf -X DELETE -u "$AUTH" "$WEBDAV/$REMOTE_DIR/$f" \
        && echo "pruned: $f" || echo "WARN: failed to prune $f"
done

echo "OK: $NAME uploaded to Yandex Disk ($REMOTE_DIR), keeping last $KEEP"
