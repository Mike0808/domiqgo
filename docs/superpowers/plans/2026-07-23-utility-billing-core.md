# Utility Billing Core — Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the working billing core — a Django app where the landlord manages apartments, tenants, and time-versioned tariffs, tenants log in to submit meter readings and see an itemized monthly bill with history, and the rental agreement is on file.

**Architecture:** A single Django project (`config`) with one app (`billing`). A framework-independent **pure calculation core** turns readings + tariffs into bill line items; a thin **statement service** wires the ORM to that core and persists results. The landlord uses Django admin; tenants use server-rendered, mobile-first Russian pages. Money is `Decimal` throughout.

**Tech Stack:** Python 3.12+, Django 5.1, SQLite (dev) / PostgreSQL (prod), pytest + pytest-django, WhiteNoise, gunicorn (prod).

**Follow-up (Plan 2, not built here):** `Payment` model, shared receipt-intake service, web receipt upload, `MessengerAdapter` + Telegram + MAX adapters, and the admin approval console. Plan 1 already includes the fields those depend on (`Tenant.messenger_*`, `Tenant.link_code`, `MonthlyStatement.status` with a `pending` value) so Plan 2 adds no rework.

## Global Constraints

- Python **3.12+**, Django **5.1.x**.
- `LANGUAGE_CODE = 'ru'`, `TIME_ZONE = 'Asia/Yekaterinburg'` (Ufa, UTC+5), `USE_TZ = True`.
- All user-facing text (labels, templates, messages) in **Russian**. Currency shown as **₽**.
- All money is `Decimal`, quantized to `0.01` with `ROUND_HALF_UP`. Tariff rates stored at 4 decimal places.
- A tenant may see and edit **only their own** apartment's data. Enforce on every tenant view.
- TDD: write the failing test first, watch it fail, implement minimally, watch it pass, commit.
- `period` is always a `date` set to the **first day of the month** (e.g. `date(2026, 7, 1)`).

---

## File Structure

```
local-rent/
  manage.py
  requirements.txt
  pytest.ini
  .gitignore
  config/
    __init__.py
    settings.py          # env-driven; SQLite default, Postgres via env
    urls.py              # admin + billing urls
    wsgi.py  asgi.py
  billing/
    __init__.py
    apps.py
    models.py            # Apartment, Tenant, Tariff, MeterReading, MonthlyStatement, Document
    admin.py             # landlord back-office
    views.py             # tenant portal
    urls.py
    forms.py             # meter-reading entry form
    services/
      __init__.py
      calculation.py     # PURE core: compute_statement (no Django imports)
      statements.py      # ORM <-> core glue: generate_statement
    templates/
      registration/login.html
      billing/base.html
      billing/current_month.html
      billing/history.html
      billing/documents.html
    migrations/
    tests/
      __init__.py
      test_calculation.py
      test_statements.py
      test_models.py
      test_portal.py
```

**Responsibilities:** `calculation.py` is pure and holds all billing math. `statements.py` reads the ORM, selects tariffs by period, and calls the core. `views.py`/`forms.py` are the tenant portal. `admin.py` is the landlord back-office. Files that change together live together under `billing/`.

---

### Task 1: Project scaffold, settings, tooling

**Files:**
- Create: `requirements.txt`, `.gitignore`, `pytest.ini`, `manage.py`, `config/*`, `billing/apps.py`, `billing/__init__.py`, `billing/services/__init__.py`, `billing/tests/__init__.py`
- Test: `billing/tests/test_smoke.py`

**Interfaces:**
- Produces: an installed `billing` app, a runnable Django project, working `pytest`.

- [ ] **Step 1: Create `requirements.txt`**

```
Django==5.1.*
pytest==8.*
pytest-django==4.*
whitenoise==6.*
python-dotenv==1.*
# prod only (do not install in dev): psycopg[binary]==3.*, gunicorn==23.*
```

- [ ] **Step 2: Create and activate a virtualenv, install deps**

Run (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
Expected: Django and pytest install without error.

- [ ] **Step 3: Scaffold the project and app**

Run:
```powershell
django-admin startproject config .
python manage.py startapp billing
New-Item -ItemType Directory billing\services | Out-Null
New-Item -ItemType File billing\services\__init__.py | Out-Null
New-Item -ItemType Directory billing\tests | Out-Null
New-Item -ItemType File billing\tests\__init__.py | Out-Null
```
Then delete the single-file `billing/tests.py` if `startapp` created it.

- [ ] **Step 4: Configure `config/settings.py`**

Replace the locale/tz/app blocks so they read:
```python
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = os.environ.get("DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "billing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

LANGUAGE_CODE = "ru"
TIME_ZONE = "Asia/Yekaterinburg"
USE_I18N = True
USE_TZ = True

if os.environ.get("DB_NAME"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ.get("DB_USER", ""),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }}
else:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }}

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "current_month"
LOGOUT_REDIRECT_URL = "login"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
```
Keep the existing `TEMPLATES`, `AUTH_PASSWORD_VALIDATORS`, `ROOT_URLCONF`, `WSGI_APPLICATION` blocks that `startproject` generated.

- [ ] **Step 5: Create `pytest.ini`**

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = test_*.py
```

- [ ] **Step 6: Create `.gitignore`**

```
.venv/
__pycache__/
*.pyc
db.sqlite3
.env
media/
staticfiles/
```

- [ ] **Step 7: Write a smoke test** — `billing/tests/test_smoke.py`

```python
def test_settings_locale():
    from django.conf import settings
    assert settings.LANGUAGE_CODE == "ru"
    assert settings.TIME_ZONE == "Asia/Yekaterinburg"
```

- [ ] **Step 8: Run checks and the smoke test**

Run:
```powershell
python manage.py check
pytest billing/tests/test_smoke.py -v
```
Expected: `check` reports no issues; test PASSES.

- [ ] **Step 9: Commit**

```powershell
git add -A
git commit -m "chore: scaffold Django project, billing app, tooling"
```

---

### Task 2: Pure calculation core (TDD)

**Files:**
- Create: `billing/services/calculation.py`
- Test: `billing/tests/test_calculation.py`

**Interfaces:**
- Produces:
  - `class MeterType(str, Enum)` with `SINGLE = "single"`, `DUAL = "dual"`.
  - `@dataclass(frozen=True) class ApartmentConfig` with fields: `electricity_meter_type: MeterType`, `has_cold_water: bool`, `has_hot_water: bool`, `has_sewage: bool`, `rent: Decimal`, `internet: Decimal`, `other_fixed: Decimal`.
  - `@dataclass(frozen=True) class LineItem` with fields: `code: str`, `label: str`, `quantity: Decimal | None`, `rate: Decimal`, `amount: Decimal`.
  - `class MissingTariffError(Exception)`.
  - `def compute_statement(config: ApartmentConfig, current: dict[str, Decimal], previous: dict[str, Decimal], tariffs: dict[str, Decimal]) -> tuple[list[LineItem], Decimal]`.
- Meter keys used everywhere: `"cold_water"`, `"hot_water"`, `"electricity_single"`, `"electricity_day"`, `"electricity_night"`. Tariff keys add `"sewage"`.

- [ ] **Step 1: Write failing tests** — `billing/tests/test_calculation.py`

```python
from decimal import Decimal
import pytest
from billing.services.calculation import (
    ApartmentConfig, MeterType, MissingTariffError, compute_statement,
)

def cfg(meter=MeterType.SINGLE, cold=True, hot=True, sewage=True,
        rent="0", internet="0", other="0"):
    return ApartmentConfig(
        electricity_meter_type=meter, has_cold_water=cold, has_hot_water=hot,
        has_sewage=sewage, rent=Decimal(rent), internet=Decimal(internet),
        other_fixed=Decimal(other),
    )

TARIFFS = {
    "cold_water": Decimal("48.15"), "hot_water": Decimal("205.30"),
    "sewage": Decimal("36.40"), "electricity_single": Decimal("4.87"),
    "electricity_day": Decimal("5.62"), "electricity_night": Decimal("2.81"),
}

def test_single_meter_full_bill():
    lines, total = compute_statement(
        cfg(rent="20000", internet="700"),
        current={"cold_water": Decimal("110"), "hot_water": Decimal("55"),
                 "electricity_single": Decimal("1500")},
        previous={"cold_water": Decimal("100"), "hot_water": Decimal("50"),
                  "electricity_single": Decimal("1400")},
        tariffs=TARIFFS,
    )
    by = {l.code: l for l in lines}
    assert by["cold_water"].amount == Decimal("481.50")     # 10 * 48.15
    assert by["hot_water"].amount == Decimal("1026.50")     # 5 * 205.30
    assert by["sewage"].amount == Decimal("546.00")         # (10+5) * 36.40
    assert by["electricity_single"].amount == Decimal("487.00")  # 100 * 4.87
    assert by["rent"].amount == Decimal("20000.00")
    assert by["internet"].amount == Decimal("700.00")
    assert by["rent"].quantity is None
    assert total == Decimal("23241.00")

def test_dual_meter_splits_day_night():
    lines, total = compute_statement(
        cfg(meter=MeterType.DUAL, cold=False, hot=False, sewage=False),
        current={"electricity_day": Decimal("1200"), "electricity_night": Decimal("800")},
        previous={"electricity_day": Decimal("1100"), "electricity_night": Decimal("700")},
        tariffs=TARIFFS,
    )
    by = {l.code: l for l in lines}
    assert by["electricity_day"].amount == Decimal("562.00")    # 100 * 5.62
    assert by["electricity_night"].amount == Decimal("281.00")  # 100 * 2.81
    assert "electricity_single" not in by
    assert total == Decimal("843.00")

def test_missing_tariff_raises():
    with pytest.raises(MissingTariffError):
        compute_statement(
            cfg(hot=False, sewage=False, meter=MeterType.SINGLE),
            current={"cold_water": Decimal("110"), "electricity_single": Decimal("1500")},
            previous={"cold_water": Decimal("100"), "electricity_single": Decimal("1400")},
            tariffs={"electricity_single": Decimal("4.87")},  # no cold_water tariff
        )

def test_reading_going_backward_raises():
    with pytest.raises(ValueError):
        compute_statement(
            cfg(hot=False, sewage=False),
            current={"cold_water": Decimal("90"), "electricity_single": Decimal("1500")},
            previous={"cold_water": Decimal("100"), "electricity_single": Decimal("1400")},
            tariffs=TARIFFS,
        )

def test_zero_fixed_charges_omitted():
    lines, _ = compute_statement(
        cfg(cold=False, hot=False, sewage=False),
        current={"electricity_single": Decimal("50")},
        previous={"electricity_single": Decimal("50")},
        tariffs=TARIFFS,
    )
    assert all(l.code not in ("rent", "internet", "other_fixed") for l in lines)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest billing/tests/test_calculation.py -v`
Expected: FAIL with `ModuleNotFoundError: billing.services.calculation`.

- [ ] **Step 3: Implement `billing/services/calculation.py`**

```python
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

CENT = Decimal("0.01")

def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)

class MeterType(str, Enum):
    SINGLE = "single"
    DUAL = "dual"

class MissingTariffError(Exception):
    """Raised when no tariff is available for a required utility."""

@dataclass(frozen=True)
class ApartmentConfig:
    electricity_meter_type: MeterType
    has_cold_water: bool
    has_hot_water: bool
    has_sewage: bool
    rent: Decimal
    internet: Decimal
    other_fixed: Decimal

@dataclass(frozen=True)
class LineItem:
    code: str
    label: str
    quantity: Decimal | None
    rate: Decimal
    amount: Decimal

LABELS = {
    "cold_water": "Холодная вода",
    "hot_water": "Горячая вода",
    "sewage": "Водоотведение",
    "electricity_single": "Электроэнергия",
    "electricity_day": "Электроэнергия (день)",
    "electricity_night": "Электроэнергия (ночь)",
    "rent": "Аренда",
    "internet": "Интернет",
    "other_fixed": "Прочее",
}

def _consumption(meter: str, current: dict, previous: dict) -> Decimal:
    cur = current[meter]
    prev = previous.get(meter, Decimal("0"))
    used = cur - prev
    if used < 0:
        raise ValueError(f"Показание по счётчику «{meter}» уменьшилось: {prev} -> {cur}")
    return used

def _tariff(code: str, tariffs: dict) -> Decimal:
    try:
        return tariffs[code]
    except KeyError:
        raise MissingTariffError(f"Нет тарифа для услуги «{code}»")

def _metered_line(code, current, previous, tariffs) -> tuple[LineItem, Decimal]:
    qty = _consumption(code, current, previous)
    rate = _tariff(code, tariffs)
    return LineItem(code, LABELS[code], qty, rate, _money(qty * rate)), qty

def compute_statement(config, current, previous, tariffs):
    lines: list[LineItem] = []
    cold = hot = Decimal("0")

    if config.has_cold_water:
        line, cold = _metered_line("cold_water", current, previous, tariffs)
        lines.append(line)
    if config.has_hot_water:
        line, hot = _metered_line("hot_water", current, previous, tariffs)
        lines.append(line)
    if config.has_sewage:
        volume = cold + hot
        rate = _tariff("sewage", tariffs)
        lines.append(LineItem("sewage", LABELS["sewage"], volume, rate, _money(volume * rate)))

    if config.electricity_meter_type == MeterType.SINGLE:
        line, _ = _metered_line("electricity_single", current, previous, tariffs)
        lines.append(line)
    else:
        for code in ("electricity_day", "electricity_night"):
            line, _ = _metered_line(code, current, previous, tariffs)
            lines.append(line)

    for code, amount in (("rent", config.rent), ("internet", config.internet),
                         ("other_fixed", config.other_fixed)):
        if amount and amount > 0:
            lines.append(LineItem(code, LABELS[code], None, _money(amount), _money(amount)))

    total = _money(sum((l.amount for l in lines), Decimal("0")))
    return lines, total
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest billing/tests/test_calculation.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add billing/services/calculation.py billing/tests/test_calculation.py
git commit -m "feat: pure billing calculation core with TDD coverage"
```

---

### Task 3: Domain models & migrations

**Files:**
- Modify: `billing/models.py`
- Test: `billing/tests/test_models.py`

**Interfaces:**
- Produces models `Apartment`, `Tenant`, `Tariff`, `MeterReading`, `MonthlyStatement`, `Document`.
- `Apartment.SINGLE = "single"`, `Apartment.DUAL = "dual"`.
- `Tariff.UTILITY_CHOICES` covers keys: `cold_water`, `hot_water`, `sewage`, `electricity_single`, `electricity_day`, `electricity_night`.
- `MonthlyStatement.UNPAID/PENDING/PAID = "unpaid"/"pending"/"paid"`.
- `MeterReading` unique on `(apartment, period, meter)`; `MonthlyStatement` unique on `(apartment, period)`.

- [ ] **Step 1: Write failing tests** — `billing/tests/test_models.py`

```python
from datetime import date
from decimal import Decimal
import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError
from billing.models import (
    Apartment, Tenant, Tariff, MeterReading, MonthlyStatement,
)

pytestmark = pytest.mark.django_db

def test_apartment_defaults():
    a = Apartment.objects.create(label="ул. Ленина 1, кв. 5")
    assert a.electricity_meter_type == Apartment.SINGLE
    assert a.has_cold_water and a.has_hot_water and a.has_sewage
    assert a.rent == Decimal("0")

def test_reading_unique_per_meter_period():
    a = Apartment.objects.create(label="кв. 1")
    MeterReading.objects.create(apartment=a, period=date(2026, 7, 1),
                                meter="cold_water", value=Decimal("100"))
    with pytest.raises(IntegrityError):
        MeterReading.objects.create(apartment=a, period=date(2026, 7, 1),
                                    meter="cold_water", value=Decimal("101"))

def test_statement_unique_per_period():
    a = Apartment.objects.create(label="кв. 2")
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1))
    with pytest.raises(IntegrityError):
        MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1))

def test_tenant_links_user_and_apartment():
    a = Apartment.objects.create(label="кв. 3")
    u = User.objects.create_user("ivanov", password="x")
    t = Tenant.objects.create(user=u, apartment=a, full_name="Иванов И.И.")
    assert t.apartment == a
    assert u.tenant == t
    assert t.messenger_platform == ""   # Plan 2 hook present but empty
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest billing/tests/test_models.py -v`
Expected: FAIL with `ImportError` (models not defined).

- [ ] **Step 3: Implement `billing/models.py`**

```python
from decimal import Decimal
from django.conf import settings
from django.db import models

class Apartment(models.Model):
    SINGLE = "single"
    DUAL = "dual"
    METER_CHOICES = [(SINGLE, "Однотарифный"), (DUAL, "День/Ночь")]

    label = models.CharField("Квартира", max_length=200)
    electricity_meter_type = models.CharField(
        "Тип счётчика электроэнергии", max_length=10,
        choices=METER_CHOICES, default=SINGLE)
    has_cold_water = models.BooleanField("Холодная вода", default=True)
    has_hot_water = models.BooleanField("Горячая вода", default=True)
    has_sewage = models.BooleanField("Водоотведение", default=True)
    rent = models.DecimalField("Аренда", max_digits=10, decimal_places=2, default=Decimal("0"))
    internet = models.DecimalField("Интернет", max_digits=10, decimal_places=2, default=Decimal("0"))
    other_fixed = models.DecimalField("Прочее", max_digits=10, decimal_places=2, default=Decimal("0"))

    class Meta:
        verbose_name = "Квартира"
        verbose_name_plural = "Квартиры"

    def __str__(self):
        return self.label

class Tenant(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="tenant")
    apartment = models.ForeignKey(Apartment, on_delete=models.PROTECT, related_name="tenants")
    full_name = models.CharField("ФИО", max_length=200, blank=True)
    # Plan 2 hooks:
    messenger_platform = models.CharField(max_length=10, blank=True)
    messenger_chat_id = models.CharField(max_length=64, blank=True)
    link_code = models.CharField(max_length=32, blank=True)

    class Meta:
        verbose_name = "Жилец"
        verbose_name_plural = "Жильцы"

    def __str__(self):
        return self.full_name or self.user.get_username()

class Tariff(models.Model):
    COLD = "cold_water"; HOT = "hot_water"; SEWAGE = "sewage"
    ESINGLE = "electricity_single"; EDAY = "electricity_day"; ENIGHT = "electricity_night"
    UTILITY_CHOICES = [
        (COLD, "Холодная вода"), (HOT, "Горячая вода"), (SEWAGE, "Водоотведение"),
        (ESINGLE, "Электроэнергия"), (EDAY, "Электроэнергия (день)"),
        (ENIGHT, "Электроэнергия (ночь)"),
    ]
    utility_type = models.CharField("Услуга", max_length=32, choices=UTILITY_CHOICES)
    rate = models.DecimalField("Тариф, ₽/ед.", max_digits=10, decimal_places=4)
    effective_from = models.DateField("Действует с")
    source_name = models.CharField("Источник", max_length=200, blank=True)
    source_url = models.URLField("Ссылка на источник", blank=True)

    class Meta:
        verbose_name = "Тариф"
        verbose_name_plural = "Тарифы"
        ordering = ["utility_type", "-effective_from"]

    def __str__(self):
        return f"{self.get_utility_type_display()} — {self.rate} (с {self.effective_from})"

class MeterReading(models.Model):
    apartment = models.ForeignKey(Apartment, on_delete=models.CASCADE, related_name="readings")
    period = models.DateField("Период")
    meter = models.CharField("Счётчик", max_length=32)
    value = models.DecimalField("Показание", max_digits=12, decimal_places=3)
    entered_by_tenant = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Показание"
        verbose_name_plural = "Показания"
        unique_together = [("apartment", "period", "meter")]
        ordering = ["-period", "meter"]

    def __str__(self):
        return f"{self.apartment} {self.period:%Y-%m} {self.meter}={self.value}"

class MonthlyStatement(models.Model):
    UNPAID = "unpaid"; PENDING = "pending"; PAID = "paid"
    STATUS_CHOICES = [(UNPAID, "Не оплачено"), (PENDING, "На проверке"), (PAID, "Оплачено")]

    apartment = models.ForeignKey(Apartment, on_delete=models.CASCADE, related_name="statements")
    period = models.DateField("Период")
    lines = models.JSONField("Строки начисления", default=list)
    total = models.DecimalField("Итого", max_digits=12, decimal_places=2, default=Decimal("0"))
    status = models.CharField("Статус", max_length=10, choices=STATUS_CHOICES, default=UNPAID)

    class Meta:
        verbose_name = "Начисление"
        verbose_name_plural = "Начисления"
        unique_together = [("apartment", "period")]
        ordering = ["-period"]

    def __str__(self):
        return f"{self.apartment} {self.period:%Y-%m} — {self.total} ₽"

def document_upload_path(instance, filename):
    return f"documents/tenant_{instance.tenant_id}/{filename}"

class Document(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="documents")
    file = models.FileField("Файл", upload_to=document_upload_path)
    title = models.CharField("Название", max_length=200, default="Договор аренды")
    uploaded_at = models.DateTimeField("Загружен", auto_now_add=True)

    class Meta:
        verbose_name = "Документ"
        verbose_name_plural = "Документы"

    def __str__(self):
        return self.title
```

- [ ] **Step 4: Make and apply migrations**

Run:
```powershell
python manage.py makemigrations billing
python manage.py migrate
```
Expected: one migration created and applied cleanly.

- [ ] **Step 5: Run model tests**

Run: `pytest billing/tests/test_models.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add billing/models.py billing/migrations billing/tests/test_models.py
git commit -m "feat: domain models for apartments, tenants, tariffs, readings, statements, documents"
```

---

### Task 4: Statement generation service (TDD)

**Files:**
- Create: `billing/services/statements.py`
- Test: `billing/tests/test_statements.py`

**Interfaces:**
- Consumes: `compute_statement`, `ApartmentConfig`, `MeterType` from Task 2; all models from Task 3.
- Produces:
  - `def meters_for(apartment) -> list[str]` — meter keys this apartment uses.
  - `def generate_statement(apartment, period: date) -> MonthlyStatement` — reads current readings for `period`, finds the most recent earlier period's readings as the baseline, selects each tariff effective on/before `period`, computes, and `update_or_create`s the `MonthlyStatement` (persisting `lines` as JSON-safe dicts and `total`). Preserves existing `status`.
  - `line_to_dict(line) -> dict` with keys `code, label, quantity, rate, amount` (Decimals serialized as strings; `quantity` may be `None`).

- [ ] **Step 1: Write failing tests** — `billing/tests/test_statements.py`

```python
from datetime import date
from decimal import Decimal
import pytest
from billing.models import Apartment, Tariff, MeterReading, MonthlyStatement
from billing.services.statements import generate_statement, meters_for

pytestmark = pytest.mark.django_db

def _tariffs(effective=date(2026, 7, 1)):
    data = {"cold_water": "48.15", "hot_water": "205.30", "sewage": "36.40",
            "electricity_single": "4.87"}
    for code, rate in data.items():
        Tariff.objects.create(utility_type=code, rate=Decimal(rate), effective_from=effective)

def _readings(apt, period, cold, hot, elec):
    MeterReading.objects.create(apartment=apt, period=period, meter="cold_water", value=Decimal(cold))
    MeterReading.objects.create(apartment=apt, period=period, meter="hot_water", value=Decimal(hot))
    MeterReading.objects.create(apartment=apt, period=period, meter="electricity_single", value=Decimal(elec))

def test_meters_for_single_vs_dual():
    a = Apartment.objects.create(label="кв", electricity_meter_type=Apartment.SINGLE)
    assert meters_for(a) == ["cold_water", "hot_water", "electricity_single"]
    a.electricity_meter_type = Apartment.DUAL
    assert meters_for(a) == ["cold_water", "hot_water", "electricity_day", "electricity_night"]

def test_generate_uses_previous_period_as_baseline():
    a = Apartment.objects.create(label="кв", rent=Decimal("20000"), internet=Decimal("700"))
    _tariffs()
    _readings(a, date(2026, 6, 1), "100", "50", "1400")
    _readings(a, date(2026, 7, 1), "110", "55", "1500")

    stmt = generate_statement(a, date(2026, 7, 1))

    assert stmt.total == Decimal("23241.00")
    by = {l["code"]: l for l in stmt.lines}
    assert by["cold_water"]["amount"] == "481.50"
    assert by["sewage"]["amount"] == "546.00"
    assert by["rent"]["quantity"] is None

def test_generate_selects_tariff_effective_for_period():
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False,
                                 electricity_meter_type=Apartment.SINGLE)
    Tariff.objects.create(utility_type="cold_water", rate=Decimal("40.00"), effective_from=date(2025, 7, 1))
    Tariff.objects.create(utility_type="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    Tariff.objects.create(utility_type="electricity_single", rate=Decimal("4.87"), effective_from=date(2025, 7, 1))
    MeterReading.objects.create(apartment=a, period=date(2026, 6, 1), meter="cold_water", value=Decimal("100"))
    MeterReading.objects.create(apartment=a, period=date(2026, 6, 1), meter="electricity_single", value=Decimal("0"))
    MeterReading.objects.create(apartment=a, period=date(2026, 7, 1), meter="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment=a, period=date(2026, 7, 1), meter="electricity_single", value=Decimal("0"))

    june = generate_statement(a, date(2026, 6, 1))   # baseline: none -> previous 0
    july = generate_statement(a, date(2026, 7, 1))   # baseline: June readings

    july_cold = {l["code"]: l for l in july.lines}["cold_water"]
    assert july_cold["rate"] == "48.1500"            # new tariff applied for July
    assert july_cold["amount"] == "481.50"           # (110-100) * 48.15

def test_generate_is_idempotent_and_keeps_status():
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    Tariff.objects.create(utility_type="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    Tariff.objects.create(utility_type="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    MeterReading.objects.create(apartment=a, period=date(2026, 7, 1), meter="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment=a, period=date(2026, 7, 1), meter="electricity_single", value=Decimal("1500"))

    stmt = generate_statement(a, date(2026, 7, 1))
    stmt.status = MonthlyStatement.PAID
    stmt.save()
    again = generate_statement(a, date(2026, 7, 1))
    assert again.pk == stmt.pk
    assert again.status == MonthlyStatement.PAID
    assert MonthlyStatement.objects.filter(apartment=a, period=date(2026, 7, 1)).count() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest billing/tests/test_statements.py -v`
Expected: FAIL with `ModuleNotFoundError: billing.services.statements`.

- [ ] **Step 3: Implement `billing/services/statements.py`**

```python
from datetime import date
from .calculation import ApartmentConfig, MeterType, compute_statement
from ..models import Apartment, Tariff, MeterReading, MonthlyStatement

def meters_for(apartment) -> list[str]:
    meters = []
    if apartment.has_cold_water:
        meters.append("cold_water")
    if apartment.has_hot_water:
        meters.append("hot_water")
    if apartment.electricity_meter_type == Apartment.SINGLE:
        meters.append("electricity_single")
    else:
        meters.extend(["electricity_day", "electricity_night"])
    return meters

def _readings_map(apartment, period) -> dict:
    return {r.meter: r.value
            for r in MeterReading.objects.filter(apartment=apartment, period=period)}

def _previous_readings(apartment, period) -> dict:
    prev = (MeterReading.objects
            .filter(apartment=apartment, period__lt=period)
            .order_by("-period").first())
    if prev is None:
        return {}
    return _readings_map(apartment, prev.period)

def _tariffs_for(period) -> dict:
    result = {}
    for code, _label in Tariff.UTILITY_CHOICES:
        t = (Tariff.objects
             .filter(utility_type=code, effective_from__lte=period)
             .order_by("-effective_from").first())
        if t is not None:
            result[code] = t.rate
    return result

def line_to_dict(line) -> dict:
    return {
        "code": line.code,
        "label": line.label,
        "quantity": None if line.quantity is None else str(line.quantity),
        "rate": str(line.rate),
        "amount": str(line.amount),
    }

def generate_statement(apartment, period: date) -> MonthlyStatement:
    config = ApartmentConfig(
        electricity_meter_type=MeterType(apartment.electricity_meter_type),
        has_cold_water=apartment.has_cold_water,
        has_hot_water=apartment.has_hot_water,
        has_sewage=apartment.has_sewage,
        rent=apartment.rent, internet=apartment.internet, other_fixed=apartment.other_fixed,
    )
    current = _readings_map(apartment, period)
    previous = _previous_readings(apartment, period)
    tariffs = _tariffs_for(period)
    lines, total = compute_statement(config, current, previous, tariffs)
    stmt, _created = MonthlyStatement.objects.update_or_create(
        apartment=apartment, period=period,
        defaults={"lines": [line_to_dict(l) for l in lines], "total": total},
    )
    return stmt
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest billing/tests/test_statements.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add billing/services/statements.py billing/tests/test_statements.py
git commit -m "feat: statement generation service with time-versioned tariff selection"
```

---

### Task 5: Admin back-office

**Files:**
- Modify: `billing/admin.py`
- Test: `billing/tests/test_admin.py`

**Interfaces:**
- Consumes: all models (Task 3), `generate_statement` (Task 4).
- Produces: registered admin for every model; a `DocumentInline` on `Tenant`; a `MonthlyStatement` admin action `regenerate_statements` that recomputes selected statements via `generate_statement`.

- [ ] **Step 1: Write failing test** — `billing/tests/test_admin.py`

```python
from datetime import date
from decimal import Decimal
import pytest
from django.contrib.auth.models import User
from django.test import Client
from billing.models import Apartment, Tariff, MeterReading, MonthlyStatement

pytestmark = pytest.mark.django_db

@pytest.fixture
def admin_client():
    User.objects.create_superuser("boss", "boss@example.com", "pass12345")
    c = Client()
    c.login(username="boss", password="pass12345")
    return c

def test_admin_apartment_changelist_loads(admin_client):
    Apartment.objects.create(label="кв. 10")
    resp = admin_client.get("/admin/billing/apartment/")
    assert resp.status_code == 200

def test_regenerate_action_recomputes_total(admin_client):
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    Tariff.objects.create(utility_type="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    Tariff.objects.create(utility_type="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    MeterReading.objects.create(apartment=a, period=date(2026, 7, 1), meter="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment=a, period=date(2026, 7, 1), meter="electricity_single", value=Decimal("1600"))
    stmt = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1))

    admin_client.post("/admin/billing/monthlystatement/", {
        "action": "regenerate_statements",
        "_selected_action": [str(stmt.pk)],
    })
    stmt.refresh_from_db()
    # No earlier period exists, so baseline is 0: 110*48.15 + 1600*4.87
    assert stmt.total == Decimal("13088.50")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest billing/tests/test_admin.py -v`
Expected: FAIL (models not registered / action missing → 404 or unchanged total).

- [ ] **Step 3: Implement `billing/admin.py`**

```python
from django.contrib import admin
from .models import (
    Apartment, Tenant, Tariff, MeterReading, MonthlyStatement, Document,
)
from .services.statements import generate_statement

@admin.register(Apartment)
class ApartmentAdmin(admin.ModelAdmin):
    list_display = ("label", "electricity_meter_type", "rent", "internet")
    list_filter = ("electricity_meter_type",)
    search_fields = ("label",)

class DocumentInline(admin.TabularInline):
    model = Document
    extra = 1

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "apartment")
    search_fields = ("full_name", "user__username")
    inlines = [DocumentInline]

@admin.register(Tariff)
class TariffAdmin(admin.ModelAdmin):
    list_display = ("utility_type", "rate", "effective_from", "source_name")
    list_filter = ("utility_type",)
    ordering = ("utility_type", "-effective_from")

@admin.register(MeterReading)
class MeterReadingAdmin(admin.ModelAdmin):
    list_display = ("apartment", "period", "meter", "value", "entered_by_tenant")
    list_filter = ("meter", "apartment")
    date_hierarchy = "period"

@admin.action(description="Пересчитать начисления")
def regenerate_statements(modeladmin, request, queryset):
    for stmt in queryset:
        generate_statement(stmt.apartment, stmt.period)

@admin.register(MonthlyStatement)
class MonthlyStatementAdmin(admin.ModelAdmin):
    list_display = ("apartment", "period", "total", "status")
    list_filter = ("status", "apartment")
    date_hierarchy = "period"
    actions = [regenerate_statements]

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "tenant", "uploaded_at")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest billing/tests/test_admin.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Manual sanity check (optional but recommended)**

Run:
```powershell
python manage.py createsuperuser
python manage.py runserver
```
Visit `http://127.0.0.1:8000/admin/`, confirm all six models appear in Russian.

- [ ] **Step 6: Commit**

```powershell
git add billing/admin.py billing/tests/test_admin.py
git commit -m "feat: admin back-office with statement regeneration action"
```

---

### Task 6: Tenant portal — auth, readings entry, bill, history, documents

**Files:**
- Create: `billing/forms.py`, `billing/urls.py`, `billing/templates/registration/login.html`, `billing/templates/billing/base.html`, `billing/templates/billing/current_month.html`, `billing/templates/billing/history.html`, `billing/templates/billing/documents.html`
- Modify: `billing/views.py`, `config/urls.py`
- Test: `billing/tests/test_portal.py`

**Interfaces:**
- Consumes: `meters_for`, `generate_statement` (Task 4); all models.
- Produces named URL routes: `login`, `logout`, `current_month`, `history`, `documents`. `current_month` (GET) shows a reading form for the current month's meters plus the latest statement; (POST) saves readings (`entered_by_tenant=True`) and regenerates the statement. A tenant only ever accesses their own apartment.

- [ ] **Step 1: Write failing tests** — `billing/tests/test_portal.py`

```python
from datetime import date
from decimal import Decimal
import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone
from billing.models import Apartment, Tenant, Tariff, MeterReading, MonthlyStatement

pytestmark = pytest.mark.django_db

def _period_first_of_this_month():
    today = timezone.localdate()
    return today.replace(day=1)

@pytest.fixture
def tenant_setup():
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    Tariff.objects.create(utility_type="cold_water", rate=Decimal("48.15"), effective_from=date(2020, 1, 1))
    Tariff.objects.create(utility_type="electricity_single", rate=Decimal("4.87"), effective_from=date(2020, 1, 1))
    # baseline (previous month) readings set by landlord
    prev = _period_first_of_this_month().replace(day=1)
    baseline_period = date(prev.year - 1, 12, 1) if prev.month == 1 else date(prev.year, prev.month - 1, 1)
    MeterReading.objects.create(apartment=a, period=baseline_period, meter="cold_water", value=Decimal("100"))
    MeterReading.objects.create(apartment=a, period=baseline_period, meter="electricity_single", value=Decimal("1400"))
    u = User.objects.create_user("ivanov", password="pass12345")
    Tenant.objects.create(user=u, apartment=a, full_name="Иванов")
    return a, u

def _login(u):
    c = Client()
    assert c.login(username=u.username, password="pass12345")
    return c

def test_current_month_requires_login():
    resp = Client().get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

def test_submit_readings_generates_statement(tenant_setup):
    a, u = tenant_setup
    c = _login(u)
    resp = c.post("/", {"cold_water": "110", "electricity_single": "1500"})
    assert resp.status_code == 302   # redirect after POST
    period = _period_first_of_this_month()
    assert MeterReading.objects.filter(apartment=a, period=period, meter="cold_water",
                                       entered_by_tenant=True).exists()
    stmt = MonthlyStatement.objects.get(apartment=a, period=period)
    # (110-100)*48.15 + (1500-1400)*4.87 = 481.50 + 487.00
    assert stmt.total == Decimal("968.50")

def test_backward_reading_is_rejected(tenant_setup):
    a, u = tenant_setup
    c = _login(u)
    resp = c.post("/", {"cold_water": "90", "electricity_single": "1500"})
    assert resp.status_code == 200            # re-renders form with error
    assert b"\xd1\x83\xd0\xbc\xd0\xb5\xd0\xbd" in resp.content or b"error" in resp.content.lower() \
        or "уменьш" in resp.content.decode("utf-8")
    period = _period_first_of_this_month()
    assert not MeterReading.objects.filter(apartment=a, period=period).exists()

def test_tenant_cannot_see_other_apartment_history(tenant_setup):
    a, u = tenant_setup
    other = Apartment.objects.create(label="чужая кв")
    MonthlyStatement.objects.create(apartment=other, period=date(2026, 5, 1), total=Decimal("999"))
    c = _login(u)
    resp = c.get("/history/")
    assert resp.status_code == 200
    assert b"999" not in resp.content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest billing/tests/test_portal.py -v`
Expected: FAIL (routes/views missing → 404).

- [ ] **Step 3: Implement `billing/forms.py`**

```python
from decimal import Decimal
from django import forms

class MeterReadingForm(forms.Form):
    """Dynamic form: one DecimalField per meter this apartment uses."""
    def __init__(self, *args, meters=None, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "cold_water": "Холодная вода (м³)",
            "hot_water": "Горячая вода (м³)",
            "electricity_single": "Электроэнергия (кВт·ч)",
            "electricity_day": "Электроэнергия день (кВт·ч)",
            "electricity_night": "Электроэнергия ночь (кВт·ч)",
        }
        for meter in (meters or []):
            self.fields[meter] = forms.DecimalField(
                label=labels[meter], min_value=Decimal("0"), max_digits=12, decimal_places=3)
```

- [ ] **Step 4: Implement `billing/views.py`**

```python
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from .forms import MeterReadingForm
from .models import MeterReading, MonthlyStatement
from .services.statements import meters_for, generate_statement

def _current_period():
    return timezone.localdate().replace(day=1)

@login_required
def current_month(request):
    tenant = request.user.tenant
    apartment = tenant.apartment
    meters = meters_for(apartment)
    period = _current_period()

    if request.method == "POST":
        form = MeterReadingForm(request.POST, meters=meters)
        if form.is_valid():
            existing = {r.meter: r for r in
                        MeterReading.objects.filter(apartment=apartment, period=period)}
            # Save then attempt to generate; roll back the save if the math rejects it.
            saved = []
            for meter in meters:
                value = form.cleaned_data[meter]
                obj = existing.get(meter)
                if obj:
                    obj.value = value; obj.entered_by_tenant = True; obj.save()
                else:
                    obj = MeterReading.objects.create(
                        apartment=apartment, period=period, meter=meter,
                        value=value, entered_by_tenant=True)
                saved.append(obj)
            try:
                generate_statement(apartment, period)
            except ValueError as exc:
                for obj in saved:
                    obj.delete()
                messages.error(request, f"Ошибка: показание уменьшилось. {exc}")
                return render(request, "billing/current_month.html",
                              {"form": form, "statement": None, "period": period})
            messages.success(request, "Показания сохранены.")
            return redirect("current_month")
    else:
        form = MeterReadingForm(meters=meters)

    statement = MonthlyStatement.objects.filter(apartment=apartment, period=period).first()
    return render(request, "billing/current_month.html",
                  {"form": form, "statement": statement, "period": period})

@login_required
def history(request):
    apartment = request.user.tenant.apartment
    statements = MonthlyStatement.objects.filter(apartment=apartment).order_by("-period")
    return render(request, "billing/history.html", {"statements": statements})

@login_required
def documents(request):
    docs = request.user.tenant.documents.all()
    return render(request, "billing/documents.html", {"documents": docs})
```

Note: tenant access is via `request.user.tenant` (the one-to-one reverse accessor from Task 3).

- [ ] **Step 5: Implement `billing/urls.py`**

```python
from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.current_month, name="current_month"),
    path("history/", views.history, name="history"),
    path("documents/", views.documents, name="documents"),
]
```

- [ ] **Step 6: Wire `config/urls.py`**

```python
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("billing.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

- [ ] **Step 7: Create templates**

`billing/templates/billing/base.html`:
```html
{% load static %}
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}ЖКХ{% endblock %}</title>
  <style>
    body{font-family:system-ui,sans-serif;margin:0;background:#f5f6f8;color:#1a1a1a}
    .wrap{max-width:560px;margin:0 auto;padding:16px}
    nav a{margin-right:12px}
    .card{background:#fff;border-radius:12px;padding:16px;margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,.08)}
    table{width:100%;border-collapse:collapse}
    td,th{padding:6px 4px;text-align:left;border-bottom:1px solid #eee}
    .total{font-weight:700;font-size:1.1em}
    input{width:100%;padding:8px;box-sizing:border-box;margin:4px 0 12px}
    button{padding:10px 16px;border:0;border-radius:8px;background:#2a6df4;color:#fff;font-size:1em}
    .badge{padding:2px 8px;border-radius:8px;font-size:.85em}
    .unpaid{background:#fde2e1;color:#a11}.pending{background:#fff2cc;color:#8a6d00}.paid{background:#e2f5e1;color:#137a13}
    .msg{padding:8px 12px;border-radius:8px;margin:8px 0;background:#eef}
    .err{background:#fde2e1;color:#a11}
  </style>
</head>
<body>
<div class="wrap">
  <nav>
    <a href="{% url 'current_month' %}">Это месяц</a>
    <a href="{% url 'history' %}">История</a>
    <a href="{% url 'documents' %}">Документы</a>
    {% if user.is_authenticated %}
      <form method="post" action="{% url 'logout' %}" style="display:inline">{% csrf_token %}<button type="submit" style="background:none;border:0;padding:0;color:#2a6df4;font-size:1em;cursor:pointer">Выход</button></form>
    {% endif %}
  </nav>
  {% for m in messages %}<div class="msg {% if m.tags == 'error' %}err{% endif %}">{{ m }}</div>{% endfor %}
  {% block content %}{% endblock %}
</div>
</body>
</html>
```

`billing/templates/billing/current_month.html`:
```html
{% extends "billing/base.html" %}
{% block title %}Начисление за месяц{% endblock %}
{% block content %}
<h2>Начисление за {{ period|date:"F Y" }}</h2>
<div class="card">
  <h3>Внести показания</h3>
  <form method="post">
    {% csrf_token %}
    {% for field in form %}
      <label>{{ field.label }}</label>
      {{ field }}
      {% for e in field.errors %}<div class="msg err">{{ e }}</div>{% endfor %}
    {% endfor %}
    <button type="submit">Сохранить показания</button>
  </form>
</div>
{% if statement %}
<div class="card">
  <h3>К оплате
    <span class="badge {{ statement.status }}">{{ statement.get_status_display }}</span>
  </h3>
  <table>
    <tr><th>Услуга</th><th>Кол-во</th><th>Тариф</th><th>Сумма, ₽</th></tr>
    {% for l in statement.lines %}
    <tr>
      <td>{{ l.label }}</td>
      <td>{% if l.quantity %}{{ l.quantity }}{% else %}—{% endif %}</td>
      <td>{{ l.rate }}</td>
      <td>{{ l.amount }}</td>
    </tr>
    {% endfor %}
    <tr class="total"><td colspan="3">Итого</td><td>{{ statement.total }}</td></tr>
  </table>
</div>
{% endif %}
{% endblock %}
```

`billing/templates/billing/history.html`:
```html
{% extends "billing/base.html" %}
{% block title %}История{% endblock %}
{% block content %}
<h2>История начислений</h2>
{% for s in statements %}
<div class="card">
  <strong>{{ s.period|date:"F Y" }}</strong>
  <span class="badge {{ s.status }}">{{ s.get_status_display }}</span>
  <table>
    {% for l in s.lines %}
    <tr><td>{{ l.label }}</td><td>{{ l.amount }} ₽</td></tr>
    {% endfor %}
    <tr class="total"><td>Итого</td><td>{{ s.total }} ₽</td></tr>
  </table>
</div>
{% empty %}
<p>Пока нет начислений.</p>
{% endfor %}
{% endblock %}
```

`billing/templates/billing/documents.html`:
```html
{% extends "billing/base.html" %}
{% block title %}Документы{% endblock %}
{% block content %}
<h2>Мои документы</h2>
{% for d in documents %}
<div class="card"><a href="{{ d.file.url }}">{{ d.title }}</a>
  <div>Загружен: {{ d.uploaded_at|date:"d.m.Y" }}</div></div>
{% empty %}
<p>Документы не загружены.</p>
{% endfor %}
{% endblock %}
```

`billing/templates/registration/login.html`:
```html
{% extends "billing/base.html" %}
{% block title %}Вход{% endblock %}
{% block content %}
<h2>Вход</h2>
<div class="card">
  <form method="post">
    {% csrf_token %}
    <label>Логин</label>{{ form.username }}
    <label>Пароль</label>{{ form.password }}
    {% if form.errors %}<div class="msg err">Неверный логин или пароль.</div>{% endif %}
    <button type="submit">Войти</button>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 8: Add app templates dir to settings**

In `config/settings.py`, confirm `TEMPLATES[0]["APP_DIRS"]` is `True` (default). No change needed — Django finds `billing/templates/` automatically.

- [ ] **Step 9: Run portal tests**

Run: `pytest billing/tests/test_portal.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 10: Run the full suite**

Run: `pytest -v`
Expected: every test across all files PASSES.

- [ ] **Step 11: Commit**

```powershell
git add billing/forms.py billing/views.py billing/urls.py config/urls.py billing/templates billing/tests/test_portal.py
git commit -m "feat: tenant portal — readings entry, itemized bill, history, documents"
```

---

## Definition of Done (Plan 1)

- Landlord can, via `/admin`: create apartments (single/dual meter, fixed charges), tenant cards with login + agreement document, tariffs with effective dates + source links, and initial meter readings; mark statements paid/unpaid; regenerate statements.
- Tenant can log in, submit this month's readings, see the itemized bill + total + status, browse history, and open their agreement.
- Backward readings are rejected; missing tariffs raise a clear error; each tenant sees only their own data.
- `pytest -v` is green.

## Deferred to Plan 2

`Payment` model; shared receipt-intake service; web receipt upload page + "Мои чеки"; `MessengerAdapter` interface with Telegram and MAX adapters; tenant↔chat linking via `link_code`; the `pending` status flow and the admin approval/reject console with receipt previews.
