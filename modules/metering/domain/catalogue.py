"""Каталог видов ресурса — словарь Metering, и только его.

[ADR-0003](../../../docs/architecture/adr/0003-service-code-vocabularies.md):
общего enum на всю систему нет. Коды здесь текстуально пересекаются с услугами
Tariffs и кодами строк счёта Billing, но означают другое — то, что **физически
измеряет прибор**. `sewage` тарифицируется, но не измеряется ничем и потому
здесь отсутствует; `hot_water` измеряется одним прибором, а тарифицируется
двумя услугами.

Сопоставление «ресурс ↔ услуга» принадлежит Billing: он единственный, кому
нужны обе стороны сразу.
"""

COLD_WATER = "cold_water"
HOT_WATER = "hot_water"
ELECTRICITY_SINGLE = "electricity_single"
ELECTRICITY_DAY = "electricity_day"
ELECTRICITY_NIGHT = "electricity_night"

#: Код ресурса → название для человека. Порядок — порядок показа владельцу.
RESOURCES: dict[str, str] = {
    COLD_WATER: "Холодная вода",
    HOT_WATER: "Горячая вода",
    ELECTRICITY_SINGLE: "Электроэнергия",
    ELECTRICITY_DAY: "Электроэнергия (день)",
    ELECTRICITY_NIGHT: "Электроэнергия (ночь)",
}

#: Единица измерения принадлежит прибору, а не счёту: Metering отдаёт
#: кубометры и киловатт-часы, во что их превращают — вопрос Billing.
UNITS: dict[str, str] = {
    COLD_WATER: "м³",
    HOT_WATER: "м³",
    ELECTRICITY_SINGLE: "кВт·ч",
    ELECTRICITY_DAY: "кВт·ч",
    ELECTRICITY_NIGHT: "кВт·ч",
}


class UnknownResource(ValueError):
    """Ресурса с таким кодом в каталоге нет."""


def ensure_known(resource: str) -> str:
    if resource not in RESOURCES:
        raise UnknownResource(
            f"«{resource}» нет в каталоге ресурсов Metering. Известны: "
            + ", ".join(RESOURCES)
        )
    return resource
