"""Публичный API Tenancy — единственная дверь для остальных модулей.

| Спецификация | Здесь |
|---|---|
| `StartTenancy` | `start_tenancy` |
| `EndTenancy` | `end_tenancy` |
| `GetTenancyFor(property_id, period)` | `tenancy_for` |
| `GetTenancy(tenancy_id)` | `get_tenancy` |
| `GetActiveTenancyForAccount(account_id)` | `active_tenancy_for_account` |
| `ListTenanciesFor(property_id)` | `list_tenancies_for` |

| `CorrectTenancy` | `correct_tenancy` |
| `RenewTenancy` | `renew_tenancy` |

**Исправление и продление — разные глаголы.** Продление — новый факт: с
такого-то числа условия другие; прежний договор продолжает действовать в
своём прошлом. Исправление — признание, что записанное было неверно с
самого начала; исправление даты заселения её же подтверждает (шаг **D2**).

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


def correct_tenancy(tenancy_id: int, *, started_on: date | None = None,
                    full_name: str | None = None,
                    terms: Terms | None = None) -> None:
    """Исправить сведения договора; исправление даты её же подтверждает.

    Подтвердить предложенную миграцией дату — вызвать с этой же датой.
    Пересечение проверяется только с подтверждёнными договорами объекта.
    """
    commands.correct_tenancy(_repository(), tenancy_id, started_on=started_on,
                             full_name=full_name, terms=terms)


def renew_tenancy(tenancy_id: int, on: date, terms: Terms,
                  full_name: str | None = None) -> int:
    """Продлить на новых условиях: завершить текущий договор днём раньше и
    открыть следующий с `on`. Возвращает номер нового договора."""
    return commands.renew_tenancy(_repository(), tenancy_id, on, terms,
                                  full_name=full_name)


__all__ = [
    "Tenancy", "Terms",
    "PropertyNotFound", "TenancyNotFound", "PeriodOverlap",
    "PropertyOutOfService", "EndBeforeStart", "AlreadyEnded",
    "tenancy_for", "get_tenancy", "active_tenancy_for_account",
    "list_tenancies_for", "start_tenancy", "end_tenancy",
    "correct_tenancy", "renew_tenancy",
]
