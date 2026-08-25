from datetime import date

from modules.metering import api as metering
from modules.tariffs import api as tariffs

from .calculation import ApartmentConfig, MeterType, compute_statement
from ..models import Apartment, MonthlyStatement

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
    return metering.get_readings(apartment.pk, period)

def _previous_readings(apartment, period, meters) -> dict:
    """Baseline per meter: the latest reading before `period`, else the
    contract-fixed initial value from the apartment's Meter. A meter with
    neither is an error — billing from an implicit 0 overcharges the tenant.
    """
    # Шаг C2c: приборы и показания спрашиваются у Metering, а не читаются
    # из собственных таблиц — их у Billing больше нет.
    initials = {m.resource: m.initial_value
                for m in metering.get_expected_meters(apartment.pk)}
    result, missing = {}, []
    for meter in meters:
        previous = metering.get_baseline_value(apartment.pk, meter, period)
        if previous is not None:
            result[meter] = previous
        elif meter in initials:
            result[meter] = initials[meter]
        else:
            missing.append(meter)
    if missing:
        raise MissingBaselineError(
            "Нет начальных показаний для: " + ", ".join(missing))
    return result

def _tariffs_for(period) -> dict:
    """Ставки, действующие на дату начала периода.

    Выбор версии уехал в Tariffs шагом C1; здесь остался только вызов и
    подстановка даты. Дату подставляет Billing, а не Tariffs: тот не знает
    понятия «расчётный период», и вопрос «что делать, если ставка сменилась в
    середине месяца» остаётся здесь, где есть данные для ответа (ADR-0004).
    """
    return {code: rate.rate for code, rate in tariffs.get_rates_on(period).items()}

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
        gvs_heat_norm=apartment.gvs_heat_norm, round_total=apartment.round_total,
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
