"""Оркестрация команд модуля: принять, проверить, сохранить, объявить.

Правил здесь нет — они в `domain/`. Здесь порядок действий и единственное
место модуля, откуда публикуются события (правило 4.4).
"""

from datetime import date
from decimal import Decimal

from bus import publish

from ..domain.catalogue import ensure_known
from ..domain.point import ReadingNotFound
from ..events import (
    MeterReadingCorrected, MeterReadingsSubmitted, MeterRegistered,
)
from .ports import MeteringRepository


def register_meter(repository: MeteringRepository, apartment_id: int,
                   resource: str, initial_value: Decimal,
                   serial_number: str = "",
                   initial_date: date | None = None) -> None:
    """Ввести прибор в учёт.

    Начальное показание обязательно и не имеет умолчания: прибор без него
    заставил бы первый расчёт считать от неявного нуля, то есть предъявить
    жильцу расход за годы до него.
    """
    ensure_known(resource)
    repository.register_meter(apartment_id, resource, initial_value,
                              serial_number, initial_date)
    publish(MeterRegistered(
        apartment_id=apartment_id, resource=resource,
        serial_number=serial_number, initial_value=initial_value,
        initial_date=initial_date,
    ))


def submit_readings(repository: MeteringRepository, apartment_id: int,
                    period: date, values: dict[str, Decimal],
                    entered_by_tenant: bool = False) -> None:
    """Сдать комплект показаний за период.

    Комплект целиком, а не по одному показанию: сдача — одна операция, и
    транзакционная граница в работающем коде уже совпадала с ней
    (`views.py`, `transaction.atomic` вокруг всех приборов сразу). Событие
    поэтому тоже одно на комплект.

    Пустой комплект не объявляется: сдавать нечего — не событие.
    """
    for resource in values:
        ensure_known(resource)
    repository.store_readings(apartment_id, period, values, entered_by_tenant)
    if not values:
        return
    publish(MeterReadingsSubmitted(
        apartment_id=apartment_id, period=period,
        resources=tuple(sorted(values)), entered_by_tenant=entered_by_tenant,
    ))


def correct_reading(repository: MeteringRepository, apartment_id: int,
                    period: date, resource: str, value: Decimal) -> None:
    """Исправить ранее внесённое показание.

    Смысл — «этого показания не должно было быть таким», а не «прибор
    накрутил ещё». Различение принципиально: первое признаёт ошибку, второе
    фиксирует расход, и на выставленный счёт они влияют по-разному. Отсюда
    отдельная команда и отдельное событие.

    Показания, которого не было, не исправляют — такую операцию выражает
    сдача.
    """
    ensure_known(resource)
    previous = repository.readings_at(apartment_id, period).get(resource)
    if previous is None:
        raise ReadingNotFound(
            f"За {period:%m.%Y} по «{resource}» показание не вносилось: "
            "исправлять нечего.")
    repository.store_readings(apartment_id, period, {resource: value},
                              entered_by_tenant=False)
    publish(MeterReadingCorrected(
        apartment_id=apartment_id, period=period, resource=resource,
        previous_value=previous, new_value=value,
    ))
