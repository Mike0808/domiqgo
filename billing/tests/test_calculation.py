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
