"""Перевод между объектом домена и строкой таблицы."""

from datetime import date

from ..domain.property import Apartment
from . import models


def _to_domain(row) -> Apartment:
    return Apartment(
        apartment_id=row.pk, label=row.label,
        has_cold_water=row.has_cold_water, has_hot_water=row.has_hot_water,
        has_sewage=row.has_sewage, gvs_heat_norm=row.gvs_heat_norm,
        address=row.address, decommissioned_on=row.decommissioned_on)


def load(apartment_id: int) -> Apartment | None:
    row = models.Apartment.objects.filter(pk=apartment_id).first()
    return None if row is None else _to_domain(row)


def load_all(include_decommissioned: bool) -> list[Apartment]:
    rows = models.Apartment.objects.all()
    if not include_decommissioned:
        rows = rows.filter(decommissioned_on__isnull=True)
    return [_to_domain(row) for row in rows.order_by("label")]


def save_service_state(apartment: Apartment) -> None:
    """Записать состояние эксплуатации.

    Точечно, а не объектом целиком: в таблице лежат поля чужих модулей —
    арендная ставка, политика округления, тип счётчика, — и перезапись строки
    домена затёрла бы их значениями, которых домен не знает.
    """
    models.Apartment.objects.filter(pk=apartment.apartment_id).update(
        decommissioned_on=apartment.decommissioned_on)


def create(label: str, address: str, has_cold_water: bool, has_hot_water: bool,
           has_sewage: bool, gvs_heat_norm) -> int:
    """Завести объект и вернуть его идентификатор.

    Поля чужих модулей — арендная ставка, интернет, политика округления —
    остаются со своими умолчаниями: домен о них не знает, а прикладной слой
    дописывает их следом.
    """
    return models.Apartment.objects.create(
        label=label, address=address, has_cold_water=has_cold_water,
        has_hot_water=has_hot_water, has_sewage=has_sewage,
        gvs_heat_norm=gvs_heat_norm).pk


def save_description(apartment: Apartment) -> None:
    """Записать то, чем владеет Properties, не тронув временных жильцов."""
    models.Apartment.objects.filter(pk=apartment.apartment_id).update(
        label=apartment.label, address=apartment.address,
        has_cold_water=apartment.has_cold_water,
        has_hot_water=apartment.has_hot_water,
        has_sewage=apartment.has_sewage,
        gvs_heat_norm=apartment.gvs_heat_norm)
