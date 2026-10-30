"""Расчёт начисления — команда модуля (в модуле с H3).

Состав подведённых услуг и норматив подогрева спрашиваются у Properties
(шаг C3c), показания и состав приборов — у Metering (C2e), ставки — у
Tariffs (C1), условия — у договора периода в Tenancy (ADR-0024). Сама
арифметика — чистый калькулятор `domain/calculation.py`.
"""

from datetime import date

from modules.metering import api as metering
from modules.properties import api as properties
from modules.tariffs import api as tariffs
from modules.tenancy import api as tenancy

from ..domain import invoice as rules
from ..domain.calculation import ApartmentConfig, compute_statement
from ..infrastructure import repository

#: Электросчётчик ожидается у любой квартиры, а какой именно — однотарифный
#: или пара «день/ночь» — знает реестр приборов, и только он
#: ([ADR-0028](../../../docs/architecture/adr/0028-electricity-zones-are-derived-from-the-registry.md)).
ELECTRICITY = ("electricity_single", "electricity_day", "electricity_night")


def metered_resources(property_id) -> list[str]:
    """Что начисляется по приборам — из реестра Metering, а не из флагов.

    Шаг C2e, нарушение №32 гап-анализа: источник состава один — тот, где
    есть заводской номер и начальное показание, то есть тот, по которому
    вообще можно посчитать.
    """
    return [m.resource for m in metering.get_expected_meters(property_id)]


def missing_meters(property_id) -> list[str]:
    """Чего не хватает в реестре приборов — названиями, для человека.

    Расчёт из-за нехватки не останавливается: ответственность за состав
    приборов несёт владелец. Но и молчать нельзя — счёт без горячей воды
    выглядит законным и недоначисляет незаметно, ровно как нулевой норматив
    подогрева до исправления дефекта №29.
    """
    obj = properties.get_property(property_id)
    registered = set(metered_resources(property_id))
    names = metering.resources()
    missing = []
    if obj.has_cold_water and "cold_water" not in registered:
        missing.append(names["cold_water"])
    if obj.has_hot_water and "hot_water" not in registered:
        missing.append(names["hot_water"])
    if not registered & set(ELECTRICITY):
        missing.append("Электроэнергия")
    return missing


def _line_to_dict(line) -> dict:
    return {
        "code": line.code,
        "label": line.label,
        "quantity": None if line.quantity is None else str(line.quantity),
        "rate": str(line.rate),
        "amount": str(line.amount),
    }


def generate_statement(property_id, period: date) -> int:
    """Пересчитать черновик начисления; возвращает идентификатор счёта.

    Счёт ключуется договором периода (шаг E2, ADR-0024). Строка тех же
    квартиры и месяца, оставшаяся без договора с миграции, усыновляется, а
    не дублируется: это тот же счёт, у которого наконец появился адресат.
    """
    obj = properties.get_property(property_id)
    contract = tenancy.tenancy_for(property_id, period)
    if contract is None:
        raise rules.MissingTenancyError(
            f"На {period:%d.%m.%Y} у квартиры «{obj.label}» нет договора: "
            "заведите жильца или проверьте дату заселения.")
    terms = contract.terms
    config = ApartmentConfig(
        has_sewage=obj.has_sewage, gvs_heat_norm=obj.gvs_heat_norm,
        rent=terms.rent, internet=terms.internet,
        other_fixed=terms.other_fixed, round_total=obj.round_total,
    )
    used = metering.get_consumption(property_id, period,
                                    metered_resources(property_id))
    consumption = {resource: value.used for resource, value in used.items()}
    # Дату подставляет Billing, а не Tariffs: тот не знает понятия
    # «расчётный период» (ADR-0004).
    rates = {code: rate.rate
             for code, rate in tariffs.get_rates_on(period).items()}
    lines, total = compute_statement(config, consumption, rates)
    draft = repository.draft_state(contract.tenancy_id, property_id, period)
    if draft is not None and draft["issued_at"] is not None:
        # Инвариант 2 Billing: выставленный счёт неизменяем. Пересчёт даст
        # ревизию, когда она появится; молча переписать предъявленное нельзя.
        raise rules.InvoiceAlreadyIssued(
            f"Счёт #{draft['invoice_id']} уже выставлен и не "
            "пересчитывается.")
    return repository.write_draft(
        draft["invoice_id"] if draft is not None else None,
        contract.tenancy_id, property_id, period,
        [_line_to_dict(line) for line in lines], total)
