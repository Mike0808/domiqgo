from datetime import date
from decimal import Decimal
import pytest
from billing.models import Apartment, Tariff, MeterReading, MonthlyStatement
from billing.services.statements import generate_statement, meters_for

pytestmark = pytest.mark.django_db

def _tariffs(effective=date(2026, 7, 1)):
    data = {"cold_water": "48.15", "hot_water_cold_component": "25.86",
            "hot_water_heat_component": "2389.72", "sewage": "36.40",
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
    a = Apartment.objects.create(label="кв", rent=Decimal("20000"), internet=Decimal("700"),
                                 gvs_heat_norm=Decimal("0.05229"))
    _tariffs()
    _readings(a, date(2026, 6, 1), "100", "50", "1400")
    _readings(a, date(2026, 7, 1), "110", "55", "1500")

    stmt = generate_statement(a, date(2026, 7, 1))

    assert stmt.total == Decimal("22968.59")
    by = {l["code"]: l for l in stmt.lines}
    assert by["cold_water"]["amount"] == "481.50"
    assert by["hot_water_cold_component"]["amount"] == "129.30"    # 5 * 25.86
    assert by["hot_water_heat_component"]["quantity"] == "0.26145"  # 5 * 0.05229 Гкал
    assert by["hot_water_heat_component"]["amount"] == "624.79"
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
