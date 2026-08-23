"""Каталог тарифицируемых услуг — словарь Tariffs, и только его.

[ADR-0003](../../../docs/architecture/adr/0003-service-code-vocabularies.md):
общего enum на всю систему нет. Коды здесь текстуально пересекаются с видами
приборов Metering и кодами строк счёта Billing, но означают другое — то, что
**тарифицируется**. `sewage` тарифицируется, но не измеряется ничем; объём ГВС
измеряется одним прибором, а тарифицируется двумя услугами. Совпадение строк —
случайность предметной области, а не общая сущность.

Сопоставление «услуга ↔ прибор» принадлежит Billing: он единственный, кому
нужны обе стороны сразу.
"""

COLD_WATER = "cold_water"
HOT_WATER_COLD_COMPONENT = "hot_water_cold_component"
HOT_WATER_HEAT_COMPONENT = "hot_water_heat_component"
SEWAGE = "sewage"
ELECTRICITY_SINGLE = "electricity_single"
ELECTRICITY_DAY = "electricity_day"
ELECTRICITY_NIGHT = "electricity_night"

#: Код услуги → название для человека. Порядок — порядок показа владельцу.
UTILITIES: dict[str, str] = {
    COLD_WATER: "Холодная вода",
    HOT_WATER_COLD_COMPONENT: "ГВС — компонент на холодную воду",
    HOT_WATER_HEAT_COMPONENT: "ГВС — компонент на тепловую энергию",
    SEWAGE: "Водоотведение",
    ELECTRICITY_SINGLE: "Электроэнергия",
    ELECTRICITY_DAY: "Электроэнергия (день)",
    ELECTRICITY_NIGHT: "Электроэнергия (ночь)",
}


class UnknownUtility(ValueError):
    """Услуги с таким кодом в каталоге нет."""


def ensure_known(utility: str) -> str:
    if utility not in UTILITIES:
        raise UnknownUtility(
            f"«{utility}» нет в каталоге услуг Tariffs. Известны: "
            + ", ".join(UTILITIES)
        )
    return utility
