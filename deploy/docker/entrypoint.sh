#!/bin/sh
set -e

mkdir -p "${MEDIA_ROOT:-/data/media}"

python manage.py migrate --noinput

# 1 CPU / 1 GB VPS: 2 workers is the sweet spot; SQLite+WAL handles the
# concurrency (see DATABASES OPTIONS in config/settings.py).
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
