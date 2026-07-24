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
    from billing.models import Meter
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    Tariff.objects.create(utility_type="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    Tariff.objects.create(utility_type="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    Meter.objects.create(apartment=a, kind="cold_water", initial_value=Decimal("0"))
    Meter.objects.create(apartment=a, kind="electricity_single", initial_value=Decimal("0"))
    MeterReading.objects.create(apartment=a, period=date(2026, 7, 1), meter="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment=a, period=date(2026, 7, 1), meter="electricity_single", value=Decimal("1600"))
    stmt = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1))

    admin_client.post("/admin/billing/monthlystatement/", {
        "action": "regenerate_statements",
        "_selected_action": [str(stmt.pk)],
    })
    stmt.refresh_from_db()
    # New meters start at 0: 110*48.15 + 1600*4.87
    assert stmt.total == Decimal("13088.50")

def test_regenerate_action_reports_failure_without_500(admin_client):
    from billing.models import Meter
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=True)
    Tariff.objects.create(utility_type="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    Tariff.objects.create(utility_type="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    Meter.objects.create(apartment=a, kind="cold_water", initial_value=Decimal("0"))
    Meter.objects.create(apartment=a, kind="electricity_single", initial_value=Decimal("0"))
    MeterReading.objects.create(apartment=a, period=date(2026, 7, 1), meter="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment=a, period=date(2026, 7, 1), meter="electricity_single", value=Decimal("1600"))
    stmt = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1))  # sewage tariff missing
    resp = admin_client.post("/admin/billing/monthlystatement/", {
        "action": "regenerate_statements",
        "_selected_action": [str(stmt.pk)],
    }, follow=True)
    assert resp.status_code == 200  # reported via messages, not a 500

def test_admin_saving_reading_recalculates_statement(admin_client):
    from billing.models import Meter
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    Tariff.objects.create(utility_type="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    Tariff.objects.create(utility_type="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    Meter.objects.create(apartment=a, kind="cold_water", initial_value=Decimal("100"))
    Meter.objects.create(apartment=a, kind="electricity_single", initial_value=Decimal("1400"))
    MeterReading.objects.create(apartment=a, period=date(2026, 7, 1), meter="electricity_single", value=Decimal("1500"))
    resp = admin_client.post("/admin/billing/meterreading/add/", {
        "apartment": str(a.pk), "period": "2026-07-01",
        "meter": "cold_water", "value": "110",
    }, follow=True)
    assert resp.status_code == 200
    stmt = MonthlyStatement.objects.get(apartment=a, period=date(2026, 7, 1))
    assert stmt.total == Decimal("968.50")  # recalculated on save
