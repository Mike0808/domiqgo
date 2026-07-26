# Deployment — domiq-ufa.ru

MVP target: a 1 CPU / 1 GB RAM / 15 GB NVMe VPS. The stack is Docker Compose,
SQLite (WAL) as the database, and Caddy for automatic Let's Encrypt TLS.

```
Internet ──▶ caddy container (:80/:443, auto Let's Encrypt)
               ├─ domiq-ufa.ru      ─▶ web container (gunicorn :8000, Django)
               │                        WhiteNoise serves /static
               │                        /media served by Django with auth
               │                        SQLite + uploads on the `data` volume
               └─ vpn.domiq-ufa.ru  ─▶ wg-easy container UI (:51821)
WireGuard itself (51820/udp) stays published directly by the wg-easy container.
```

## Prerequisites

- Docker Engine + the compose plugin (`docker compose version`).
- **DNS:** `A` records for **domiq-ufa.ru** and **vpn.domiq-ufa.ru** pointing
  at the server IP. Verify: `dig +short domiq-ufa.ru vpn.domiq-ufa.ru`.
- **Firewall:** 80 and 443 open (80 is required for the ACME HTTP-01
  challenge), 51820/udp open for WireGuard. **51821 must NOT be reachable
  from the internet** once Caddy fronts it (see wg-easy wiring below).

## 1. Get the code and configure

```bash
git clone https://github.com/Mike0808/domiqgo.git /srv/domiqgo
cd /srv/domiqgo
cp deploy/.env.example .env
# Generate a real secret key:
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
nano .env   # paste SECRET_KEY, keep DEBUG=0 and DB_ENGINE=sqlite
```

## 2. Build and start

```bash
docker compose up -d --build
docker compose logs -f caddy   # watch the Let's Encrypt certificates arrive
```

First start runs migrations automatically (entrypoint). Create the landlord
admin account:

```bash
docker compose exec web python manage.py createsuperuser
```

Check: `https://domiq-ufa.ru/login/` (tenant portal) and
`https://domiq-ufa.ru/admin/` (landlord back-office).

## 3. Wire up the existing wg-easy container

The wireguard/wg-easy container is preinstalled on the host and is *not*
managed by this compose file. Give Caddy a private path to its UI:

```bash
docker network connect domiqgo_default wg-easy
docker compose restart caddy
```

Then **stop publishing the UI port publicly** — recreate the wg-easy
container without the `-p 51821:51821` mapping (keep `51820:51820/udp`).
Docker's published ports bypass ufw, so as long as 51821 is published,
firewall rules will NOT protect it.

`https://vpn.domiq-ufa.ru` now serves the wg-easy login over TLS. Caddy adds
only TLS — keep a strong wg-easy password.

If you'd rather leave wg-easy untouched (UI still published on the host),
switch the upstream in `deploy/docker/Caddyfile` to
`host.docker.internal:51821` and restart caddy — but then firewall 51821 at
the provider level, not with ufw.

## Updating after a code change

```bash
cd /srv/domiqgo
git pull
docker compose up -d --build
```

Migrations and collectstatic run automatically (entrypoint / image build).

## Backups (SQLite + uploads → Yandex Disk)

Everything that matters lives on the `data` volume: `/data/db.sqlite3` and
`/data/media/`. `deploy/backup-yadisk.sh` snapshots both (online-safe SQLite
backup, works while the site is live), packs them into
`domiqgo-YYYY-MM-DD_HHMM.tar.gz`, uploads to Yandex Disk over WebDAV, and
prunes old archives (keeps the newest `KEEP`, default 14).

```bash
# once: create an app password (id.yandex.ru -> Безопасность ->
# Пароли приложений -> «Файлы (WebDAV)»), then:
cp deploy/.backup.env.example /srv/domiqgo/.backup.env
chmod 600 /srv/domiqgo/.backup.env
nano /srv/domiqgo/.backup.env          # login + app password
chmod +x deploy/backup-yadisk.sh
./deploy/backup-yadisk.sh              # test run — expect "OK: ... uploaded"

# nightly at 03:00:
crontab -e
# 0 3 * * * /srv/domiqgo/deploy/backup-yadisk.sh >> /var/log/domiqgo-backup.log 2>&1
```

Restore instructions are in the header of `deploy/backup-yadisk.sh`.

## Moving to PostgreSQL later

Set `DB_ENGINE=postgres` and the `DB_*` vars in `.env`, add a postgres
service (or managed DB), and add `--extra postgres` to the `uv sync` line in
the Dockerfile. No code changes.

## Local development (uv)

```powershell
uv sync                                  # creates .venv with dev deps (pytest)
uv run python manage.py migrate
uv run python manage.py runserver
uv run pytest
```

## Frontend CSS build (development machines only)

The stylesheet `billing/static/billing/css/app.css` is **generated** by the
Tailwind standalone CLI (no Node needed) and **committed**, so servers never
build it. Rebuild whenever templates, `static_src/input.css`, or
`tailwind.config.js` change:

```powershell
# one-time: download the CLI (~40 MB) — Windows dev machine
# https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-windows-x64.exe
#   -> save as tools\tailwindcss.exe   (tools/ is git-ignored)
tools\tailwindcss.exe -i static_src\input.css -o billing\static\billing\css\app.css --minify
```

htmx, Alpine.js, and the PT Sans/PT Mono fonts are vendored under
`billing/static/billing/` — the site makes no CDN requests.

## Bare-metal alternative (no Docker)

`deploy/gunicorn.service` (systemd) and `deploy/Caddyfile` (host Caddy) are
kept for a non-Docker install: `uv sync --no-dev` in /srv/domiqgo, copy the
unit, `manage.py migrate && collectstatic`, reload Caddy. The Docker path
above is the recommended one for the MVP VPS.

## Troubleshooting

- **Cert won't issue:** DNS not pointing here yet, or port 80 blocked. Check
  `dig +short domiq-ufa.ru` and watch `docker compose logs -f caddy`.
- **CSRF verification failed on login:** `CSRF_TRUSTED_ORIGINS` in `.env`
  must include `https://domiq-ufa.ru` (scheme included).
- **502 from Caddy:** web container isn't running —
  `docker compose ps`, `docker compose logs web`.
- **`database is locked`:** shouldn't happen (WAL + busy_timeout are on);
  if it does, check for a stray second stack writing to the same volume.
- **wg-easy UI unreachable via vpn.domiq-ufa.ru:** the wg-easy container
  must be on the compose network — `docker network inspect domiqgo_default`
  should list it; re-run the `docker network connect` command after the
  wg-easy container is recreated.
