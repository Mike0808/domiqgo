"""Оркестрация команд: принять, дёрнуть домен, сохранить, опубликовать событие.

Правил здесь нет — все они в `domain/schedule.py`. Здесь порядок действий и
единственное место модуля, откуда публикуются события (правило 4.4).
"""

from datetime import date
from decimal import Decimal

from bus import publish

from ..events import (
    TariffVersionCorrected, TariffVersionPublished, TariffVersionWithdrawn,
)
from .ports import ScheduleRepository


def publish_tariff_version(repository: ScheduleRepository, utility: str,
                           rate: Decimal, effective_from: date,
                           source_name: str = "", source_url: str = "") -> None:
    """Ввести новую ставку на услугу, действующую с даты."""
    schedule = repository.load(utility)
    version = schedule.publish(rate, effective_from, source_name, source_url)
    repository.save(schedule)
    publish(TariffVersionPublished(
        utility=version.utility, rate=version.rate,
        effective_from=version.effective_from,
        source_name=version.source_name, source_url=version.source_url,
    ))


def correct_tariff_version(repository: ScheduleRepository, utility: str,
                           was_effective_from: date, **changes) -> None:
    """Исправить опечатку в уже введённой версии.

    Отрезок действия для события снимается **после** правки: если исправляли
    дату, затронутым оказывается новый отрезок, а не прежний.
    """
    schedule = repository.load(utility)
    previous, corrected = schedule.correct(was_effective_from, **changes)
    repository.save(schedule)
    starts, ends = schedule.effective_range(corrected.effective_from)
    publish(TariffVersionCorrected(
        utility=corrected.utility, effective_from=starts, effective_until=ends,
        previous_rate=previous.rate, new_rate=corrected.rate,
    ))


def withdraw_tariff_version(repository: ScheduleRepository, utility: str,
                            effective_from: date) -> None:
    """Убрать версию, введённую по ошибке."""
    schedule = repository.load(utility)
    version = schedule.withdraw(effective_from)
    repository.save(schedule)
    publish(TariffVersionWithdrawn(
        utility=version.utility, effective_from=version.effective_from,
        withdrawn_rate=version.rate,
    ))
