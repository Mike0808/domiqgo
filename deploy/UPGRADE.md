# Upgrading production without losing data

How to move the live site (`/srv/domiqgo`, Docker Compose, SQLite on the
`domiqgo_data` volume) to a newer version of `master`:

1. Write down exactly what runs now.
2. Take a full backup.
3. Run the **new version next to the old one**, on a *copy* of the data,
   reachable only by you through an SSH tunnel. Tenants and the Telegram
   bot keep using the old version.
4. When it checks out, switch the live site over in place (about 10–20 s of
   downtime). The live volume is upgraded where it is, so nothing entered
   in the meantime is lost.
5. Remove the side-by-side copy.

The whole procedure was rehearsed with Docker, upgrading a pre-OAuth build
(`00ca461`, billing migrations up to 0005) to current `master`: 18
migrations applied, record counts and uploaded files identical, data added
on the old site after the backup survived the switch, and the rollback in
the last section brought the old version back on the same data.

Run everything on the server as a user that can run `docker`. Commands use
these variables — **re-run this block if you reconnect** (shell variables
don't survive a new SSH session):

```bash
export APP=/srv/domiqgo
export NEW=/srv/domiqgo-new
export BK=/srv/domiqgo-backups/upgrade-$(date +%F_%H%M)   # set once; reuse the same value later
```

> **Never** run `docker compose down -v` in `$APP`: `-v` deletes the live
> database and every upload. Nothing in this guide needs it.

---

## 1. Write down what runs now

```bash
cd $APP
mkdir -p $BK
git rev-parse HEAD | tee $BK/old-commit.txt
docker compose ps
docker compose exec -T web python manage.py showmigrations billing | tee $BK/old-migrations.txt
```

The last `[X]` line in `old-migrations.txt` (e.g. `0005_apartment_round_total`)
is your **rollback target** — you only need it if you ever roll back.

See what the upgrade brings:

```bash
git fetch origin
git log --oneline $(cat $BK/old-commit.txt)..origin/master
git diff --stat $(cat $BK/old-commit.txt) origin/master -- billing/migrations deploy/.env.example docker-compose.yml
```

Check headroom (two stacks run for a while; the new one uses 1 worker):

```bash
df -h /            # want a few GB free for the second image
free -m
```

## 2. Full backup

Online-safe — the site keeps running.

```bash
cd $APP
# SQLite snapshot through the backup API (safe while the site is live)
docker compose exec -T web python - <<'PY'
import sqlite3
src = sqlite3.connect("/data/db.sqlite3")
dst = sqlite3.connect("/data/upgrade-snapshot.sqlite3")
with dst:
    src.backup(dst)
dst.close(); src.close()
PY
docker compose cp web:/data/upgrade-snapshot.sqlite3 $BK/db.sqlite3
docker compose exec -T web rm -f /data/upgrade-snapshot.sqlite3

# Uploads (rental agreements, receipts)
docker compose cp web:/data/media $BK/media || mkdir -p $BK/media

# Settings
cp .env $BK/env.backup

# Verify, then pack one archive
python3 -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('pragma integrity_check').fetchone()[0])" $BK/db.sqlite3
#  -> must print: ok
find $BK/media -type f | wc -l       # number of uploaded files
tar -czf $BK.tar.gz -C $BK .
ls -lh $BK.tar.gz
```

If the Yandex Disk backup is set up, also run it so a copy leaves the server:

```bash
$APP/deploy/backup-yadisk.sh
```

## 3. Start the new version next to the old one

The new version gets its own checkout (`$NEW`), its own containers and its
own volume (`domiqgo-new_data`) through the project name `domiqgo-new`. The
override file `deploy/docker/compose.side-by-side.yml` keeps it off ports
80/443, binds it to `127.0.0.1:8001`, runs 1 worker and blanks the Telegram
settings so it never answers the bot.

```bash
# Separate checkout of the new code (shares the git repo, no second clone)
git -C $APP worktree add --detach $NEW origin/master
cp $APP/.env $NEW/.env
```

Compare `.env` with the new template and add any variables that are new
(OAuth ones may be left empty — those login buttons just won't work yet):

```bash
diff <(grep -oE '^[A-Z_]+' $NEW/.env | sort) <(grep -oE '^[A-Z_]+' $NEW/deploy/.env.example | sort)
```

Lines marked `>` are in the template but not in your `.env`. If you add
any, add them to `$APP/.env` too, so the live site gets them at the switch.

Build, load the **copy** of the data, start:

```bash
cd $NEW
newc() { docker compose -p domiqgo-new -f docker-compose.yml -f deploy/docker/compose.side-by-side.yml "$@"; }

newc build web

# Put the backup into the new volume (as root, then hand it to the app user)
newc run --rm --no-deps -u root --entrypoint sh -v $BK:/restore:ro web -c \
  'cp /restore/db.sqlite3 /data/db.sqlite3 && rm -rf /data/media && cp -r /restore/media /data/media && chown -R app:app /data'

newc up -d web
newc logs web | grep -E 'Applying|Error|Listening'
#  -> "Applying ... OK" lines for new migrations, then "Listening at"
newc exec -T web python manage.py showmigrations | grep '\[ \]' || echo "all migrations applied"
```

Both versions are now up:

```bash
docker ps --format '{{.Names}}  {{.Status}}  {{.Ports}}'
#  domiqgo-web-1, domiqgo-caddy-1   <- live (old)
#  domiqgo-new-web-1  127.0.0.1:8001->8000/tcp   <- new, on the copy
```

Compare record counts — they must match (the old site may have a few more
if people used it since step 2):

```bash
Q='from billing.models import *; print({m.__name__: m.objects.count() for m in (Apartment, Tenant, Tariff, Meter, MeterReading, MonthlyStatement, Payment, Document)})'
(cd $APP && docker compose exec -T web python manage.py shell -c "$Q")
newc exec -T web python manage.py shell -c "$Q"
```

> In `$NEW`, use `newc` every time. A plain `docker compose` there would
> address a different project.

## 4. Check the new version yourself

From **your own computer**, open a tunnel and keep that window open:

```bash
ssh -L 8001:127.0.0.1:8001 <user>@domiq-ufa.ru
```

Open **http://localhost:8001** in the browser. (Plain http is expected here;
browsers allow the secure session cookie on `localhost`.)

- Log in as a tenant: «Этот месяц», «История», «Чеки», «Документы» show the
  real data; an old receipt and the rental agreement open.
- Upload a test receipt on «Чеки».
- `http://localhost:8001/admin/` — log in as the landlord, look at
  «Платежи» and «Начисления».

Everything you do here happens on the **copy** and is thrown away in
step 6. Yandex/VK/Gosuslugi buttons can't complete a login on
`localhost:8001` (providers only redirect to the registered domain) —
that's expected.

Found a problem? Stop here: remove the copy (step 6) and the live site was
never touched.

## 5. Switch the live site to the new version

Pick a quiet moment. Take a **fresh** backup right before, so it includes
everything entered since step 2:

```bash
export BK=/srv/domiqgo-backups/upgrade-$(date +%F_%H%M)-cutover
mkdir -p $BK
cd $APP && git rev-parse HEAD > $BK/old-commit.txt
```

Repeat the commands of **step 2** (snapshot, media, `.env`, integrity
check, tar). Then:

```bash
cd $APP
git pull --ff-only                 # moves the live checkout to the new master
docker compose build web           # build while the old site still serves
docker compose up -d               # recreates web: migrations run, then gunicorn starts
docker compose logs --since 5m web | grep -E 'Applying|Error|Listening'
docker compose exec -T web python manage.py showmigrations | grep '\[ \]' || echo "all migrations applied"
docker compose ps
```

Only when upgrading from a version **before OAuth login** (the
`old-migrations.txt` from step 1 has no `0006_tenant_privacy_consent...`
line): point allauth's site record at the real domain, once:

```bash
docker compose exec -T web python manage.py shell -c "from django.contrib.sites.models import Site; Site.objects.update_or_create(id=1, defaults={'domain': 'domiq-ufa.ru', 'name': 'domiq-ufa.ru'})"
```

Check the live site:

- `https://domiq-ufa.ru/login/` loads; a tenant can log in and sees their
  data; «Чеки» is there.
- `https://domiq-ufa.ru/admin/` works for the landlord.
- Send the Telegram bot a message — it answers (the webhook URL hasn't
  changed, so nothing needs re-registering).
- Record counts (the `$Q` command from step 3, in `$APP`) are the same as
  just before the switch.

## 6. Remove the side-by-side copy

Wait until you're happy with the live site (a day is fine), then:

```bash
cd $NEW
docker compose -p domiqgo-new -f docker-compose.yml -f deploy/docker/compose.side-by-side.yml down
docker volume rm domiqgo-new_data            # the COPY's volume — check the name says "-new"
cd $APP
git worktree remove --force $NEW             # --force: it holds the untracked .env
docker image prune -f                        # drop unused old images
```

Keep the backup archives (`/srv/domiqgo-backups/*.tar.gz`) until the next
regular backup has run successfully.

---

## Rolling back after the switch

**Keeping the data entered since the switch** (preferred). Undo the new
migrations with the *new* code still running, then go back to the old code.
Use the rollback target from step 1. `$BK` here is the **cutover** backup
folder from step 5 (`ls -d /srv/domiqgo-backups/*-cutover` if you
reconnected):

```bash
export BK=/srv/domiqgo-backups/upgrade-YYYY-MM-DD_HHMM-cutover   # <- yours
cd $APP
docker compose exec -T web python manage.py migrate billing 0005_apartment_round_total   # <- your target
git checkout $(cat $BK/old-commit.txt)
docker compose up -d --build
```

This drops only what the new version added (e.g. recorded privacy
consents); readings, statements, payments and files stay. Tables added by
other apps (such as allauth's) are left in place and ignored by the old
code. To upgrade again later: `git checkout master`, then step 5.

**Restoring the backup** (if the database itself is damaged). Everything
entered after the cutover backup is lost:

```bash
cd $APP
git checkout $(cat $BK/old-commit.txt)
docker compose build web
docker compose stop web
docker compose cp $BK/db.sqlite3 web:/data/db.sqlite3
docker compose run --rm --no-deps --entrypoint sh web -c 'rm -f /data/db.sqlite3-wal /data/db.sqlite3-shm && rm -rf /data/media'
docker compose cp $BK/media web:/data/media
docker compose run --rm --no-deps -u root --entrypoint chown web -R app:app /data
docker compose up -d
```

The `chown` matters: files copied in with `docker compose cp` belong to
root, and the site would come back unable to save anything ("attempt to
write a readonly database"). `deploy/restore-yadisk.sh` does the same for a
Yandex Disk backup.
