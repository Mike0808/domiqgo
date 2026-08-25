"""Публичный API Metering — единственная дверь для остальных модулей.

Спецификация называет операции существительными (`GetExpectedMeters`,
`SubmitReadings`); здесь они функции в змеином регистре — соответствие
однозначное и записано в таблице ниже.

| Спецификация | Здесь |
|---|---|
| `GetExpectedMeters(apartment_id)` | `get_expected_meters` |
| `GetReadings(apartment_id, period)` | `get_readings` |
| `SubmitReadings` | `submit_readings` |

**Чего здесь пока нет.** `GetConsumption` не заведён: вычитание показаний и
правило монотонности живут в `billing/services/calculation.py` и переезжают
шагом **C2d**. До тех пор Billing спрашивает базу отсчёта значением
(`get_baseline_value`) и вычитает сам — ровно как раньше. Команды
`RegisterMeter`, `CorrectReading`, `ClosePeriod`, `ReopenPeriod` появятся на
C2f и C2g вместе с событиями и замком периода.

**Это точка сборки модуля.** Правило 3.5 запрещает `application/` обращаться
к `infrastructure/`, поэтому реализацию хранилища подставляет сюда `api/`.
Отсюда `_repository()` — и импорт внутри функции: `api/__init__` попадает в
граф импортов раньше, чем Django готов отдать модели.
"""

from datetime import date
from decimal import Decimal

from ..application import commands, queries
from ..domain.catalogue import RESOURCES, UNITS, UnknownResource


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


def get_baseline_value(apartment_id: int, resource: str,
                       period: date) -> Decimal | None:
    """Последнее показание до периода, либо `None`, если его не было.

    «Показания не было» — нормальный ответ, а не ошибка модуля. Чем его
    заменить (начальным значением прибора) и считать ли отсутствие обоих
    ошибкой, на шаге C2c по-прежнему решает Billing; правило переезжает
    сюда на C2d.
    """
    return queries.value_before(_repository(), apartment_id, resource, period)


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

def submit_readings(apartment_id: int, period: date,
                    values: dict[str, Decimal],
                    entered_by_tenant: bool = False) -> None:
    """Сдать комплект показаний за период одной операцией."""
    commands.submit_readings(_repository(), apartment_id, period, values,
                             entered_by_tenant)


__all__ = [
    "UnknownResource",
    "get_expected_meters", "get_readings", "get_baseline_value",
    "has_meters", "has_readings", "resources", "units",
    "submit_readings",
]
