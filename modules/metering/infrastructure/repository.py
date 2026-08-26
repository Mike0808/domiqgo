"""Перевод между понятиями модуля и строками таблиц.

Репозиторий — единственный переводчик. Слой `application/` работает с
записями, не зная, где они лежат.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction

from . import models


@dataclass(frozen=True)
class MeterRecord:
    """Прибор так, как его видит модуль: без Django и без первичного ключа."""

    apartment_id: int
    resource: str
    serial_number: str
    initial_value: Decimal
    initial_date: date | None


def _to_record(row) -> MeterRecord:
    return MeterRecord(
        apartment_id=row.apartment_id, resource=row.resource,
        serial_number=row.serial_number, initial_value=row.initial_value,
        initial_date=row.initial_date)


def meters_at(apartment_id: int) -> list[MeterRecord]:
    """Реестр приборов точки учёта."""
    return [_to_record(row) for row in
            models.Meter.objects.filter(apartment_id=apartment_id)
            .order_by("resource")]


def readings_at(apartment_id: int, period: date) -> dict[str, Decimal]:
    """Комплект показаний за период: код ресурса → значение."""
    return {row.resource: row.value for row in
            models.MeterReading.objects.filter(apartment_id=apartment_id,
                                               period=period)}


def latest_value_before(apartment_id: int, resource: str,
                        period: date) -> Decimal | None:
    """Последнее показание до периода — то, от чего считается расход."""
    row = (models.MeterReading.objects
           .filter(apartment_id=apartment_id, resource=resource,
                   period__lt=period)
           .order_by("-period").first())
    return None if row is None else row.value


def previous_values(apartment_id: int, resources,
                    period: date) -> dict[str, Decimal]:
    """Базы отсчёта пачкой: ресурс → последнее показание до периода.

    Ресурсов у точки учёта единицы, поэтому запрос на каждый — не проблема;
    выигрыш от одного хитрого запроса не стоил бы того, что он перестанет
    читаться.
    """
    found = {}
    for resource in resources:
        value = latest_value_before(apartment_id, resource, period)
        if value is not None:
            found[resource] = value
    return found


@transaction.atomic
def store_readings(apartment_id: int, period: date, values: dict[str, Decimal],
                   entered_by_tenant: bool) -> None:
    """Записать комплект: существующие строки правятся, недостающие заводятся.

    Ровно то, что делало представление до шага C2c, — включая то, что сдача
    комплекта повторно перезаписывает прежние значения. Правила, ограничивающие
    перезапись, переезжают шагами C2d и C2g.
    """
    existing = {row.resource: row for row in
                models.MeterReading.objects.filter(apartment_id=apartment_id,
                                                   period=period)}
    for resource, value in values.items():
        row = existing.get(resource)
        if row is not None:
            row.value = value
            row.entered_by_tenant = entered_by_tenant
            row.save()
        else:
            models.MeterReading.objects.create(
                apartment_id=apartment_id, period=period, resource=resource,
                value=value, entered_by_tenant=entered_by_tenant)


def has_meters(apartment_id: int) -> bool:
    return models.Meter.objects.filter(apartment_id=apartment_id).exists()


def has_readings(apartment_id: int) -> bool:
    return models.MeterReading.objects.filter(apartment_id=apartment_id).exists()
