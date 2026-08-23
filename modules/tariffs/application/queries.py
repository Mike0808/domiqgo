"""Чтение: ставка на дату, ставки на дату, история версий."""

from datetime import date

from ..domain.schedule import TariffVersion
from .ports import ScheduleRepository


def rate_on(repository: ScheduleRepository, utility: str,
            on_date: date) -> TariffVersion | None:
    """Версия, действовавшая на дату, либо `None` — «ставки нет».

    Отсутствие ставки — нормальный результат, а не ошибка модуля. Ошибкой его
    назначает Billing.
    """
    return repository.load(utility).rate_on(on_date)


def rates_on(repository: ScheduleRepository,
             on_date: date) -> dict[str, TariffVersion]:
    """Действующие на дату версии по всем услугам каталога."""
    return repository.rates_on(on_date)


def list_versions(repository: ScheduleRepository,
                  utility: str) -> list[TariffVersion]:
    """Вся история версий услуги по возрастанию даты начала действия."""
    return repository.load(utility).versions
