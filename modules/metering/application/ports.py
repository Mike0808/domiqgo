"""Порт хранилища: то, что `application/` вправе требовать от инфраструктуры.

Правило 3.5 запрещает `application/` обращаться к `infrastructure/` напрямую.
Реализацию подставляет `api/` — единственный слой, которому видны обе стороны.
"""

from datetime import date
from decimal import Decimal
from typing import Protocol


class MeteringRepository(Protocol):
    def meters_at(self, apartment_id: int) -> list: ...

    def readings_at(self, apartment_id: int, period: date) -> dict[str, Decimal]: ...

    def previous_values(self, apartment_id: int, resources,
                        period: date) -> dict[str, Decimal]: ...

    def store_readings(self, apartment_id: int, period: date,
                       values: dict[str, Decimal],
                       entered_by_tenant: bool) -> None: ...

    def has_meters(self, apartment_id: int) -> bool: ...

    def has_readings(self, apartment_id: int) -> bool: ...
