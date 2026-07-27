# OAuth-вход через Яндекс ID, VK ID, Госуслуги — Design

**Date:** 2026-07-27
**Status:** Approved

## Problem

Tenants log in with a landlord-issued username/password only. The landlord
wants Russian OAuth providers (Яндекс ID, VK ID, Госуслуги) added as an
**additional** login method for every tenant — password login keeps working
unchanged.

## Decisions (made with the landlord)

- Applies to **all tenants**, not one apartment — added as one more way in.
- **Additive**: password stays; OAuth is an extra door to the same account.
- Providers: **Яндекс ID**, **VK ID**, **Госуслуги (ESIA)**.
- **No self-registration through OAuth, ever.** A tenant must log in with
  their landlord-issued password **at least once**, then explicitly connect
  a provider from within their own authenticated session (a «Способы входа»
  page). After that, logging in via that provider works too. An anonymous
  visitor who authenticates with a provider that isn't already connected to
  an account gets rejected with «Обратитесь к арендодателю» — never a
  create-account form. This gives the landlord the same control as manually
  approving each link, without needing to know a tenant's Yandex/VK ID in
  advance (impractical) or handle a linking code out-of-band (unnecessary —
  the tenant is already authenticated when they connect).
- Госуслуги is built now (not deferred), because it is the most recognized
  ID provider in Russia — but flagged: production ESIA access requires the
  landlord's organization to pass Rostelecom/Minsvyaz vetting, which can
  take real time and generally expects a registered ИП/ООО. The code will
  be complete and interface-conforming; it simply won't authenticate real
  users until `ESIA_CLIENT_ID`/`ESIA_CLIENT_SECRET` for an approved
  integration exist in `.env`.

## Architecture

**django-allauth** for the account-linking machinery (`SocialAccount` model:
provider + uid + FK to `User`, already exactly what's needed — no new model).
Яндекс and VK use allauth's bundled providers. Госуслуги has no bundled
allauth provider, so it's a small custom one (`billing/esia_provider/`)
following allauth's standard `OAuth2Provider`/`OAuth2Adapter` extension
points — same shape as the Telegram `MessengerAdapter` pattern already used
in this codebase (a documented seam, not a fork of allauth internals).

**ESIA scope kept minimal: `openid` only.** ESIA's fuller scopes (full name,
SNILS, email, etc.) require every authorization request to carry a PKCS#7
signature made with a GOST-2012-256 certificate registered with the
ministry — a real operational burden for a solo landlord. `openid` alone
identifies the person (a stable `oid` claim) without triggering that
requirement, which is all this system needs: proof of "same person who
logged in before", not their personal data. If the landlord later wants
more (e.g. surname prefill), that's a separate, bigger piece of work and
explicitly out of scope here.

**No auto-signup, enforced centrally.** A custom
`SOCIALACCOUNT_ADAPTER` (`billing/adapters.py`):
- `is_open_for_signup()` → always `False` (belt-and-braces alongside the
  settings flag).
- `pre_social_login()`: if the social account is already linked, proceed
  (normal login). If the current request is an authenticated session,
  proceed (this is the "connect" flow attaching a new provider to the
  tenant's own account). Otherwise (anonymous + unlinked) → short-circuit
  to a friendly Russian "not linked, contact your landlord" page instead of
  allauth's default signup form.

allauth already enforces `(provider, uid)` uniqueness — the same Yandex/VK/
ESIA identity cannot attach to two different tenants, and attempting to
connect an identity already linked elsewhere surfaces allauth's own
"already connected" error (customized to Russian text).

## Settings / config

- `INSTALLED_APPS`: `django.contrib.sites`, `allauth`, `allauth.account`,
  `allauth.socialaccount`, `allauth.socialaccount.providers.yandex`,
  `allauth.socialaccount.providers.vk`, `billing.esia_provider`.
- `SITE_ID = 1`; `AUTHENTICATION_BACKENDS` gains
  `allauth.account.auth_backends.AuthenticationBackend`.
- `SOCIALACCOUNT_AUTO_SIGNUP = False`; `SOCIALACCOUNT_ADAPTER` points at the
  custom adapter above.
- `SOCIALACCOUNT_PROVIDERS` built from env vars (matches this project's
  existing `TELEGRAM_BOT_TOKEN`-style config, not DB-managed `SocialApp`
  rows): `YANDEX_CLIENT_ID`/`YANDEX_CLIENT_SECRET`,
  `VK_CLIENT_ID`/`VK_CLIENT_SECRET`, `ESIA_CLIENT_ID`/`ESIA_CLIENT_SECRET`
  (+ `ESIA_BASE_URL`, defaulting to the sandbox host so a misconfigured
  deployment fails obviously rather than hitting production ESIA).
  All documented in `deploy/.env.example`.

## URLs / pages

- `config/urls.py`: `path("accounts/", include("allauth.urls"))`.
- `billing/templates/billing/oauth_not_linked.html` — «Этот способ входа не
  привязан ни к одному аккаунту. Обратитесь к арендодателю.» (same voice as
  the existing `no_tenant.html`).
- `registration/login.html` — three "Войти через …" buttons under the
  existing password form, each linking to
  `{% provider_login_url "yandex" %}` / `"vk"` / `"esia"`.
- New «Способы входа» page (customized allauth `socialaccount/connections.html`)
  reachable from the nav once logged in: shows which providers are
  connected, "Подключить"/"Отключить" per provider
  (`{% provider_login_url provider.id process="connect" %}`). Disconnecting
  is allowed only if the tenant still has a usable password login (allauth's
  default guard against total lockout) — acceptable since password login
  never goes away here.

## Out of scope

- Any change to how tenant accounts/apartments are created — still
  landlord-only, via admin.
- ESIA scopes beyond `openid` (signed requests, personal data prefill).
- Automatic ESIA sandbox↔production switch-over tooling; the landlord edits
  `.env` when real credentials arrive.

## Testing

- Adapter unit tests: `pre_social_login` proceeds for an existing link,
  proceeds for an authenticated session (connect), and short-circuits to
  the not-linked page for anonymous + unlinked. `is_open_for_signup` is
  always `False`.
- Login page renders all three provider buttons; each URL resolves to a
  real allauth view (200/redirect, not 404).
- Connect flow requires login (`@login_required`-equivalent on the
  connections page — anonymous visitor redirected to `/login/`).
- ESIA provider: unit tests of the adapter's URL-building and `openid`
  token/userinfo parsing against a monkeypatched `requests` (same style as
  `billing/tests/test_telegram_adapter.py` — no real network, no real ESIA
  credentials needed to pass CI).
- Full OAuth handshakes against live Yandex/VK/ESIA servers are explicitly
  **not** covered by the automated suite (they require real registered app
  credentials and network access) — call this out in the plan as a manual
  smoke test to run once real credentials exist in `.env`.
