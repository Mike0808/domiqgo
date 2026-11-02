# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Utility billing portal for rented apartments (domiq-ufa.ru). Django 5.1 monolith, single app `billing`. UI text, model verbose names and user-facing error messages are in Russian; `TIME_ZONE = "Asia/Yekaterinburg"`.

## Commands

Python deps are managed with `uv` (project is not an installable package).

```powershell
uv sync                                   # .venv incl. dev deps (pytest)
uv run python manage.py migrate
uv run python manage.py runserver
uv run pytest                             # whole suite
uv run pytest billing/tests/test_calculation.py::test_name   # single test
uv run python manage.py run_telegram_polling   # dev bot delivery (needs TELEGRAM_BOT_TOKEN)
```

Tailwind CSS (standalone CLI v3, binary in git-ignored `tools/`; download link in `deploy/README.md`). `billing/static/billing/css/app.css` is generated **and committed** — rebuild after touching templates, `static_src/input.css` or `tailwind.config.js`:

```powershell
tools\tailwindcss.exe -i static_src\input.css -o billing\static\billing\css\app.css --minify
```

`conftest.py` swaps the WhiteNoise manifest storage for plain storage in tests, so no `collectstatic` is needed to run them.

## Architecture

**Two audiences.** Tenants use the portal (`billing/views.py`: current month readings, history, documents, OAuth connections). The landlord works entirely in Django admin (`billing/admin.py`) — there is no custom back-office. Users without a `Tenant` row who are staff get redirected to `/admin/`. No self-registration: the landlord creates every account.

**Billing pipeline** — keep the layers separate:
- `services/calculation.py` — pure, DB-free `compute_statement(config, current, previous, tariffs)` on `Decimal`s (rounding rules, two-component hot water via `gvs_heat_norm`, optional floor-to-50 ₽ total with an explicit adjustment line).
- `services/statements.py` — `generate_statement(apartment, period)` loads readings, baselines (previous reading, else `Meter.initial_value`; missing → `MissingBaselineError`, never an implicit 0) and the tariff effective at the period, then `update_or_create`s a `MonthlyStatement` whose `lines` is a JSON snapshot.
- Statements are regenerated when a tenant submits readings, when the landlord saves a `MeterReading` in admin, and via the "Пересчитать начисления" admin action.

**Payment state machine** (`services/intake.py`): `MonthlyStatement.status` is `unpaid → pending` (receipt attached to the *earliest* unpaid statement) `→ paid` (landlord confirms) or back to `unpaid` (reject/delete, only if no other pending payment and never undoing `paid`). Readings are locked while a month is `pending`/`paid`.

**Messenger bot.** `messengers/base.py` defines `MessengerAdapter` (parse/download/send/set_webhook); `telegram.py` is real, `max.py` is a stub. `services/bot.py` is platform-agnostic: `/start <code>` links a chat to a tenant (`services/linking.py`), a photo/file becomes a receipt via `attach_receipt`. Production delivery is `billing/webhooks.py` (secret-token header check); dev uses the polling command. Tests use `billing/tests/fakes.py::FakeAdapter`.

**OAuth (django-allauth, Yandex ID / VK ID / Gosuslugi).** Additive to password login, never creates accounts:
- `billing/adapters.py::NoSignupSocialAccountAdapter` blocks signup and only lets a logged-in tenant connect a provider after 152-FZ consent for the current `billing/consent.py::PRIVACY_POLICY_VERSION` (bump it when the policy text changes materially).
- `config/urls.py` deliberately does not include `allauth.urls` (it would expose local signup); it builds per-provider routes from the provider registry instead.
- `billing/esia_provider/` is a custom Gosuslugi provider with `openid` scope only; it decodes the id_token **without signature verification**. `config/settings.py` refuses to boot with `DEBUG=0` against production ESIA unless `ESIA_ALLOW_UNVERIFIED_SIGNATURE=1`.

**Media is private.** `/media/` is never served statically (not even in DEBUG); uploads go through the auth-checked `billing.views.media_file`.

## Configuration & deployment

Settings come from `.env` (`python-dotenv`; template in `deploy/.env.example`). `DEBUG` defaults to `1`; with `DEBUG=0` the dev `SECRET_KEY` is rejected. Database is SQLite with WAL + `IMMEDIATE` transactions even in production (1 CPU / 1 GB VPS); `DB_ENGINE=postgres` + `uv sync --extra postgres` switches without code changes.

Production is Docker Compose (`web` = gunicorn, `caddy` = TLS) — the entrypoint runs `migrate`, the image build runs `collectstatic`. Full runbook (backups to Yandex Disk, restore, wg-easy wiring) is in `deploy/README.md`. Design specs and implementation plans live in `docs/superpowers/`.

## Frontend
- Django templates only, no SPA
- Template inheritance: base.html + {% block %}
- HTMX for interactivity, Alpine.js for local state (both vendored under `billing/static/billing/vendor/` — no CDN requests)
- Tailwind via standalone CLI (no Node build step); custom palette/fonts in `tailwind.config.js`, which also scans `.venv` crispy-tailwind files
- Forms: django-crispy-forms, never hand-written <form> HTML
