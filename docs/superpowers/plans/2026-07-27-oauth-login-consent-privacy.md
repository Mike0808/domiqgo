# OAuth Login (Yandex ID / VK ID / Gosuslugi) + Consent + Privacy Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a tenant log in via Яндекс ID, VK ID, or Госуслуги in addition to their existing username/password, with no path to self-register an account, and with a 152-ФЗ-compliant consent step and public privacy policy gating any new personal-data processing.

**Architecture:** `django-allauth` supplies the `SocialAccount` linking model and the Yandex/VK provider integrations; a small custom `OAuth2Provider` follows the same pattern for Госуслуги (ESIA), using only the `openid` scope so it never needs a GOST-signed request. A single custom `SOCIALACCOUNT_ADAPTER` is the one enforcement point for two rules: never auto-create an account, and never let a tenant connect a provider before they've given consent. Only `allauth.socialaccount.urls` is wired in — **not** `allauth.urls` — so allauth's own local-account signup/login views are never exposed.

**Tech Stack:** Django 5.1, django-allauth, existing `requests` (already a dependency, reused by the ESIA adapter), pytest + pytest-django.

## Global Constraints

- Python 3.12+, Django 5.1.x — do not change the existing pin (`pyproject.toml`).
- Windows/PowerShell only; the Bash tool is non-functional in this environment. Always invoke the venv interpreter explicitly: `.\.venv\Scripts\python.exe -m pytest ...` and `.\.venv\Scripts\python.exe manage.py ...`.
- Dependency installs go through `uv` (`uv add <package>`, then `uv sync`). If `uv lock`/`uv sync`/`pip install` fail with `CERTIFICATE_VERIFY_FAILED` (this environment sits behind a TLS-intercepting corporate proxy), set `$env:SSL_CERT_FILE = "$env:TEMP\corp-ca.pem"` first if that file exists from a prior session, otherwise re-export the proxy's certificate chain the same way earlier sessions did, or fall back to `pip install --use-feature=truststore <package>`.
- TDD: failing test first, watch it fail, minimal implementation, watch it pass, run the full suite once before committing, commit.
- Commit with `git add <exact files>` — never `git add -A` (unrelated scratch directories exist in the working tree). If a commit fails on git identity, prefix `git -c user.name="local-rent" -c user.email="haighrain@gmail.com" commit ...`.
- **No self-registration via OAuth, ever** — enforced centrally in the adapter (`pre_social_login`), not only by hiding UI.
- Provider ids are exactly: `"yandex"`, `"vk"`, `"esia"`.
- **Only `allauth.socialaccount.urls` is included in `config/urls.py`** — never `allauth.urls` (which also exposes allauth's own account signup/login/password-reset views, defeating "no self-registration").
- A tenant must give consent (timestamp + policy version recorded) **before** any OAuth provider can be connected to their account. Enforced in the adapter, not only in the view.
- The privacy policy page must be reachable at `/privacy/` without login.
- Existing models, calculation core, and statement logic are untouched by this plan.
- The ESIA adapter decodes the identity token's payload **without verifying its signature** — call this out in a code comment and in the final report; it is a known, deliberate limitation until real ESIA accreditation provides the verification certificate.

---

## File Structure

```
billing/
  adapters.py                    # NEW: NoSignupSocialAccountAdapter
  consent.py                     # NEW: PRIVACY_POLICY_VERSION constant
  models.py                      # + Tenant.privacy_consent_at / privacy_consent_version (append)
  views.py                       # + oauth_connections, privacy_policy (append)
  urls.py                        # + connections/, privacy/ routes (append)
  migrations/000N_*.py           # NEW: Tenant consent fields
  esia_provider/
    __init__.py                  # NEW
    apps.py                      # NEW: registers ESIAProvider with allauth's registry
    provider.py                  # NEW: ESIAProvider(OAuth2Provider)
    views.py                     # NEW: ESIAOAuth2Adapter(OAuth2Adapter) + login/callback views
    urls.py                      # NEW: default_urlpatterns(ESIAProvider)
  templates/
    billing/
      oauth_not_linked.html      # NEW
      oauth_consent.html         # NEW
      oauth_connections.html     # NEW
      privacy_policy.html        # NEW
    registration/
      login.html                 # + provider login buttons (modify)
    billing/base.html             # + nav link to "Способы входа" (modify)
  tests/
    test_oauth_adapter.py        # NEW
    test_oauth_consent.py        # NEW
    test_privacy_policy.py       # NEW
    test_oauth_providers.py      # NEW
    test_esia_provider.py        # NEW
config/settings.py               # + allauth apps/backends/adapter/provider settings (append)
config/urls.py                   # + include("allauth.socialaccount.urls") (append)
pyproject.toml                   # + django-allauth dependency
deploy/.env.example               # + YANDEX_*/VK_*/ESIA_* vars (append)
```

**Responsibilities:** `adapters.py` is the single enforcement point for "no self-signup" and "consent before connect". `consent.py` holds the one version constant both the adapter and the view compare against. `esia_provider/` isolates all Госуслуги-specific OAuth2 plumbing behind allauth's standard provider extension points, mirroring how `billing/messengers/` isolates Telegram/MAX behind `MessengerAdapter`.

---

### Task 1: Install django-allauth, wire settings and socialaccount-only urls

**Files:**
- Modify: `pyproject.toml`
- Modify: `config/settings.py`
- Modify: `config/urls.py`
- Test: `billing/tests/test_oauth_providers.py` (created here, extended in Task 5)

**Interfaces:**
- Produces: `INSTALLED_APPS` containing `django.contrib.sites`, `allauth`, `allauth.account`, `allauth.socialaccount`; `SITE_ID = 1`; `AUTHENTICATION_BACKENDS` containing `allauth.account.auth_backends.AuthenticationBackend`; `SOCIALACCOUNT_AUTO_SIGNUP = False`; `MIDDLEWARE` containing `allauth.account.middleware.AccountMiddleware`. `config/urls.py` includes `allauth.socialaccount.urls` at `accounts/`.

- [ ] **Step 1: Add the dependency**

```powershell
uv add "django-allauth>=65,<66"
```

If uv reports a TLS certificate error, run:
```powershell
$env:SSL_CERT_FILE = "$env:TEMP\corp-ca.pem"
uv add "django-allauth>=65,<66"
```
If that file doesn't exist, export the proxy's certificate chain the same way as in `deploy/README.md`'s troubleshooting notes, or use `pip install --use-feature=truststore django-allauth` into `.venv` directly and add the line to `pyproject.toml`'s `dependencies` list by hand, then run `uv lock` to regenerate `uv.lock` (it will pick up the already-installed version).

Verify: `.venv\Scripts\python.exe -c "import allauth; print(allauth.__version__)"` prints a version starting with a number >= 65.

- [ ] **Step 2: Write the failing test**

`billing/tests/test_oauth_providers.py`:

```python
import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

def test_socialaccount_connections_url_redirects_anonymous_to_login():
    # Proves allauth.socialaccount.urls is wired in and login-gated.
    resp = Client().get("/accounts/social/connections/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest billing/tests/test_oauth_providers.py -v`
Expected: FAIL — either a 404 (urls not wired) or an error from Django complaining allauth apps aren't installed/migrated yet.

- [ ] **Step 4: Wire settings**

In `config/settings.py`, change the `INSTALLED_APPS` list to:

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "crispy_forms",
    "crispy_tailwind",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.yandex",
    "allauth.socialaccount.providers.vk",
    "billing",
]

SITE_ID = 1
```

Add `"allauth.account.middleware.AccountMiddleware"` to the end of `MIDDLEWARE`:

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]
```

Add near the bottom of the file (after the existing `TELEGRAM_*` settings):

```python
# OAuth login (Yandex ID / VK ID / Gosuslugi) — additive to password login.
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

SOCIALACCOUNT_ADAPTER = "billing.adapters.NoSignupSocialAccountAdapter"
SOCIALACCOUNT_AUTO_SIGNUP = False
SOCIALACCOUNT_LOGIN_ON_GET = True
```

(`billing.adapters` doesn't exist yet — that's Task 2. Django won't import it until a social login is actually attempted, so the app boots fine with this pointing at a not-yet-created module for now, but running the test suite before Task 2 exists would fail on any test that exercises an actual social-login flow — Task 1's test above doesn't, so it's fine.

Note: `"billing.esia_provider"` is **not** added to `INSTALLED_APPS` here — that package doesn't exist until Task 6 creates it, and listing a non-existent app would break Django's startup for every task in between. Task 6 adds that line when it creates the package.)

- [ ] **Step 5: Wire urls**

In `config/urls.py`, add the import and a new path, placed before the closing of `urlpatterns`:

```python
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.socialaccount.urls")),
    path("", include("billing.urls")),
]
```

(Note: `include("allauth.socialaccount.urls")`, **not** `include("allauth.urls")` — the latter also bundles allauth's own local-account signup/login/password-reset views, which would let anyone create a brand-new password account, defeating "landlord issues logins".)

- [ ] **Step 6: Create migrations for the new allauth apps and run them**

```powershell
.venv\Scripts\python.exe manage.py migrate
```

Expected output includes lines applying `sites`, `account`, and `socialaccount` migrations (these ship inside the installed packages — no new migration file is created in `billing/migrations/`).

- [ ] **Step 7: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest billing/tests/test_oauth_providers.py -v`
Expected: PASS

- [ ] **Step 8: Run the full suite to confirm no regressions**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all previously-passing tests still pass, plus the 1 new test (90 passed, if the suite was at 89 before this plan).

- [ ] **Step 9: Commit**

```powershell
git add pyproject.toml uv.lock config/settings.py config/urls.py billing/tests/test_oauth_providers.py
git commit -m "feat: install django-allauth, wire socialaccount-only urls"
```

---

### Task 2: Custom adapter — no self-signup, consent-gated connect

**Files:**
- Create: `billing/adapters.py`
- Create: `billing/consent.py`
- Create: `billing/templates/billing/oauth_not_linked.html`
- Test: `billing/tests/test_oauth_adapter.py`

**Interfaces:**
- Consumes: `Tenant` model (`billing/models.py`) — will gain `privacy_consent_version` in Task 3; this task's tests use a plain object stand-in for the parts of `Tenant` it reads, so it does not depend on Task 3 having run yet. Once Task 3 lands, the real `Tenant.privacy_consent_version` field satisfies the same read.
- Produces: `billing.adapters.NoSignupSocialAccountAdapter` with methods `is_open_for_signup(request, sociallogin) -> bool` and `pre_social_login(request, sociallogin) -> None` (raises `allauth`'s `ImmediateHttpResponse` to short-circuit). `billing.consent.PRIVACY_POLICY_VERSION: str`.

- [ ] **Step 1: Determine the correct `ImmediateHttpResponse` import path for the installed allauth version**

```powershell
.venv\Scripts\python.exe -c "from allauth.core.exceptions import ImmediateHttpResponse; print('core.exceptions')"
```

If that fails with `ModuleNotFoundError` or `ImportError`, try:

```powershell
.venv\Scripts\python.exe -c "from allauth.exceptions import ImmediateHttpResponse; print('exceptions')"
```

Use whichever import path succeeds in Step 3 below (write it as `from allauth.core.exceptions import ImmediateHttpResponse` if the first worked, otherwise `from allauth.exceptions import ImmediateHttpResponse`).

- [ ] **Step 2: Write the failing test**

`billing/tests/test_oauth_adapter.py`:

```python
from datetime import date
import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory
from billing.adapters import NoSignupSocialAccountAdapter
from billing.consent import PRIVACY_POLICY_VERSION
from billing.models import Apartment, Tenant

pytestmark = pytest.mark.django_db

class _FakeSocialLogin:
    """Stand-in exposing only the attribute the adapter actually reads —
    avoids depending on allauth's real SocialLogin constructor shape."""
    def __init__(self, is_existing):
        self.is_existing = is_existing

def _request(user):
    req = RequestFactory().get("/")
    req.user = user
    return req

def test_is_open_for_signup_is_always_false():
    adapter = NoSignupSocialAccountAdapter()
    assert adapter.is_open_for_signup(_request(AnonymousUser()), _FakeSocialLogin(False)) is False

def test_pre_social_login_proceeds_for_existing_link():
    adapter = NoSignupSocialAccountAdapter()
    # Must not raise for an already-linked account (normal login).
    adapter.pre_social_login(_request(AnonymousUser()), _FakeSocialLogin(True))

def test_pre_social_login_rejects_anonymous_unlinked():
    from allauth.core.exceptions import ImmediateHttpResponse
    adapter = NoSignupSocialAccountAdapter()
    with pytest.raises(ImmediateHttpResponse):
        adapter.pre_social_login(_request(AnonymousUser()), _FakeSocialLogin(False))

def test_pre_social_login_redirects_to_connections_when_consent_missing():
    from allauth.core.exceptions import ImmediateHttpResponse
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user("ivanov", password="pass12345")
    Tenant.objects.create(user=u, apartment=a, full_name="Иванов")  # no consent given
    adapter = NoSignupSocialAccountAdapter()
    with pytest.raises(ImmediateHttpResponse) as exc:
        adapter.pre_social_login(_request(u), _FakeSocialLogin(False))
    assert exc.value.response.status_code == 302
    assert exc.value.response.headers["Location"] == "/connections/"

def test_pre_social_login_proceeds_when_consent_given():
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user("petrov", password="pass12345")
    Tenant.objects.create(user=u, apartment=a, full_name="Петров",
                         privacy_consent_at=date(2026, 7, 27),
                         privacy_consent_version=PRIVACY_POLICY_VERSION)
    adapter = NoSignupSocialAccountAdapter()
    # Must not raise — connect is allowed once consent matches the current version.
    adapter.pre_social_login(_request(u), _FakeSocialLogin(False))
```

(This test file references `Tenant.privacy_consent_at`/`privacy_consent_version`, which don't exist until Task 3. That's fine — this task's test run in Step 3 is expected to fail on the `ModuleNotFoundError: billing.adapters` first; after Step 4 makes the module exist, the two tests using those fields will still fail with `TypeError: unexpected keyword argument` until Task 3 adds them. Task 2's Step 5 below runs only the two tests that don't need those fields; the full file is confirmed green at the end of Task 3.)

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest billing/tests/test_oauth_adapter.py::test_is_open_for_signup_is_always_false billing/tests/test_oauth_adapter.py::test_pre_social_login_proceeds_for_existing_link billing/tests/test_oauth_adapter.py::test_pre_social_login_rejects_anonymous_unlinked -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'billing.adapters'` (and `billing.consent`).

- [ ] **Step 4: Implement**

`billing/consent.py`:

```python
# Bump this string whenever the privacy policy text changes materially —
# every tenant with an older recorded consent will be asked to re-consent
# before connecting a new OAuth provider (see billing/adapters.py).
PRIVACY_POLICY_VERSION = "2026-07-27"
```

`billing/adapters.py` (using whichever import Step 1 determined — this plan writes the `allauth.core.exceptions` form; swap to `allauth.exceptions` if that's what Step 1 found):

```python
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import redirect, render
from .consent import PRIVACY_POLICY_VERSION

class NoSignupSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Enforces two rules everywhere, not just in the UI:
    1. OAuth can never create a new account — a tenant record must already
       exist (landlord-issued username/password).
    2. A tenant may only CONNECT a new provider to their own account after
       giving 152-FZ consent for the current policy version.
    """

    def is_open_for_signup(self, request, sociallogin):
        return False

    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            return  # already linked -> ordinary login, proceed
        if request.user.is_authenticated:
            tenant = getattr(request.user, "tenant", None)
            if tenant is None or tenant.privacy_consent_version != PRIVACY_POLICY_VERSION:
                raise ImmediateHttpResponse(redirect("oauth_connections"))
            return  # consent on file -> allow attaching the new provider
        raise ImmediateHttpResponse(
            render(request, "billing/oauth_not_linked.html", status=403))
```

`billing/templates/billing/oauth_not_linked.html`:

```html
{% extends "billing/base.html" %}
{% block title %}Вход не выполнен{% endblock %}
{% block content %}
<section class="rounded-lg border border-line bg-white p-5">
  <h1 class="mb-2 text-xl font-bold">Этот способ входа не привязан к аккаунту</h1>
  <p class="text-sm text-ink-soft">
    Обратитесь к арендодателю, чтобы получить логин и пароль. После этого вы
    сможете подключить Яндекс ID, VK ID или Госуслуги в разделе
    «Способы входа».
  </p>
</section>
{% endblock %}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest billing/tests/test_oauth_adapter.py::test_is_open_for_signup_is_always_false billing/tests/test_oauth_adapter.py::test_pre_social_login_proceeds_for_existing_link billing/tests/test_oauth_adapter.py::test_pre_social_login_rejects_anonymous_unlinked -v`
Expected: PASS (3 passed). The other two tests in the file still fail/error until Task 3 — that's expected, don't run the whole file yet.

- [ ] **Step 6: Commit**

```powershell
git add billing/adapters.py billing/consent.py billing/templates/billing/oauth_not_linked.html billing/tests/test_oauth_adapter.py
git commit -m "feat: no-signup social adapter with consent-gated connect"
```

---

### Task 3: Consent fields, connections page, consent form

**Files:**
- Modify: `billing/models.py` (append `Tenant` fields)
- Create: `billing/migrations/000N_tenant_privacy_consent.py` (via `makemigrations`)
- Modify: `billing/views.py` (append `oauth_connections`)
- Modify: `billing/urls.py` (append route)
- Modify: `billing/templates/billing/base.html` (nav link)
- Create: `billing/templates/billing/oauth_consent.html`
- Create: `billing/templates/billing/oauth_connections.html`
- Test: `billing/tests/test_oauth_consent.py`
- Test: extend `billing/tests/test_oauth_adapter.py` (the two tests already written in Task 2 now pass)

**Interfaces:**
- Consumes: `billing.consent.PRIVACY_POLICY_VERSION` (Task 2). `allauth.socialaccount.models.SocialAccount` (from the dependency added in Task 1).
- Produces: `Tenant.privacy_consent_at: DateTimeField | None`, `Tenant.privacy_consent_version: str`. View `oauth_connections` at url name `oauth_connections`, path `/connections/`.

- [ ] **Step 1: Write the failing tests**

`billing/tests/test_oauth_consent.py`:

```python
from datetime import date
import pytest
from django.contrib.auth.models import User
from django.test import Client
from billing.consent import PRIVACY_POLICY_VERSION
from billing.models import Apartment, Tenant

pytestmark = pytest.mark.django_db

def _tenant(username, consented=False):
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user(username, password="pass12345")
    kwargs = {}
    if consented:
        kwargs = {"privacy_consent_at": date(2026, 7, 27),
                  "privacy_consent_version": PRIVACY_POLICY_VERSION}
    Tenant.objects.create(user=u, apartment=a, full_name="Жилец", **kwargs)
    return u

def _login(username):
    c = Client()
    assert c.login(username=username, password="pass12345")
    return c

def test_connections_page_requires_login():
    resp = Client().get("/connections/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

def test_connections_page_shows_consent_form_first(db):
    _tenant("noconsent")
    c = _login("noconsent")
    resp = c.get("/connections/")
    assert resp.status_code == 200
    assert "согласие" in resp.content.decode().lower()
    assert "Яндекс" not in resp.content.decode()  # provider list not shown yet

def test_posting_consent_records_it_and_shows_providers(db):
    _tenant("agrees")
    c = _login("agrees")
    resp = c.post("/connections/", {"consent": "on"}, follow=True)
    assert resp.status_code == 200
    tenant = Tenant.objects.get(user__username="agrees")
    assert tenant.privacy_consent_version == PRIVACY_POLICY_VERSION
    assert tenant.privacy_consent_at is not None
    assert "Яндекс" in resp.content.decode()

def test_connections_page_lists_providers_when_already_consented(db):
    _tenant("already", consented=True)
    c = _login("already")
    resp = c.get("/connections/")
    assert resp.status_code == 200
    assert "Яндекс" in resp.content.decode()
    assert "VK" in resp.content.decode()
    assert "Госуслуги" in resp.content.decode()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest billing/tests/test_oauth_consent.py -v`
Expected: FAIL — `Tenant() got unexpected keyword arguments` and/or 404s (fields and view don't exist yet).

- [ ] **Step 3: Add the model fields**

In `billing/models.py`, inside the `Tenant` class, after the existing `link_code` field:

```python
    # 152-ФЗ: consent must be on file, for the current policy version,
    # before a tenant may connect any OAuth provider (see billing/adapters.py).
    privacy_consent_at = models.DateTimeField(
        "Согласие на обработку ПДн дано", null=True, blank=True)
    privacy_consent_version = models.CharField(
        "Версия политики на момент согласия", max_length=32, blank=True)
```

- [ ] **Step 4: Generate and apply the migration**

```powershell
.venv\Scripts\python.exe manage.py makemigrations billing
.venv\Scripts\python.exe manage.py migrate
```

Expected: a new file `billing/migrations/000N_tenant_privacy_consent_at_and_more.py` (exact name assigned by Django) adding the two fields.

- [ ] **Step 5: Implement the view**

In `billing/views.py`, add the import and the view (after the existing `media_file` view):

```python
from django.utils import timezone
from allauth.socialaccount.models import SocialAccount
from .consent import PRIVACY_POLICY_VERSION
```

(Add these alongside the existing imports at the top of the file.)

```python
@login_required
def oauth_connections(request):
    tenant = _tenant_for(request)
    if tenant is None:
        return _no_tenant_response(request)
    if request.method == "POST" and "consent" in request.POST:
        tenant.privacy_consent_at = timezone.now()
        tenant.privacy_consent_version = PRIVACY_POLICY_VERSION
        tenant.save(update_fields=["privacy_consent_at", "privacy_consent_version"])
        return redirect("oauth_connections")
    if tenant.privacy_consent_version != PRIVACY_POLICY_VERSION:
        return render(request, "billing/oauth_consent.html", {})
    connected_provider_ids = list(
        SocialAccount.objects.filter(user=request.user).values_list("provider", flat=True))
    return render(request, "billing/oauth_connections.html",
                  {"connected_provider_ids": connected_provider_ids})
```

- [ ] **Step 6: Wire the url**

In `billing/urls.py`, add the route (after `media_file`):

```python
    path("connections/", views.oauth_connections, name="oauth_connections"),
```

- [ ] **Step 7: Templates**

`billing/templates/billing/oauth_consent.html`:

```html
{% extends "billing/base.html" %}
{% block title %}Согласие на обработку персональных данных{% endblock %}
{% block content %}
<section class="rounded-lg border border-line bg-white p-5">
  <h1 class="mb-4 text-xl font-bold">Согласие на обработку персональных данных</h1>
  <p class="mb-4 text-sm">
    Перед подключением входа через Яндекс ID, VK ID или Госуслуги необходимо
    дать согласие на обработку персональных данных, которые передаёт выбранный
    сервис (идентификатор учётной записи и, при наличии, имя и адрес
    электронной почты). Полный текст:
    <a href="{% url 'privacy_policy' %}" class="text-accent underline" target="_blank">
      Политика обработки персональных данных</a>.
  </p>
  <form method="post">
    {% csrf_token %}
    <label class="mb-4 flex items-start gap-2 text-sm">
      <input type="checkbox" name="consent" required class="mt-1">
      <span>Я ознакомлен(а) и даю согласие на обработку персональных данных.</span>
    </label>
    <button type="submit"
            class="rounded bg-accent px-4 py-2.5 font-bold text-white hover:bg-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
      Согласиться и продолжить
    </button>
  </form>
</section>
{% endblock %}
```

`billing/templates/billing/oauth_connections.html`:

```html
{% extends "billing/base.html" %}
{% load socialaccount %}
{% block title %}Способы входа{% endblock %}
{% block content %}
<h1 class="mb-6 text-3xl font-bold">Способы входа</h1>
<section class="rounded-lg border border-line bg-white p-5">
  <p class="mb-4 text-sm text-ink-soft">
    Логин и пароль всегда работают. Ниже можно дополнительно подключить вход
    через Яндекс ID, VK ID или Госуслуги.
  </p>
  {% get_providers as socialaccount_providers %}
  {% for provider in socialaccount_providers %}
    <div class="mb-2 flex items-center justify-between border-b border-line pb-2">
      <span class="text-sm">{{ provider.name }}</span>
      {% if provider.id in connected_provider_ids %}
        <span class="text-sm font-bold text-paid">Подключено</span>
      {% else %}
        <a href="{% provider_login_url provider.id process='connect' %}"
           class="rounded bg-accent px-3 py-1.5 text-sm font-bold text-white hover:bg-ink">
          Подключить
        </a>
      {% endif %}
    </div>
  {% endfor %}
</section>
{% endblock %}
```

- [ ] **Step 8: Add the nav link**

In `billing/templates/billing/base.html`, inside the authenticated `<nav>` block, after the «Документы» link:

```html
    <a href="{% url 'oauth_connections' %}"
       class="rounded-t px-3 py-2 text-sm {% if url_name == 'oauth_connections' %}border-x border-t border-line bg-paper font-bold{% else %}text-ink-soft hover:text-ink{% endif %}">Способы входа</a>
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest billing/tests/test_oauth_consent.py billing/tests/test_oauth_adapter.py -v`
Expected: PASS (all tests in both files, including the two in `test_oauth_adapter.py` left unrun in Task 2).

- [ ] **Step 10: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all green, no regressions.

- [ ] **Step 11: Commit**

```powershell
git add billing/models.py billing/migrations billing/views.py billing/urls.py billing/templates/billing/base.html billing/templates/billing/oauth_consent.html billing/templates/billing/oauth_connections.html billing/tests/test_oauth_consent.py billing/tests/test_oauth_adapter.py
git commit -m "feat: 152-FZ consent gate and connections page"
```

---

### Task 4: Privacy policy page

**Files:**
- Create: `billing/templates/billing/privacy_policy.html`
- Modify: `billing/views.py` (append `privacy_policy` view)
- Modify: `billing/urls.py` (append route)
- Modify: `billing/templates/billing/base.html` (footer link)
- Test: `billing/tests/test_privacy_policy.py`

**Interfaces:**
- Produces: view `privacy_policy` at url name `privacy_policy`, path `/privacy/`, reachable without login.

- [ ] **Step 1: Write the failing test**

`billing/tests/test_privacy_policy.py`:

```python
import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

def test_privacy_policy_reachable_without_login():
    resp = Client().get("/privacy/")
    assert resp.status_code == 200
    html = resp.content.decode()
    for phrase in ("Оператор", "Яндекс", "VK", "Госуслуги", "согласие",
                   "срок хранения", "Роскомнадзор"):
        assert phrase in html, f"missing: {phrase}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest billing/tests/test_privacy_policy.py -v`
Expected: FAIL with 404.

- [ ] **Step 3: Implement the view**

In `billing/views.py`, add (no `@login_required` — must be publicly reachable):

```python
def privacy_policy(request):
    return render(request, "billing/privacy_policy.html", {})
```

- [ ] **Step 4: Wire the url**

In `billing/urls.py`, add:

```python
    path("privacy/", views.privacy_policy, name="privacy_policy"),
```

- [ ] **Step 5: Write the template**

`billing/templates/billing/privacy_policy.html` — the bracketed fields are facts only the landlord knows (organization details, exact retention periods, contact channel); fill them in before relying on this page to satisfy ст. 18.1. This text is a starting draft, not a substitute for review by a qualified specialist:

```html
{% extends "billing/base.html" %}
{% block title %}Политика обработки персональных данных{% endblock %}
{% block content %}
<h1 class="mb-6 text-3xl font-bold">Политика обработки персональных данных</h1>
<section class="space-y-4 rounded-lg border border-line bg-white p-5 text-sm leading-relaxed">
  <p>
    Настоящая политика определяет порядок обработки персональных данных
    пользователей сайта domiq-ufa.ru в соответствии с Федеральным законом
    от 27.07.2006 № 152-ФЗ «О персональных данных».
  </p>

  <h2 class="text-lg font-bold">1. Оператор персональных данных</h2>
  <p>
    Оператором является [ФИО арендодателя / ИП, ИНН/ОГРНИП], контакт для
    обращений по вопросам персональных данных: [email или телефон].
  </p>

  <h2 class="text-lg font-bold">2. Какие данные обрабатываются</h2>
  <p>
    ФИО, логин, показания счётчиков и начисления, скан-копия договора
    аренды, чеки об оплате — вносятся арендодателем или самим жильцом
    при использовании личного кабинета. При подключении входа через
    Яндекс ID, VK ID или Госуслуги дополнительно обрабатывается
    идентификатор учётной записи выбранного сервиса и, если сервис их
    передаёт, имя и адрес электронной почты.
  </p>

  <h2 class="text-lg font-bold">3. Цели обработки</h2>
  <p>
    Начисление платы за коммунальные услуги, приём и подтверждение оплаты,
    предоставление доступа к личному кабинету, включая повторный вход через
    подключённый способ входа.
  </p>

  <h2 class="text-lg font-bold">4. Срок хранения</h2>
  <p>
    Данные хранятся на протяжении действия договора аренды и [N] лет после
    его окончания, либо до отзыва согласия, если это не противоречит
    обязательствам оператора по иным законам.
  </p>

  <h2 class="text-lg font-bold">5. Передача третьим лицам</h2>
  <p>
    Данные не передаются третьим лицам, за исключением случаев, прямо
    предусмотренных законодательством РФ.
  </p>

  <h2 class="text-lg font-bold">6. Права субъекта персональных данных</h2>
  <p>
    Вы вправе запросить сведения об обработке ваших персональных данных,
    их уточнение, блокирование или уничтожение, а также отозвать согласие,
    обратившись по контакту, указанному в разделе 1. Вы также вправе
    обратиться в Роскомнадзор, если считаете, что ваши права нарушены.
  </p>

  <h2 class="text-lg font-bold">7. Отзыв согласия на вход через внешние сервисы</h2>
  <p>
    Отключить привязанный способ входа (Яндекс ID, VK ID, Госуслуги) можно,
    обратившись к арендодателю; логин и пароль продолжают работать
    независимо от подключённых способов входа.
  </p>

  <p class="text-xs text-ink-soft">Версия политики: [ДАТА]</p>
</section>
{% endblock %}
```

- [ ] **Step 6: Add a footer link**

In `billing/templates/billing/base.html`, inside `<footer>`, after the `domiq-ufa.ru` text:

```html
  <div class="mt-1"><a href="{% url 'privacy_policy' %}" class="underline">Политика обработки персональных данных</a></div>
```

- [ ] **Step 7: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest billing/tests/test_privacy_policy.py -v`
Expected: PASS

- [ ] **Step 8: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all green.

- [ ] **Step 9: Commit**

```powershell
git add billing/views.py billing/urls.py billing/templates/billing/privacy_policy.html billing/templates/billing/base.html billing/tests/test_privacy_policy.py
git commit -m "feat: public privacy policy page (152-FZ st.18.1)"
```

---

### Task 5: Yandex + VK provider settings and login page buttons

**Files:**
- Modify: `config/settings.py` (append `SOCIALACCOUNT_PROVIDERS`)
- Modify: `billing/templates/registration/login.html`
- Modify: `deploy/.env.example`
- Test: extend `billing/tests/test_oauth_providers.py`

**Interfaces:**
- Consumes: env vars `YANDEX_CLIENT_ID`, `YANDEX_CLIENT_SECRET`, `VK_CLIENT_ID`, `VK_CLIENT_SECRET`.
- Produces: `settings.SOCIALACCOUNT_PROVIDERS["yandex"]` / `["vk"]` app config dicts; login page renders three provider links.

- [ ] **Step 1: Write the failing tests**

Append to `billing/tests/test_oauth_providers.py`:

```python
def test_login_page_shows_all_three_provider_buttons():
    resp = Client().get("/login/")
    html = resp.content.decode()
    assert "Яндекс" in html
    assert "VK" in html
    assert "Госуслуги" in html

def test_yandex_login_url_redirects_toward_provider_not_404():
    resp = Client().get("/accounts/yandex/login/")
    assert resp.status_code == 302
    assert resp.status_code != 404

def test_vk_login_url_redirects_toward_provider_not_404():
    resp = Client().get("/accounts/vk/login/")
    assert resp.status_code == 302
    assert resp.status_code != 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest billing/tests/test_oauth_providers.py -v`
Expected: the three new tests FAIL (login page has no provider buttons yet; `/accounts/yandex/login/` and `/accounts/vk/login/` 404 or error without `SOCIALACCOUNT_PROVIDERS` configured).

- [ ] **Step 3: Add provider settings**

In `config/settings.py`, add near the `TELEGRAM_*` settings at the bottom:

```python
# OAuth providers. Client credentials come from each provider's own app
# registration console; test values are fine for local dev (the redirect
# still 302s toward the real provider — only completing a real login
# requires real, registered credentials).
SOCIALACCOUNT_PROVIDERS = {
    "yandex": {
        "APP": {
            "client_id": os.environ.get("YANDEX_CLIENT_ID", ""),
            "secret": os.environ.get("YANDEX_CLIENT_SECRET", ""),
        },
    },
    "vk": {
        "APP": {
            "client_id": os.environ.get("VK_CLIENT_ID", ""),
            "secret": os.environ.get("VK_CLIENT_SECRET", ""),
        },
    },
    "esia": {
        "APP": {
            "client_id": os.environ.get("ESIA_CLIENT_ID", ""),
            "secret": os.environ.get("ESIA_CLIENT_SECRET", ""),
        },
        # Deliberately minimal: broader ESIA scopes (full name, SNILS, email)
        # require every authorization request to carry a PKCS#7 signature
        # made with a GOST-2012-256 certificate registered with the
        # ministry. "openid" alone (just a stable person identifier) avoids
        # that requirement entirely — see the design spec.
        "SCOPE": ["openid"],
    },
}

# Госуслуги (ESIA) sandbox by default — fail obviously rather than talking
# to production ESIA from a misconfigured deployment. Switch to
# https://esia.gosuslugi.ru once accredited with real production credentials.
ESIA_BASE_URL = os.environ.get("ESIA_BASE_URL", "https://esia-portal1.test.gosuslugi.ru")
```

- [ ] **Step 4: Add the login page buttons**

In `billing/templates/registration/login.html`, add `{% load socialaccount %}` after the existing `{% load crispy_forms_tags %}` line, and add this block just before `{% endblock %}` (after the closing `</section>` of the password form, before the final `<p>` about login/password being landlord-issued):

```html
  <div class="mt-6 space-y-2">
    <p class="text-center text-xs text-ink-soft">или войдите через:</p>
    <a href="{% provider_login_url 'yandex' %}"
       class="block w-full rounded border border-line px-4 py-2 text-center text-sm hover:border-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">Яндекс ID</a>
    <a href="{% provider_login_url 'vk' %}"
       class="block w-full rounded border border-line px-4 py-2 text-center text-sm hover:border-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">VK ID</a>
    <a href="{% provider_login_url 'esia' %}"
       class="block w-full rounded border border-line px-4 py-2 text-center text-sm hover:border-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">Госуслуги</a>
  </div>
```

- [ ] **Step 5: Add `.env.example` entries**

In `deploy/.env.example`, after the `TELEGRAM_*` lines:

```
# OAuth login (additive to password login). Each provider's console:
#   Yandex: https://oauth.yandex.ru/client/new
#   VK:     https://id.vk.com/business/go
#   Gosuslugi (ESIA): requires org accreditation via Rostelecom/Minsvyaz —
#     see docs/superpowers/specs/2026-07-27-oauth-login-design.md
YANDEX_CLIENT_ID=
YANDEX_CLIENT_SECRET=
VK_CLIENT_ID=
VK_CLIENT_SECRET=
ESIA_CLIENT_ID=
ESIA_CLIENT_SECRET=
ESIA_BASE_URL=https://esia-portal1.test.gosuslugi.ru
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest billing/tests/test_oauth_providers.py -v`
Expected: all PASS (the `esia` provider test is added in Task 6 — this task's 3 new tests plus Task 1's test all pass now; the app is registered as `billing.esia_provider` in `INSTALLED_APPS` since Task 1, but its provider class isn't registered with allauth's registry until Task 6, so don't add an `/accounts/esia/login/` test yet).

- [ ] **Step 7: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all green.

- [ ] **Step 8: Commit**

```powershell
git add config/settings.py billing/templates/registration/login.html deploy/.env.example billing/tests/test_oauth_providers.py
git commit -m "feat: Yandex ID and VK ID login buttons and settings"
```

---

### Task 6: Госуслуги (ESIA) custom OAuth2 provider

**Files:**
- Create: `billing/esia_provider/__init__.py`
- Create: `billing/esia_provider/apps.py`
- Create: `billing/esia_provider/provider.py`
- Create: `billing/esia_provider/views.py`
- Create: `billing/esia_provider/urls.py`
- Modify: `config/settings.py` (add `"billing.esia_provider"` to `INSTALLED_APPS`)
- Test: `billing/tests/test_esia_provider.py`

**Interfaces:**
- Consumes: `settings.ESIA_BASE_URL`, `settings.SOCIALACCOUNT_PROVIDERS["esia"]["APP"]` (Task 5).
- Produces: `ESIAProvider(OAuth2Provider)` with `id = "esia"`, registered with allauth's provider registry on app load. `ESIAOAuth2Adapter(OAuth2Adapter)` with `authorize_url`/`access_token_url` built from `ESIA_BASE_URL`, and `complete_login()` that decodes (without signature verification) the identity token's `oid`/`sub` claim.

**Known limitation, called out again here:** `_decode_id_token_payload` below reads the JWT payload by base64-decoding it directly — it does **not** verify the token's cryptographic signature. Real ESIA integration requires validating against ESIA's published signing certificate once your organization is accredited; until then, treat any ESIA login as provisional. This is a deliberate, documented scope limit, not an oversight — production hardening is explicitly out of scope until real ESIA sandbox/production credentials exist to test against.

- [ ] **Step 1: Write the failing tests**

`billing/tests/test_esia_provider.py`:

```python
import base64
import json
from billing.esia_provider.provider import ESIAProvider
from billing.esia_provider.views import ESIAOAuth2Adapter, _decode_id_token_payload

def test_esia_provider_registered_with_id():
    assert ESIAProvider.id == "esia"
    assert ESIAProvider.name == "Госуслуги"

def test_decode_id_token_payload_reads_claims_without_verifying_signature():
    payload = {"sub": "1000000001", "urn:esia:sbj_id": "1000000001"}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    fake_jwt = f"headerpart.{payload_b64}.signaturepart"
    claims = _decode_id_token_payload(fake_jwt)
    assert claims["sub"] == "1000000001"

def test_authorize_and_token_urls_use_esia_base_url(settings):
    settings.ESIA_BASE_URL = "https://esia-portal1.test.gosuslugi.ru"
    adapter = ESIAOAuth2Adapter(request=None)
    assert adapter.authorize_url == "https://esia-portal1.test.gosuslugi.ru/aas/oauth2/ac"
    assert adapter.access_token_url == "https://esia-portal1.test.gosuslugi.ru/aas/oauth2/te"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest billing/tests/test_esia_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'billing.esia_provider.provider'`.

- [ ] **Step 3: Add the app to `INSTALLED_APPS` now that the package will exist**

In `config/settings.py`, add `"billing.esia_provider"` to `INSTALLED_APPS`, after `"billing"`:

```python
    "billing",
    "billing.esia_provider",
]
```

- [ ] **Step 4: Implement**

`billing/esia_provider/__init__.py`:

```python
```

(empty file — marks the directory as a package)

`billing/esia_provider/provider.py`:

```python
from allauth.socialaccount.providers.base import ProviderAccount
from allauth.socialaccount.providers.oauth2.provider import OAuth2Provider

class ESIAAccount(ProviderAccount):
    def to_str(self):
        return self.account.extra_data.get("oid") or super().to_str()

class ESIAProvider(OAuth2Provider):
    id = "esia"
    name = "Госуслуги"
    account_class = ESIAAccount

    def extract_uid(self, data):
        return str(data["oid"])

    def extract_common_fields(self, data):
        return {"username": data.get("oid", "")}

provider_classes = [ESIAProvider]
```

`billing/esia_provider/views.py`:

```python
import base64
import json
from django.conf import settings
from allauth.socialaccount.providers.oauth2.views import (
    OAuth2Adapter, OAuth2CallbackView, OAuth2LoginView,
)
from .provider import ESIAProvider

def _decode_id_token_payload(id_token):
    """Decode the JWT payload WITHOUT verifying its signature.

    KNOWN LIMITATION: production use must verify against ESIA's published
    signing certificate before trusting this as authenticated identity —
    not implemented here. See
    docs/superpowers/specs/2026-07-27-oauth-login-design.md.
    """
    payload_b64 = id_token.split(".")[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))

class ESIAOAuth2Adapter(OAuth2Adapter):
    provider_id = ESIAProvider.id

    @property
    def authorize_url(self):
        return f"{settings.ESIA_BASE_URL}/aas/oauth2/ac"

    @property
    def access_token_url(self):
        return f"{settings.ESIA_BASE_URL}/aas/oauth2/te"

    def complete_login(self, request, app, token, **kwargs):
        id_token = kwargs.get("response", {}).get("id_token", "")
        claims = _decode_id_token_payload(id_token) if id_token else {}
        oid = claims.get("urn:esia:sbj_id") or claims.get("sub") or ""
        extra_data = {"oid": oid, **claims}
        return self.get_provider().sociallogin_from_response(request, extra_data)

oauth2_login = OAuth2LoginView.adapter_view(ESIAOAuth2Adapter)
oauth2_callback = OAuth2CallbackView.adapter_view(ESIAOAuth2Adapter)
```

`billing/esia_provider/urls.py`:

```python
from allauth.socialaccount.providers.oauth2.urls import default_urlpatterns
from .provider import ESIAProvider

urlpatterns = default_urlpatterns(ESIAProvider)
```

`billing/esia_provider/apps.py`:

```python
from allauth.socialaccount.apps import SocialAccountConfig

class ESIAProviderConfig(SocialAccountConfig):
    name = "billing.esia_provider"

    def ready(self):
        super().ready()
        from allauth.socialaccount.providers import registry
        from .provider import ESIAProvider
        registry.register(ESIAProvider)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest billing/tests/test_esia_provider.py -v`
Expected: PASS (3 passed). If `ESIAOAuth2Adapter(request=None)` errors on construction because the base `OAuth2Adapter.__init__` requires a real request object, change the test to construct it as `ESIAOAuth2Adapter.__new__(ESIAOAuth2Adapter)` instead (bypassing `__init__`, since the two properties under test only read `settings.ESIA_BASE_URL` and don't touch `self.request`) — note this adjustment in the task report if you had to make it.

- [ ] **Step 6: Add the ESIA login test now that the provider is registered**

Append to `billing/tests/test_oauth_providers.py`:

```python
def test_esia_login_url_redirects_toward_provider_not_404():
    resp = Client().get("/accounts/esia/login/")
    assert resp.status_code == 302
    assert resp.status_code != 404
```

Run: `.venv\Scripts\python.exe -m pytest billing/tests/test_oauth_providers.py -v`
Expected: PASS, including this new test.

- [ ] **Step 7: Run the full suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all green.

- [ ] **Step 8: Commit**

```powershell
git add billing/esia_provider billing/tests/test_esia_provider.py billing/tests/test_oauth_providers.py
git commit -m "feat: Gosuslugi (ESIA) OAuth2 provider (openid scope, unverified id_token)"
```

---

## Manual smoke test (not part of the automated suite)

Real OAuth handshakes against live Yandex/VK/ESIA servers require real
registered app credentials and network access — they are not part of CI.
Once you have real `YANDEX_CLIENT_ID`/`SECRET` and `VK_CLIENT_ID`/`SECRET`
in `.env`:

1. Log in with a tenant's password at `/login/`.
2. Visit «Способы входа», tick the consent checkbox, submit.
3. Click «Подключить» next to Яндекс ID — complete the real OAuth flow —
   confirm you land back on «Способы входа» showing «Подключено».
4. Log out, then log back in via the «Яндекс ID» button on `/login/` —
   confirm it logs into the same tenant account.
5. Repeat for VK ID.
6. Confirm an anonymous click on `/accounts/yandex/login/` for an
   **unconnected** Yandex account lands on the «не привязан» page, not a
   signup form.

ESIA cannot be smoke-tested until the landlord has real, accredited ESIA
credentials — skip until then.
