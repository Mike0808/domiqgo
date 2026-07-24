from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

CENT = Decimal("0.01")
GCAL = Decimal("0.00001")  # heating quantities are shown to 5 decimal places

def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)

class MeterType(str, Enum):
    SINGLE = "single"
    DUAL = "dual"

class MissingTariffError(Exception):
    """Raised when no tariff is available for a required utility."""

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
    gvs_heat_norm: Decimal = Decimal("0")

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
}

def _consumption(meter: str, current: dict, previous: dict) -> Decimal:
    cur = current[meter]
    prev = previous.get(meter, Decimal("0"))
    used = cur - prev
    if used < 0:
        raise ValueError(f"Показание по счётчику «{meter}» уменьшилось: {prev} -> {cur}")
    return used

def _tariff(code: str, tariffs: dict) -> Decimal:
    try:
        return tariffs[code]
    except KeyError:
        raise MissingTariffError(f"Нет тарифа для услуги «{code}»")

def _metered_line(code, current, previous, tariffs) -> tuple[LineItem, Decimal]:
    qty = _consumption(code, current, previous)
    rate = _tariff(code, tariffs)
    return LineItem(code, LABELS[code], qty, rate, _money(qty * rate)), qty

def compute_statement(config, current, previous, tariffs):
    lines: list[LineItem] = []
    cold = hot = Decimal("0")

    if config.has_cold_water:
        line, cold = _metered_line("cold_water", current, previous, tariffs)
        lines.append(line)
    if config.has_hot_water:
        # Двухкомпонентный ГВС: объём по счётчику (м³) оплачивается по
        # компоненту ХВ, а тепло на подогрев (объём × норматив, Гкал) — по
        # компоненту ТЭ. Водоотведение ниже считает только объём (hot).
        hot = _consumption("hot_water", current, previous)
        cold_rate = _tariff("hot_water_cold_component", tariffs)
        lines.append(LineItem("hot_water_cold_component",
                              LABELS["hot_water_cold_component"],
                              hot, cold_rate, _money(hot * cold_rate)))
        heat_qty = (hot * config.gvs_heat_norm).quantize(GCAL, rounding=ROUND_HALF_UP)
        heat_rate = _tariff("hot_water_heat_component", tariffs)
        lines.append(LineItem("hot_water_heat_component",
                              LABELS["hot_water_heat_component"],
                              heat_qty, heat_rate, _money(heat_qty * heat_rate)))
    if config.has_sewage:
        volume = cold + hot
        rate = _tariff("sewage", tariffs)
        lines.append(LineItem("sewage", LABELS["sewage"], volume, rate, _money(volume * rate)))

    if config.electricity_meter_type == MeterType.SINGLE:
        line, _ = _metered_line("electricity_single", current, previous, tariffs)
        lines.append(line)
    else:
        for code in ("electricity_day", "electricity_night"):
            line, _ = _metered_line(code, current, previous, tariffs)
            lines.append(line)

    for code, amount in (("rent", config.rent), ("internet", config.internet),
                         ("other_fixed", config.other_fixed)):
        if amount and amount > 0:
            lines.append(LineItem(code, LABELS[code], None, _money(amount), _money(amount)))

    total = _money(sum((l.amount for l in lines), Decimal("0")))
    return lines, total
