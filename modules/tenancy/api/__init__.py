"""Публичный API Tenancy — единственная дверь для остальных модулей.

| Спецификация | Здесь |
|---|---|
| `StartTenancy` | `start_tenancy` |
| `EndTenancy` | `end_tenancy` |
| `GetTenancyFor(property_id, period)` | `tenancy_for` |
| `GetTenancy(tenancy_id)` | `get_tenancy` |
| `GetActiveTenancyForAccount(account_id)` | `active_tenancy_for_account` |
| `ListTenanciesFor(property_id)` | `list_tenancies_for` |

**Чего здесь пока нет.** `RenewTenancy` и `CorrectTenancy` — вместе с
диалогом подтверждения дат (шаг **D2**), где владельцу впервые понадобится
исправлять договор.

**«Сегодня» приходит снаружи.** Какой день считать текущим — вопрос
интерфейса; модуль не читает часы, и потому один и тот же запрос отвечает
одинаково в тесте и в проде.
"""

from datetime import date

from ..application import commands, queries
from ..application.commands import PropertyNotFound, TenancyNotFound
from ..domain.history import PeriodOverlap, PropertyOutOfService
from ..domain.tenancy import AlreadyEnded, EndBeforeStart, Tenancy, Terms


def _repository():
    """Импорт внутри функции: `api/__init__` попадает в граф импортов раньше,
    чем Django готов отдать модели."""
    from ..infrastructure import repository

    return repository


# ------------------------------------------------------------------- запросы

def tenancy_for(property_id: int, period_start: date) -> Tenancy | None:
    """Договор, действовавший на дату начала расчётного периода (ADR-0024),
    или `None`, если объект пустовал."""
    return queries.tenancy_for(_repository(), property_id, period_start)


def get_tenancy(tenancy_id: int) -> Tenancy | None:
    return queries.get_tenancy(_repository(), tenancy_id)


def active_tenancy_for_account(account_id: int, today: date) -> Tenancy | None:
    """Действующий договор учётной записи — какой объект показывать жильцу."""
    return queries.active_tenancy_for_account(_repository(), account_id, today)


def list_tenancies_for(property_id: int) -> list[Tenancy]:
    """История заселений объекта, от ранних к поздним."""
    return queries.list_tenancies_for(_repository(), property_id)


# ------------------------------------------------------------------- команды

def start_tenancy(property_id: int, account_id: int, full_name: str,
                  started_on: date, terms: Terms) -> int:
    """Заселить. Поднимает `PropertyNotFound`, `PropertyOutOfService`,
    `PeriodOverlap`. Возвращает номер договора."""
    return commands.start_tenancy(_repository(), property_id, account_id,
                                  full_name, started_on, terms)


def end_tenancy(tenancy_id: int, on: date) -> None:
    """Зафиксировать выезд. Поднимает `TenancyNotFound`, `EndBeforeStart`,
    `AlreadyEnded`."""
    commands.end_tenancy(_repository(), tenancy_id, on)


__all__ = [
    "Tenancy", "Terms",
    "PropertyNotFound", "TenancyNotFound", "PeriodOverlap",
    "PropertyOutOfService", "EndBeforeStart", "AlreadyEnded",
    "tenancy_for", "get_tenancy", "active_tenancy_for_account",
    "list_tenancies_for", "start_tenancy", "end_tenancy",
]
