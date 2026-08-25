"""Чтение: реестр приборов, комплект показаний, база отсчёта."""

from datetime import date
from decimal import Decimal

from .ports import MeteringRepository


def expected_meters(repository: MeteringRepository, apartment_id: int) -> list:
    """Приборы, зарегистрированные в точке учёта."""
    return repository.meters_at(apartment_id)


def readings(repository: MeteringRepository, apartment_id: int,
             period: date) -> dict[str, Decimal]:
    return repository.readings_at(apartment_id, period)


def value_before(repository: MeteringRepository, apartment_id: int,
                 resource: str, period: date) -> Decimal | None:
    return repository.latest_value_before(apartment_id, resource, period)
