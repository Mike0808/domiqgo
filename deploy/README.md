# Deployment — domiq-ufa.ru (Ubuntu + Caddy + gunicorn + PostgreSQL)

Production stack:

```
Internet ──▶ Caddy (:80/:443, auto Let's Encrypt TLS)
               └─ everything ─▶ gunicorn 127.0.0.1:8000 ──▶ Django
                                   (WhiteNoise serves /static;
                                    /media served by Django with auth —
                                    uploads are private documents)
```

The app lives at `/srv/domiqgo`. Adjust paths if you deploy elsewhere (keep the
Caddyfile `root`, the systemd `WorkingDirectory`/`ExecStart`, and `MEDIA_ROOT`
in agreement).

## Prerequisites

- An Ubuntu VPS with a public IP.
- **DNS:** an `A` record for `domiq-ufa.ru` pointing at that IP. Verify:
  `dig +short domiq-ufa.ru` returns your server IP.
- **Firewall:** ports **80** and **443** open (80 is required for the ACME
  HTTP-01 challenge Caddy uses to get the certificate).

## 1. System packages

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip postgresql
```

Install Caddy (official repo):

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

## 2. PostgreSQL database

```bash
sudo -u postgres psql <<'SQL'
CREATE DATABASE domiqgo;
CREATE USER domiqgo WITH PASSWORD 'replace-with-db-password';
GRANT ALL PRIVILEGES ON DATABASE domiqgo TO domiqgo;
ALTER DATABASE domiqgo OWNER TO domiqgo;
SQL
```

## 3. Application code

```bash
sudo mkdir -p /srv/domiqgo
sudo chown "$USER":"$USER" /srv/domiqgo
git clone https://github.com/Mike0808/domiqgo.git /srv/domiqgo
cd /srv/domiqgo

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-prod.txt
```

## 4. Environment file

```bash
cp deploy/.env.example .env
# Generate a real secret key:
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(64))"
# Edit .env: paste SECRET_KEY, set DB_PASSWORD, keep DEBUG=0.
nano .env
```

## 5. Migrate and collect static

```bash
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py createsuperuser   # your landlord admin login
```

`collectstatic` writes the hashed static manifest WhiteNoise needs — don't skip
it, or admin pages 500 with "Missing staticfiles manifest entry".

## 6. Permissions

Keep the repo owned by your deploy user (so `git pull` and `pip install` keep
working). gunicorn runs as `www-data` and only needs to *write* uploads, plus
*read* the code, static files, and `.env`:

```bash
sudo mkdir -p /srv/domiqgo/media
sudo chown -R www-data:www-data /srv/domiqgo/media
# .env holds secrets: readable by www-data, not by everyone.
sudo chgrp www-data /srv/domiqgo/.env
sudo chmod 640 /srv/domiqgo/.env
```

## 7. gunicorn service

```bash
sudo cp deploy/gunicorn.service /etc/systemd/system/domiqgo.service
sudo systemctl daemon-reload
sudo systemctl enable --now domiqgo
sudo systemctl status domiqgo          # should be active (running)
# Host header required: ALLOWED_HOSTS only lists domiq-ufa.ru, so a bare
# 127.0.0.1 request would get 400 DisallowedHost even on a healthy install.
curl -I -H "Host: domiq-ufa.ru" http://127.0.0.1:8000/login/   # should return 200
```

## 8. Caddy (automatic HTTPS)

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo mkdir -p /var/log/caddy && sudo chown caddy:caddy /var/log/caddy
sudo systemctl reload caddy
sudo journalctl -u caddy -f            # watch it obtain the Let's Encrypt cert
```

On first load of `https://domiq-ufa.ru` Caddy completes the ACME challenge and
installs the certificate. Renewal is automatic — nothing further to do.

## 9. Verify

- Visit `https://domiq-ufa.ru/login/` — valid padlock, tenant login page.
- Visit `https://domiq-ufa.ru/admin/` — your landlord back-office.
- `http://domiq-ufa.ru` redirects to `https://` (Caddy does this automatically).

## Updating after a code change

```bash
cd /srv/domiqgo
git pull
.venv/bin/pip install -r requirements-prod.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart domiqgo
```

## Troubleshooting

- **Cert won't issue:** DNS not pointing here yet, or port 80 blocked. Check
  `dig +short domiq-ufa.ru` and your firewall; watch `journalctl -u caddy -f`.
- **CSRF verification failed on login:** `CSRF_TRUSTED_ORIGINS` in `.env` must
  include `https://domiq-ufa.ru` (scheme included).
- **502 from Caddy:** gunicorn isn't running — `systemctl status domiqgo` and
  `journalctl -u domiqgo -e`.
- **Static/admin pages 500:** re-run `collectstatic --noinput`.
