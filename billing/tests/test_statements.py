from datetime import date
from decimal import Decimal
import pytest
from billing.models import Apartment, Meter, MeterReading, MonthlyStatement
from modules.tariffs.api import publish_tariff_version
from billing.services.statements import (
    MissingBaselineError, generate_statement, meters_for,
)

pytestmark = pytest.mark.django_db

def _tariffs(effective=date(2026, 7, 1)):
    data = {"cold_water": "48.15", "hot_water_cold_component": "25.86",
            "hot_water_heat_component": "2389.72", "sewage": "36.40",
            "electricity_single": "4.87"}
    for code, rate in data.items():
        publish_tariff_version(utility=code, rate=Decimal(rate), effective_from=effective)

def _readings(apt, period, cold, hot, elec):
    MeterReading.objects.create(apartment_id=apt.pk, period=period, meter="cold_water", value=Decimal(cold))
    MeterReading.objects.create(apartment_id=apt.pk, period=period, meter="hot_water", value=Decimal(hot))
    MeterReading.objects.create(apartment_id=apt.pk, period=period, meter="electricity_single", value=Decimal(elec))

def test_meters_for_single_vs_dual():
    a = Apartment.objects.create(label="кв", electricity_meter_type=Apartment.SINGLE)
    assert meters_for(a) == ["cold_water", "hot_water", "electricity_single"]
    a.electricity_meter_type = Apartment.DUAL
    assert meters_for(a) == ["cold_water", "hot_water", "electricity_day", "electricity_night"]

def test_generate_uses_previous_period_as_baseline():
    a = Apartment.objects.create(label="кв", rent=Decimal("20000"), internet=Decimal("700"),
                                 gvs_heat_norm=Decimal("0.05229"))
    _tariffs()
    _readings(a, date(2026, 6, 1), "100", "50", "1400")
    _readings(a, date(2026, 7, 1), "110", "55", "1500")

    stmt = generate_statement(a, date(2026, 7, 1))

    assert stmt.total == Decimal("22950.00")   # 22968.59 floored to 50
    by = {l["code"]: l for l in stmt.lines}
    assert by["rounding"]["amount"] == "-18.59"
    assert by["cold_water"]["amount"] == "481.50"
    assert by["hot_water_cold_component"]["amount"] == "129.30"    # 5 * 25.86
    assert by["hot_water_heat_component"]["quantity"] == "0.26145"  # 5 * 0.05229 Гкал
    assert by["hot_water_heat_component"]["amount"] == "624.79"
    assert by["sewage"]["amount"] == "546.00"
    assert by["rent"]["quantity"] is None

def test_generate_selects_tariff_effective_for_period():
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False,
                                 electricity_meter_type=Apartment.SINGLE)
    publish_tariff_version(utility="cold_water", rate=Decimal("40.00"), effective_from=date(2025, 7, 1))
    publish_tariff_version(utility="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    publish_tariff_version(utility="electricity_single", rate=Decimal("4.87"), effective_from=date(2025, 7, 1))
    Meter.objects.create(apartment_id=a.pk, kind="cold_water", initial_value=Decimal("100"))
    Meter.objects.create(apartment_id=a.pk, kind="electricity_single", initial_value=Decimal("0"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 6, 1), meter="cold_water", value=Decimal("100"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 6, 1), meter="electricity_single", value=Decimal("0"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), meter="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), meter="electricity_single", value=Decimal("0"))

    june = generate_statement(a, date(2026, 6, 1))   # baseline: contract initials
    july = generate_statement(a, date(2026, 7, 1))   # baseline: June readings

    july_cold = {l["code"]: l for l in july.lines}["cold_water"]
    assert july_cold["rate"] == "48.1500"            # new tariff applied for July
    assert july_cold["amount"] == "481.50"           # (110-100) * 48.15

def test_generate_is_idempotent_and_keeps_status():
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    publish_tariff_version(utility="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    publish_tariff_version(utility="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    Meter.objects.create(apartment_id=a.pk, kind="cold_water", initial_value=Decimal("0"))
    Meter.objects.create(apartment_id=a.pk, kind="electricity_single", initial_value=Decimal("0"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), meter="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), meter="electricity_single", value=Decimal("1500"))

    stmt = generate_statement(a, date(2026, 7, 1))
    stmt.status = MonthlyStatement.PAID
    stmt.save()
    again = generate_statement(a, date(2026, 7, 1))
    assert again.pk == stmt.pk
    assert again.status == MonthlyStatement.PAID
    assert MonthlyStatement.objects.filter(apartment=a, period=date(2026, 7, 1)).count() == 1

def test_first_month_baseline_comes_from_meter_initial_values():
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    publish_tariff_version(utility="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    publish_tariff_version(utility="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    # values fixed in the act at contract signing
    Meter.objects.create(apartment_id=a.pk, kind="cold_water", serial_number="CW-1",
                         initial_value=Decimal("100"), initial_date=date(2026, 6, 15))
    Meter.objects.create(apartment_id=a.pk, kind="electricity_single", serial_number="E-1",
                         initial_value=Decimal("1400"), initial_date=date(2026, 6, 15))
    # tenant's very first submission — no prior-month readings exist
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), meter="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), meter="electricity_single", value=Decimal("1500"))

    stmt = generate_statement(a, date(2026, 7, 1))

    # (110-100)*48.15 + (1500-1400)*4.87 = 968.50 — below 10 000, not rounded
    assert stmt.total == Decimal("968.50")

def test_baseline_falls_back_per_meter():
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    publish_tariff_version(utility="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    publish_tariff_version(utility="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    Meter.objects.create(apartment_id=a.pk, kind="cold_water", initial_value=Decimal("100"))
    Meter.objects.create(apartment_id=a.pk, kind="electricity_single", initial_value=Decimal("1400"))
    # June has a reading for electricity only; cold water must fall back to the initial value
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 6, 1), meter="electricity_single", value=Decimal("1450"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), meter="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), meter="electricity_single", value=Decimal("1500"))

    stmt = generate_statement(a, date(2026, 7, 1))

    # cold: (110-100)*48.15 = 481.50; elec: (1500-1450)*4.87 = 243.50 — not rounded
    assert stmt.total == Decimal("725.00")

def test_missing_baseline_raises_instead_of_billing_from_zero():
    a = Apartment.objects.create(label="кв", has_hot_water=False, has_sewage=False)
    publish_tariff_version(utility="cold_water", rate=Decimal("48.15"), effective_from=date(2026, 7, 1))
    publish_tariff_version(utility="electricity_single", rate=Decimal("4.87"), effective_from=date(2026, 7, 1))
    # no Meter rows, no prior readings
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), meter="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment_id=a.pk, period=date(2026, 7, 1), meter="electricity_single", value=Decimal("1500"))

    with pytest.raises(MissingBaselineError):
        generate_statement(a, date(2026, 7, 1))
    assert not MonthlyStatement.objects.filter(apartment=a).exists()
