from datetime import date
from decimal import Decimal
import pytest
from django.contrib.auth.models import User
from django.test import Client
from modules.metering.infrastructure.models import Meter, MeterReading
from billing.models import Apartment, MonthlyStatement
from modules.tariffs.api import publish_tariff_version

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
    publish_tariff_version(utility="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    publish_tariff_version(utility="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    Meter.objects.create(apartment_id=a.pk, resource="cold_water", initial_value=Decimal("0"))
    Meter.objects.create(apartment_id=a.pk, resource="electricity_single", initial_value=Decimal("0"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="electricity_single", value=Decimal("1600"))
    stmt = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1))

    admin_client.post("/admin/billing/monthlystatement/", {
        "action": "regenerate_statements",
        "_selected_action": [str(stmt.pk)],
    })
    stmt.refresh_from_db()
    # New meters start at 0: 110*48.15 + 1600*4.87 = 13088.50 -> floored to 13050
    assert stmt.total == Decimal("13050.00")

def test_regenerate_action_reports_failure_without_500(admin_client):
    
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=True)
    publish_tariff_version(utility="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    publish_tariff_version(utility="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    Meter.objects.create(apartment_id=a.pk, resource="cold_water", initial_value=Decimal("0"))
    Meter.objects.create(apartment_id=a.pk, resource="electricity_single", initial_value=Decimal("0"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="electricity_single", value=Decimal("1600"))
    stmt = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1))  # sewage tariff missing
    resp = admin_client.post("/admin/billing/monthlystatement/", {
        "action": "regenerate_statements",
        "_selected_action": [str(stmt.pk)],
    }, follow=True)
    assert resp.status_code == 200  # reported via messages, not a 500

def test_admin_saving_reading_recalculates_statement(admin_client):
    
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    publish_tariff_version(utility="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    publish_tariff_version(utility="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    Meter.objects.create(apartment_id=a.pk, resource="cold_water", initial_value=Decimal("100"))
    Meter.objects.create(apartment_id=a.pk, resource="electricity_single", initial_value=Decimal("1400"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), resource="electricity_single", value=Decimal("1500"))
    resp = admin_client.post("/admin/metering/meterreading/add/", {
        "apartment_id": str(a.pk), "period": "2026-07-01",
        "resource": "cold_water", "value": "110",
    }, follow=True)
    assert resp.status_code == 200
    stmt = MonthlyStatement.objects.get(apartment=a, period=date(2026, 7, 1))
    assert stmt.total == Decimal("968.50")  # recalculated on save; below 10 000 — not rounded


# ------------------------------- предупреждение о незаведённых приборах (C2e)

def test_the_apartment_list_names_the_meters_to_register(admin_client):
    """Счёт чаще всего порождает жилец, сдавая показания, и сообщения того
    пересчёта владелец не увидит никогда. Поэтому нехватка видна в списке."""
    Apartment.objects.create(label="кв. 10", has_hot_water=False)

    page = admin_client.get("/admin/billing/apartment/").content.decode()

    assert "Холодная вода" in page
    assert "Электроэнергия" in page


def test_the_apartment_list_stays_quiet_when_the_registry_is_complete(admin_client):
    a = Apartment.objects.create(label="кв. 10", has_hot_water=False)
    Meter.objects.create(apartment_id=a.pk, resource="cold_water",
                         initial_value=Decimal("0"))
    Meter.objects.create(apartment_id=a.pk, resource="electricity_single",
                         initial_value=Decimal("0"))

    page = admin_client.get("/admin/billing/apartment/").content.decode()

    assert "Холодная вода" not in page


def test_recalculating_warns_about_meters_that_are_not_registered(admin_client):
    a = Apartment.objects.create(label="кв. 10", has_hot_water=False,
                                 has_sewage=False)
    stmt = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1))

    resp = admin_client.post("/admin/billing/monthlystatement/", {
        "action": "regenerate_statements",
        "_selected_action": [str(stmt.pk)],
    }, follow=True)

    page = resp.content.decode()
    assert "не заведены приборы" in page
    assert "в счёт не попали" in page
