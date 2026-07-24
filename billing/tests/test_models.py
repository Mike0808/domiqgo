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
