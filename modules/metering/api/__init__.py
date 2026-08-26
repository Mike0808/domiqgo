"""Публичный API Metering — единственная дверь для остальных модулей.

Спецификация называет операции существительными (`GetExpectedMeters`,
`SubmitReadings`); здесь они функции в змеином регистре — соответствие
однозначное и записано в таблице ниже.

| Спецификация | Здесь |
|---|---|
| `GetExpectedMeters(apartment_id)` | `get_expected_meters` |
| `GetReadings(apartment_id, period)` | `get_readings` |
| `GetConsumption(apartment_id, period)` | `get_consumption` |
| `SubmitReadings` | `submit_readings` |
| `RegisterMeter` | `register_meter` |
| `CorrectReading` | `correct_reading` |

**Чего здесь пока нет.** Команды `ClosePeriod` и `ReopenPeriod` появятся на
C2g вместе с замком периода.

**События объявлены, подписчиков нет.** Пересчёт счёта после сдачи показаний
делает вызывающий, синхронно; перевод его на подписку — часть шага **E4**, где
счёт перестаёт возникать сам собой. Подробности — в `events/`.

**Это точка сборки модуля.** Правило 3.5 запрещает `application/` обращаться
к `infrastructure/`, поэтому реализацию хранилища подставляет сюда `api/`.
Отсюда `_repository()` — и импорт внутри функции: `api/__init__` попадает в
граф импортов раньше, чем Django готов отдать модели.
"""

from datetime import date
from decimal import Decimal

from ..application import commands, queries
from ..domain.catalogue import RESOURCES, UNITS, UnknownResource
from ..domain.point import (
    BaselineMissing, Consumption, ReadingNotFound, ReadingWentBackwards,
)


def _repository():
    from ..infrastructure import repository

    return repository


# ------------------------------------------------------------------- запросы

def get_expected_meters(apartment_id: int) -> list:
    """Приборы точки учёта: вид ресурса, заводской номер, начальное значение.

    Возвращает `MeterRecord` — замкнутые датаклассы без Django, поэтому
    вызывающему не нужно ничего знать о моделях модуля.
    """
    return queries.expected_meters(_repository(), apartment_id)


def get_readings(apartment_id: int, period: date) -> dict[str, Decimal]:
    """Уже внесённые за период значения: код ресурса → показание."""
    return queries.readings(_repository(), apartment_id, period)


def get_consumption(apartment_id: int, period: date, resources) -> dict:
    """Расход за период по каждому запрошенному ресурсу.

    Возвращает `Consumption`: расход и обе границы интервала. Границы нужны
    счёту — жилец должен видеть, из чего получилась цифра, — а вычитает их
    Metering, потому что при замене прибора вычитание перестаёт быть простой
    разностью.

    Отказы: `BaselineMissing`, если у части ресурсов нет ни предыдущего
    показания, ни начального значения прибора; `ReadingWentBackwards`, если
    показание меньше базы отсчёта. Оба — правила прибора, а не счёта, и с
    шага C2d живут здесь.
    """
    return queries.consumption(_repository(), apartment_id, period, resources)


def has_meters(apartment_id: int) -> bool:
    """Есть ли в точке учёта зарегистрированные приборы."""
    return _repository().has_meters(apartment_id)


def has_readings(apartment_id: int) -> bool:
    """Сдавались ли по этой точке учёта показания."""
    return _repository().has_readings(apartment_id)


def resources() -> dict[str, str]:
    """Каталог видов ресурса: код → название."""
    return dict(RESOURCES)


def units() -> dict[str, str]:
    """Единицы измерения по видам ресурса: код → «м³», «кВт·ч»."""
    return dict(UNITS)


# ------------------------------------------------------------------- команды

def register_meter(apartment_id: int, resource: str, initial_value: Decimal,
                   serial_number: str = "",
                   initial_date: date | None = None) -> None:
    """Ввести прибор в учёт: вид ресурса, номер, начальное показание."""
    commands.register_meter(_repository(), apartment_id, resource,
                            initial_value, serial_number, initial_date)


def submit_readings(apartment_id: int, period: date,
                    values: dict[str, Decimal],
                    entered_by_tenant: bool = False) -> None:
    """Сдать комплект показаний за период одной операцией."""
    commands.submit_readings(_repository(), apartment_id, period, values,
                             entered_by_tenant)


def correct_reading(apartment_id: int, period: date, resource: str,
                    value: Decimal) -> None:
    """Исправить ранее внесённое показание.

    Отдельно от сдачи: сдача — ежемесячный ход событий, исправление —
    признание ошибки в уже сданных данных. События тоже разные.
    """
    commands.correct_reading(_repository(), apartment_id, period, resource,
                             value)


__all__ = [
    "UnknownResource",
    "Consumption", "BaselineMissing", "ReadingNotFound",
    "ReadingWentBackwards",
    "get_expected_meters", "get_readings", "get_consumption",
    "has_meters", "has_readings", "resources", "units",
    "register_meter", "submit_readings", "correct_reading",
]
