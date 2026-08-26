"""Публичный API Properties — единственная дверь для остальных модулей.

| Спецификация | Здесь |
|---|---|
| `GetProperty(property_id)` | `get_property` |
| `ListProperties(include_decommissioned)` | `list_properties` |
| `DecommissionProperty` | `decommission_property` |
| `RecommissionProperty` | `recommission_property` |

**Чего здесь пока нет и почему.** `RegisterProperty`, `RenameProperty` и
`ChangeServiceComposition` не заведены: сегодня объект заводят и правят обычной
формой админки, и все три команды свелись бы к `obj.save()` без единого
правила. Они появятся вместе с инвариантами, которые им предстоит держать, —
на **C3c** (норматив подогрева) и **C3e** (адрес и непустое наименование).
Объявлять команду раньше правила значит заводить обёртку, которую потом всё
равно переписывать.

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

from ..application import commands, queries
from ..application.commands import PropertyNotFound
from ..domain.property import Apartment


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
    "Apartment", "PropertyNotFound",
    "get_property", "list_properties",
    "decommission_property", "recommission_property",
]
