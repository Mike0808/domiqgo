"""Оркестрация команд модуля.

Правил здесь нет — на шаге C2c их нет и в домене: перенос владения данными
не совмещается с переносом правил (правило 7.4). Правила приезжают на C2d,
события — на C2f.
"""

from datetime import date
from decimal import Decimal

from ..domain.catalogue import ensure_known
from .ports import MeteringRepository


def submit_readings(repository: MeteringRepository, apartment_id: int,
                    period: date, values: dict[str, Decimal],
                    entered_by_tenant: bool = False) -> None:
    """Сдать комплект показаний за период.

    Комплект целиком, а не по одному показанию: сдача — одна операция, и
    транзакционная граница в работающем коде уже совпадала с ней
    (`views.py`, `transaction.atomic` вокруг всех приборов сразу).
    """
    for resource in values:
        ensure_known(resource)
    repository.store_readings(apartment_id, period, values, entered_by_tenant)
