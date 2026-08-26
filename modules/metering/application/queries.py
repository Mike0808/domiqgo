"""Чтение: реестр приборов, комплект показаний, расход за период."""

from datetime import date
from decimal import Decimal

from ..domain.point import MeteringPoint
from .ports import MeteringRepository


def expected_meters(repository: MeteringRepository, apartment_id: int) -> list:
    """Приборы, зарегистрированные в точке учёта."""
    return repository.meters_at(apartment_id)


def readings(repository: MeteringRepository, apartment_id: int,
             period: date) -> dict[str, Decimal]:
    return repository.readings_at(apartment_id, period)


def consumption(repository: MeteringRepository, apartment_id: int,
                period: date, resources) -> dict:
    """Расход за период по каждому запрошенному ресурсу.

    Оркестрация и только: собрать точку учёта из того, что лежит в хранилище,
    и спросить у неё. Правила — база отсчёта и монотонность — в `domain/`.
    """
    resources = list(resources)
    point = MeteringPoint(
        apartment_id=apartment_id,
        initial_values={m.resource: m.initial_value
                        for m in repository.meters_at(apartment_id)},
        previous_values=repository.previous_values(apartment_id, resources,
                                                   period),
        current_values=repository.readings_at(apartment_id, period),
    )
    return point.consumption(resources)
