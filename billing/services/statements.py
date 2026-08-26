from datetime import date

from modules.metering import api as metering
from modules.properties import api as properties
from modules.tariffs import api as tariffs

from .calculation import ApartmentConfig, compute_statement
from ..models import Apartment, MonthlyStatement

#: Что квартира обещает измерять, если верить её флагам. Пары «флаг → приборы»
#: остались единственным местом, где флаги ещё что-то значат для учёта: они
#: больше не решают, что начислять, а служат сверкой с реестром.
def _promised_by_flags(apartment) -> list[str]:
    obj = properties.get_property(apartment.pk)
    promised = []
    if obj.has_cold_water:
        promised.append("cold_water")
    if obj.has_hot_water:
        promised.append("hot_water")
    if apartment.electricity_meter_type == Apartment.SINGLE:
        promised.append("electricity_single")
    else:
        promised.extend(["electricity_day", "electricity_night"])
    return promised

def metered_resources(apartment) -> list[str]:
    """Что начисляется по приборам — из реестра Metering, а не из флагов.

    Шаг C2e, нарушение №32 гап-анализа: до него состав выводился из флагов
    `has_*`, а номера и базы лежали в реестре, и два источника расходились в
    обе стороны. Теперь источник один — тот, где есть заводской номер и
    начальное показание, то есть тот, по которому вообще можно посчитать.
    """
    return [m.resource for m in metering.get_expected_meters(apartment.pk)]

def missing_meters(apartment) -> list[str]:
    """Услуги, которые квартира обещает флагами, но прибора для них нет.

    Расчёт из-за этого не останавливается: ответственность за состав приборов
    несёт владелец. Но и молчать нельзя — счёт без горячей воды выглядит
    законным и недоначисляет незаметно, ровно как нулевой норматив подогрева
    до исправления дефекта №29. Поэтому владелец видит перечень в списке
    квартир и в сообщении при пересчёте.
    """
    registered = set(metered_resources(apartment))
    return [r for r in _promised_by_flags(apartment) if r not in registered]

def _consumption_for(apartment, period, resources) -> dict:
    """Расход по приборам квартиры за период.

    Правило базы отсчёта уехало в Metering шагом C2d — вместе с прибором,
    которому оно принадлежит. Перевода отказа здесь больше нет: с шага C2e
    состав берётся из реестра, а зарегистрированный прибор всегда имеет
    начальное показание, поэтому базе отсчёта неоткуда пропасть.
    """
    used = metering.get_consumption(apartment.pk, period, resources)
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
    # Состав подведённых услуг и норматив подогрева спрашиваются у Properties:
    # это конфигурация объекта, и владеет ею модуль (шаг C3c). Ставка аренды,
    # интернет, прочее и политика округления читаются из той же строки
    # напрямую — они лежат в таблице объектов как временные жильцы и ждут
    # Tenancy и Billing.
    obj = properties.get_property(apartment.pk)
    config = ApartmentConfig(
        has_sewage=obj.has_sewage, gvs_heat_norm=obj.gvs_heat_norm,
        rent=apartment.rent, internet=apartment.internet,
        other_fixed=apartment.other_fixed, round_total=apartment.round_total,
    )
    consumption = _consumption_for(apartment, period, metered_resources(apartment))
    tariffs = _tariffs_for(period)
    lines, total = compute_statement(config, consumption, tariffs)
    stmt, _created = MonthlyStatement.objects.update_or_create(
        apartment=apartment, period=period,
        defaults={"lines": [line_to_dict(l) for l in lines], "total": total},
    )
    return stmt
