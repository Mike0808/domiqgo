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
