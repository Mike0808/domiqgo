"""Порт хранилища тарифных линий.

Правило 3.5 запрещает `application/` обращаться к `infrastructure/` напрямую:
оркестрация работает через порт, иначе подменить хранилище в тесте
невозможно. Реализацию подставляет `api/` — единственный слой, которому видны
обе стороны, то есть точка сборки модуля.

`Protocol`, а не абстрактный базовый класс: реализации не нужно ничего
наследовать, и `infrastructure/repository.py` остаётся обычным модулем с
функциями. Проверка структурная — совпали имена и подписи, значит подходит.
"""

from datetime import date
from typing import Protocol

from ..domain.schedule import TariffSchedule, TariffVersion


class ScheduleRepository(Protocol):
    def load(self, utility: str) -> TariffSchedule:
        """Тарифная линия услуги целиком, со всеми версиями."""

    def save(self, schedule: TariffSchedule) -> None:
        """Записать линию, заместив прежнее состояние услуги."""

    def rates_on(self, on_date: date) -> dict[str, TariffVersion]:
        """Действующие на дату версии по всем услугам — одним запросом."""
