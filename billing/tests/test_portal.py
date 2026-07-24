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

def test_resubmit_with_backward_meter_preserves_prior_readings(tenant_setup):
    from billing.models import MeterReading
    a, u = tenant_setup
    c = _login(u)
    # First submit succeeds and persists this-month readings.
    assert c.post("/", {"cold_water": "110", "electricity_single": "1500"}).status_code == 302
    period = _period_first_of_this_month()
    assert MeterReading.objects.get(apartment=a, period=period, meter="cold_water").value == Decimal("110")
    # Re-submit: electricity now reads backward (1500 -> 1490 < baseline logic), cold_water is fine.
    resp = c.post("/", {"cold_water": "115", "electricity_single": "1300"})
    assert resp.status_code == 200  # rejected, re-rendered with error
    # The previously-saved cold_water reading must NOT be destroyed by the rollback.
    assert MeterReading.objects.filter(apartment=a, period=period, meter="cold_water").exists()
    assert MeterReading.objects.get(apartment=a, period=period, meter="cold_water").value == Decimal("110")

def test_tenant_cannot_see_other_apartment_history(tenant_setup):
    a, u = tenant_setup
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 5, 1), total=Decimal("123"))
    other = Apartment.objects.create(label="чужая кв")
    MonthlyStatement.objects.create(apartment=other, period=date(2026, 5, 1), total=Decimal("999"))
    c = _login(u)
    resp = c.get("/history/")
    assert resp.status_code == 200
    assert b"123" in resp.content        # own statement shown
    assert b"999" not in resp.content    # foreign statement hidden

def test_paid_month_locks_readings(tenant_setup):
    a, u = tenant_setup
    period = _period_first_of_this_month()
    MonthlyStatement.objects.create(apartment=a, period=period, total=Decimal("500"),
                                    status=MonthlyStatement.PAID)
    c = _login(u)
    resp = c.post("/", {"cold_water": "110", "electricity_single": "1500"})
    assert resp.status_code == 302               # rejected with a message, not applied
    assert not MeterReading.objects.filter(apartment=a, period=period).exists()
    stmt = MonthlyStatement.objects.get(apartment=a, period=period)
    assert stmt.status == MonthlyStatement.PAID
    assert stmt.total == Decimal("500")          # settled amount untouched
    page = c.get("/")
    assert "Показания заблокированы" in page.content.decode()

def test_pending_month_locks_readings(tenant_setup):
    a, u = tenant_setup
    period = _period_first_of_this_month()
    MonthlyStatement.objects.create(apartment=a, period=period, total=Decimal("500"),
                                    status=MonthlyStatement.PENDING)
    c = _login(u)
    resp = c.post("/", {"cold_water": "110", "electricity_single": "1500"})
    assert resp.status_code == 302               # rejected with a message, not applied
    assert not MeterReading.objects.filter(apartment=a, period=period).exists()
    stmt = MonthlyStatement.objects.get(apartment=a, period=period)
    assert stmt.status == MonthlyStatement.PENDING
    assert stmt.total == Decimal("500")          # amount under review untouched
    page = c.get("/")
    assert "Показания заблокированы" in page.content.decode()

def test_staff_without_tenant_profile_redirects_to_admin(db):
    User.objects.create_superuser("boss", "boss@example.com", "pass12345")
    c = Client()
    assert c.login(username="boss", password="pass12345")
    resp = c.get("/")
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith("/admin/")

def test_user_without_tenant_profile_gets_friendly_page(db):
    User.objects.create_user("nobody", password="pass12345")
    c = Client()
    assert c.login(username="nobody", password="pass12345")
    resp = c.get("/")
    assert resp.status_code == 200               # not a 500
    assert "не привязана" in resp.content.decode()

def test_missing_sewage_tariff_shows_message_not_500(db):
    from django.contrib.auth.models import User
    from billing.models import Apartment, Tenant, Tariff, MeterReading, MonthlyStatement
    period = _period_first_of_this_month()
    baseline = date(period.year - 1, 12, 1) if period.month == 1 else date(period.year, period.month - 1, 1)
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=True)
    # cold + electricity tariffs exist, but NO sewage tariff
    Tariff.objects.create(utility_type="cold_water", rate=Decimal("48.15"), effective_from=date(2020, 1, 1))
    Tariff.objects.create(utility_type="electricity_single", rate=Decimal("4.87"), effective_from=date(2020, 1, 1))
    MeterReading.objects.create(apartment=a, period=baseline, meter="cold_water", value=Decimal("100"))
    MeterReading.objects.create(apartment=a, period=baseline, meter="electricity_single", value=Decimal("1400"))
    u = User.objects.create_user("petrov", password="pass12345")
    Tenant.objects.create(user=u, apartment=a, full_name="Петров")
    c = Client()
    assert c.login(username="petrov", password="pass12345")
    resp = c.post("/", {"cold_water": "110", "electricity_single": "1500"})
    assert resp.status_code == 200  # graceful re-render, not a 500
    assert not MonthlyStatement.objects.filter(apartment=a, period=period).exists()

def test_first_month_uses_contract_initial_values(db):
    from billing.models import Meter
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    Tariff.objects.create(utility_type="cold_water", rate=Decimal("48.15"), effective_from=date(2020, 1, 1))
    Tariff.objects.create(utility_type="electricity_single", rate=Decimal("4.87"), effective_from=date(2020, 1, 1))
    Meter.objects.create(apartment=a, kind="cold_water", serial_number="CW-77",
                         initial_value=Decimal("100"))
    Meter.objects.create(apartment=a, kind="electricity_single", serial_number="E-77",
                         initial_value=Decimal("1400"))
    u = User.objects.create_user("newbie", password="pass12345")
    Tenant.objects.create(user=u, apartment=a, full_name="Новосёл")
    c = Client()
    assert c.login(username="newbie", password="pass12345")
    # serial numbers are visible on the form
    page = c.get("/")
    assert "CW-77" in page.content.decode()
    # first-ever submission bills from the contract values, not from zero
    resp = c.post("/", {"cold_water": "110", "electricity_single": "1500"})
    assert resp.status_code == 302
    stmt = MonthlyStatement.objects.get(apartment=a)
    assert stmt.total == Decimal("968.50")

def test_missing_baseline_shows_message_not_bill_from_zero(db):
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    Tariff.objects.create(utility_type="cold_water", rate=Decimal("48.15"), effective_from=date(2020, 1, 1))
    Tariff.objects.create(utility_type="electricity_single", rate=Decimal("4.87"), effective_from=date(2020, 1, 1))
    # no Meter rows, no prior readings
    u = User.objects.create_user("orphan", password="pass12345")
    Tenant.objects.create(user=u, apartment=a, full_name="Без базы")
    c = Client()
    assert c.login(username="orphan", password="pass12345")
    resp = c.post("/", {"cold_water": "110", "electricity_single": "1500"})
    assert resp.status_code == 200  # friendly re-render, not a bill from zero
    assert "Начальные показания не заданы" in resp.content.decode()
    assert not MonthlyStatement.objects.filter(apartment=a).exists()
