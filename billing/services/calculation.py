from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from enum import Enum

CENT = Decimal("0.01")
GCAL = Decimal("0.00001")  # heating quantities are shown to 5 decimal places
# The payable total is floored to a multiple of ROUND_STEP (landlord's choice:
# 60 047.81 -> 60 000; 60 097.81 -> 60 050), with an explicit adjustment line —
# but only when it exceeds ROUND_THRESHOLD and the apartment opts in.
ROUND_STEP = Decimal("50")
ROUND_THRESHOLD = Decimal("10000")

def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)

class MeterType(str, Enum):
    SINGLE = "single"
    DUAL = "dual"

class MissingTariffError(Exception):
    """Raised when no tariff is available for a required utility."""

class MissingHeatNormError(Exception):
    """Raised when hot water is plumbed but the heating norm is not set.

    Гкал = объём × норматив, поэтому нулевой норматив даёт нулевую сумму за
    подогрев — счёт со строкой «подогрев: 0,00 ₽» выглядит законно и молча
    недоначисляет (дефект №29 гап-анализа). Величина не выводится ни из чего:
    она подомовая и берётся из квитанции УК. Единственный правильный ответ —
    отказаться считать.
    """

@dataclass(frozen=True)
class ApartmentConfig:
    electricity_meter_type: MeterType
    has_cold_water: bool
    has_hot_water: bool
    has_sewage: bool
    rent: Decimal
    internet: Decimal
    other_fixed: Decimal
    # Гкал на подогрев 1 м³ ГВС (норматив дома); Гкал = объём × норматив.
    # Без значения по умолчанию намеренно: при `has_hot_water` ноль — ошибка,
    # а умолчание, которое всегда ошибка, только прячет её (дефект №29).
    gvs_heat_norm: Decimal
    # Округлять итог вниз до 50 ₽ (только свыше ROUND_THRESHOLD).
    round_total: bool = True

@dataclass(frozen=True)
class LineItem:
    code: str
    label: str
    quantity: Decimal | None
    rate: Decimal
    amount: Decimal

LABELS = {
    "cold_water": "Холодная вода",
    "hot_water_cold_component": "Горячая вода (компонент ХВ)",
    "hot_water_heat_component": "Горячая вода (подогрев)",
    "sewage": "Водоотведение",
    "electricity_single": "Электроэнергия",
    "electricity_day": "Электроэнергия (день)",
    "electricity_night": "Электроэнергия (ночь)",
    "rent": "Аренда",
    "internet": "Интернет",
    "other_fixed": "Прочее",
    "rounding": "Округление",
}

def _tariff(code: str, tariffs: dict) -> Decimal:
    try:
        return tariffs[code]
    except KeyError:
        raise MissingTariffError(f"Нет тарифа для услуги «{code}»")

def _metered_line(code, consumption, tariffs) -> tuple[LineItem, Decimal]:
    qty = consumption[code]
    rate = _tariff(code, tariffs)
    return LineItem(code, LABELS[code], qty, rate, _money(qty * rate)), qty

def compute_statement(config, consumption, tariffs):
    """Счёт из готового расхода, тарифов и условий квартиры.

    Расход приходит посчитанным: вычитание показаний и правило «показание не
    уменьшается» — знание прибора, и с шага C2d они живут в Metering
    (`modules/metering/domain/point.py`). Здесь остался счёт: какие услуги
    начислить, по какой ставке и как сложить.
    """
    lines: list[LineItem] = []
    cold = hot = Decimal("0")

    if config.has_cold_water:
        line, cold = _metered_line("cold_water", consumption, tariffs)
        lines.append(line)
    if config.has_hot_water:
        # Двухкомпонентный ГВС: объём по счётчику (м³) оплачивается по
        # компоненту ХВ, а тепло на подогрев (объём × норматив, Гкал) — по
        # компоненту ТЭ. Водоотведение ниже считает только объём (hot).
        if config.gvs_heat_norm <= 0:
            raise MissingHeatNormError(
                "Не задан норматив подогрева ГВС (Гкал/м³): "
                f"{config.gvs_heat_norm}")
        hot = consumption["hot_water"]
        cold_rate = _tariff("hot_water_cold_component", tariffs)
        lines.append(LineItem("hot_water_cold_component",
                              LABELS["hot_water_cold_component"],
                              hot, cold_rate, _money(hot * cold_rate)))
        heat_qty = (hot * config.gvs_heat_norm).quantize(GCAL, rounding=ROUND_HALF_UP)
        heat_rate = _tariff("hot_water_heat_component", tariffs)
        # Spell out the derivation so the tenant sees the volume factor:
        # the Гкал quantity already equals объём × норматив.
        heat_label = (f"{LABELS['hot_water_heat_component']}: "
                      f"{hot} м³ × {config.gvs_heat_norm} Гкал/м³")
        lines.append(LineItem("hot_water_heat_component", heat_label,
                              heat_qty, heat_rate, _money(heat_qty * heat_rate)))
    if config.has_sewage:
        volume = cold + hot
        rate = _tariff("sewage", tariffs)
        lines.append(LineItem("sewage", LABELS["sewage"], volume, rate, _money(volume * rate)))

    if config.electricity_meter_type == MeterType.SINGLE:
        line, _ = _metered_line("electricity_single", consumption, tariffs)
        lines.append(line)
    else:
        for code in ("electricity_day", "electricity_night"):
            line, _ = _metered_line(code, consumption, tariffs)
            lines.append(line)

    for code, amount in (("rent", config.rent), ("internet", config.internet),
                         ("other_fixed", config.other_fixed)):
        if amount and amount > 0:
            lines.append(LineItem(code, LABELS[code], None, _money(amount), _money(amount)))

    exact = _money(sum((l.amount for l in lines), Decimal("0")))
    total = exact
    if config.round_total and exact > ROUND_THRESHOLD:
        total = _money((exact / ROUND_STEP).to_integral_value(rounding=ROUND_FLOOR)
                       * ROUND_STEP)
        if total != exact:
            lines.append(LineItem("rounding", LABELS["rounding"], None,
                                  Decimal("0.00"), _money(total - exact)))
    return lines, total
