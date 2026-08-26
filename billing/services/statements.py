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

def _consumption_for(apartment, period, meters) -> dict:
    """Расход по приборам квартиры за период.

    Правило базы отсчёта уехало в Metering шагом C2d — вместе с самим
    прибором, которому оно и принадлежит. Здесь остался перевод отказа модуля
    на язык Billing: «нет базы отсчёта» модуль называет фактом, а ошибкой
    расчёта его по-прежнему назначает счёт.
    """
    try:
        used = metering.get_consumption(apartment.pk, period, meters)
    except metering.BaselineMissing as gap:
        raise MissingBaselineError(
            "Нет начальных показаний для: " + ", ".join(gap.resources))
    return {resource: value.used for resource, value in used.items()}

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
    consumption = _consumption_for(apartment, period, meters_for(apartment))
    tariffs = _tariffs_for(period)
    lines, total = compute_statement(config, consumption, tariffs)
    stmt, _created = MonthlyStatement.objects.update_or_create(
        apartment=apartment, period=period,
        defaults={"lines": [line_to_dict(l) for l in lines], "total": total},
    )
    return stmt
