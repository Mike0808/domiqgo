"""Публичный API Properties — единственная дверь для остальных модулей.

| Спецификация | Здесь |
|---|---|
| `GetProperty(property_id)` | `get_property` |
| `ListProperties(include_decommissioned)` | `list_properties` |
| `RegisterProperty` | `register_property` |
| `RenameProperty` | `rename_property` |
| `ChangeServiceComposition` | `change_service_composition` |
| `DecommissionProperty` | `decommission_property` |
| `RecommissionProperty` | `recommission_property` |

**Команды `DeleteProperty` нет намеренно** — объект выводят из эксплуатации, а
не удаляют (шаг C3a,
[ADR-0009](../../../docs/architecture/adr/0009-property-decommission-and-active-tenancy.md)).

**Модель ещё видна снаружи.** `billing/` держит два внешних ключа на таблицу
объектов — `Tenant.apartment` и `MonthlyStatement.apartment` — и читает поля
напрямую. Разорвать их здесь нельзя: первый ждёт Tenancy (этап D), второй —
шага **E2**, где ключом счёта становится договор. До тех пор перенос владения
частичный, и это записано в плане, а не спрятано.
"""

from datetime import date
from decimal import Decimal

from ..application import commands, queries
from ..application.commands import PropertyNotFound
from ..domain.property import Apartment, HeatNormMissing, LabelMissing


def _repository():
    """Импорт внутри функции: `api/__init__` попадает в граф импортов раньше,
    чем Django готов отдать модели."""
    from ..infrastructure import repository

    return repository


# ------------------------------------------------------------------- запросы

def get_property(apartment_id: int) -> Apartment | None:
    """Объект: наименование, состав подведённых услуг, норматив, статус.

    Возвращает замкнутый датакласс без Django — вызывающему незачем знать ни
    про ORM, ни про внутренности модуля. `None`, если объекта нет.
    """
    return queries.get_property(_repository(), apartment_id)


def list_properties(include_decommissioned: bool = False) -> list[Apartment]:
    """Перечень объектов. Выведенные из эксплуатации по умолчанию скрыты."""
    return queries.list_properties(_repository(), include_decommissioned)


# ------------------------------------------------------------------- команды

def register_property(label: str, address: str = "",
                      has_cold_water: bool = True, has_hot_water: bool = True,
                      has_sewage: bool = True,
                      gvs_heat_norm: Decimal = Decimal("0")) -> int:
    """Завести объект. Возвращает идентификатор заведённого.

    Отказы: `LabelMissing` — без наименования объект не отличить от соседнего;
    `HeatNormMissing` — подведённая ГВС без норматива молча недоначисляет.
    """
    return commands.register_property(_repository(), label, address,
                                      has_cold_water, has_hot_water,
                                      has_sewage, gvs_heat_norm)


def rename_property(apartment_id: int, label: str, address: str = "") -> None:
    """Изменить наименование или адрес объекта."""
    commands.rename_property(_repository(), apartment_id, label, address)


def change_service_composition(apartment_id: int, has_cold_water: bool,
                               has_hot_water: bool, has_sewage: bool,
                               gvs_heat_norm: Decimal) -> None:
    """Изменить состав подведённых услуг и норматив подогрева."""
    commands.change_service_composition(_repository(), apartment_id,
                                        has_cold_water, has_hot_water,
                                        has_sewage, gvs_heat_norm)


def decommission_property(apartment_id: int, on_date: date) -> None:
    """Вывести объект из эксплуатации: продан, больше не сдаётся.

    Действующий договор не прекращается: предупредить, что в объекте живёт
    жилец, обязан прикладной слой, у которого есть обе стороны.
    """
    commands.decommission_property(_repository(), apartment_id, on_date)


def recommission_property(apartment_id: int) -> None:
    """Вернуть объект в эксплуатацию."""
    commands.recommission_property(_repository(), apartment_id)


__all__ = [
    "Apartment", "PropertyNotFound", "LabelMissing", "HeatNormMissing",
    "get_property", "list_properties",
    "register_property", "rename_property", "change_service_composition",
    "decommission_property", "recommission_property",
]
