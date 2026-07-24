from datetime import date
from .calculation import ApartmentConfig, MeterType, compute_statement
from ..models import Apartment, Tariff, MeterReading, MonthlyStatement

class MissingBaselineError(Exception):
    """No previous reading and no contract-fixed initial value for a meter."""

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

def _previous_readings(apartment, period, meters) -> dict:
    """Baseline per meter: the latest reading before `period`, else the
    contract-fixed initial value from the apartment's Meter. A meter with
    neither is an error — billing from an implicit 0 overcharges the tenant.
    """
    initials = {m.kind: m.initial_value for m in apartment.meters.all()}
    result, missing = {}, []
    for meter in meters:
        r = (MeterReading.objects
             .filter(apartment=apartment, meter=meter, period__lt=period)
             .order_by("-period").first())
        if r is not None:
            result[meter] = r.value
        elif meter in initials:
            result[meter] = initials[meter]
        else:
            missing.append(meter)
    if missing:
        raise MissingBaselineError(
            "Нет начальных показаний для: " + ", ".join(missing))
    return result

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
        gvs_heat_norm=apartment.gvs_heat_norm,
    )
    current = _readings_map(apartment, period)
    previous = _previous_readings(apartment, period, meters_for(apartment))
    tariffs = _tariffs_for(period)
    lines, total = compute_statement(config, current, previous, tariffs)
    stmt, _created = MonthlyStatement.objects.update_or_create(
        apartment=apartment, period=period,
        defaults={"lines": [line_to_dict(l) for l in lines], "total": total},
    )
    return stmt
