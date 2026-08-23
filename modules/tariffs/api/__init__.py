"""Публичный API Tariffs — единственная дверь для остальных модулей.

Спецификация называет операции существительными (`GetRateOn`,
`PublishTariffVersion`); здесь они функции в змеином регистре — соответствие
однозначное и записано в таблице ниже. Заводить классы-команды ради буквального
совпадения с текстом спецификации значило бы добавить слой без содержания.

| Спецификация | Здесь |
|---|---|
| `GetRateOn(utility, on_date)` | `get_rate_on` |
| `GetRatesOn(on_date)` | `get_rates_on` |
| `ListVersions(utility)` | `list_versions` |
| `PublishTariffVersion` | `publish_tariff_version` |
| `CorrectTariffVersion` | `correct_tariff_version` |
| `WithdrawTariffVersion` | `withdraw_tariff_version` |

**Это точка сборки модуля.** Правило 3.5 запрещает `application/` обращаться к
`infrastructure/`, поэтому реализацию хранилища подставляет сюда `api/` —
единственный слой, которому видны обе стороны. Отсюда `_repository()`.

Правил здесь нет (правило 3.7): каждая функция принимает аргументы, добавляет
хранилище и зовёт `application`.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..application import commands, queries
from ..domain.catalogue import UTILITIES, UnknownUtility
from ..domain.schedule import VersionNotFound


@dataclass(frozen=True)
class Rate:
    """Ставка с реквизитами источника — то, что уезжает за границу модуля.

    Отдельный тип, а не доменный `TariffVersion`: иначе вызывающему пришлось бы
    импортировать `domain/` чужого модуля, чтобы назвать тип ответа, — то есть
    ровно то, что запрещают правила 1.1 и 1.2.
    """

    utility: str
    rate: Decimal
    effective_from: date
    source_name: str
    source_url: str


def _repository():
    """Импорт внутри функции: `api/__init__` попадает в граф импортов раньше,
    чем Django готов отдать модели, и импорт сверху ломает `manage.py`."""
    from ..infrastructure import repository

    return repository


def _to_rate(version) -> Rate:
    return Rate(utility=version.utility, rate=version.rate,
                effective_from=version.effective_from,
                source_name=version.source_name, source_url=version.source_url)


# ------------------------------------------------------------------- запросы

def get_rate_on(utility: str, on_date: date) -> Rate | None:
    """Ставка, действовавшая на дату, либо `None`, если её не было.

    Принимает **дату, а не расчётный период**: Tariffs не знает такого понятия
    — это словарь Billing и Metering. Какую дату подставить, решает
    вызывающий, и вопрос «что делать, если ставка сменилась в середине месяца»
    остаётся там, где есть данные для ответа
    ([ADR-0004](../../../docs/architecture/adr/0004-tariff-version-period-resolution.md)).
    """
    version = queries.rate_on(_repository(), utility, on_date)
    return None if version is None else _to_rate(version)


def get_rates_on(on_date: date) -> dict[str, Rate]:
    """Действующие на дату ставки по всем услугам каталога — один вызов вместо
    семи. Услуги, у которых ставки на эту дату нет, в ответе отсутствуют."""
    return {utility: _to_rate(version)
            for utility, version in queries.rates_on(_repository(), on_date).items()}


def list_versions(utility: str) -> list[Rate]:
    """Вся история версий услуги по возрастанию даты начала действия."""
    return [_to_rate(v) for v in queries.list_versions(_repository(), utility)]


def utilities() -> dict[str, str]:
    """Каталог услуг: код → название. Нужен интерфейсному слою для выбора."""
    return dict(UTILITIES)


# ------------------------------------------------------------------- команды

def publish_tariff_version(utility: str, rate: Decimal, effective_from: date,
                           source_name: str = "", source_url: str = "") -> None:
    commands.publish_tariff_version(
        _repository(), utility, rate, effective_from, source_name, source_url)


def correct_tariff_version(utility: str, was_effective_from: date, **changes) -> None:
    """Изменения передаются именами полей: `rate`, `effective_from`,
    `source_name`, `source_url`. `was_effective_from` — дата, по которой версия
    опознаётся сейчас."""
    commands.correct_tariff_version(
        _repository(), utility, was_effective_from, **changes)


def withdraw_tariff_version(utility: str, effective_from: date) -> None:
    commands.withdraw_tariff_version(_repository(), utility, effective_from)


__all__ = [
    "Rate", "UnknownUtility", "VersionNotFound",
    "get_rate_on", "get_rates_on", "list_versions", "utilities",
    "publish_tariff_version", "correct_tariff_version", "withdraw_tariff_version",
]
