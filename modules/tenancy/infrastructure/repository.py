"""Перевод между договорами домена и строками таблиц."""

from datetime import date

from ..domain.history import PropertyHistory
from ..domain.tenancy import Tenancy, Terms
from . import models


def _to_domain(row: models.Tenancy) -> Tenancy:
    return Tenancy(
        tenancy_id=row.pk, property_id=row.property_id, account_id=row.account_id,
        full_name=row.full_name, started_on=row.started_on, ended_on=row.ended_on,
        start_confirmed=row.start_confirmed,
        terms=Terms(rent=row.rent, internet=row.internet, other_fixed=row.other_fixed))


def _fields_of(tenancy: Tenancy) -> dict:
    return dict(
        property_id=tenancy.property_id, account_id=tenancy.account_id,
        full_name=tenancy.full_name, started_on=tenancy.started_on,
        ended_on=tenancy.ended_on, start_confirmed=tenancy.start_confirmed,
        rent=tenancy.terms.rent, internet=tenancy.terms.internet,
        other_fixed=tenancy.terms.other_fixed)


def load_history(property_id: int) -> PropertyHistory:
    """История целиком: непересечение периодов проверяется по всем договорам
    объекта, и на куске его не проверить."""
    rows = models.Tenancy.objects.filter(property_id=property_id)
    out = models.OutOfService.objects.filter(property_id=property_id).exists()
    return PropertyHistory(property_id, [_to_domain(r) for r in rows], out_of_service=out)


def add(tenancy: Tenancy) -> Tenancy:
    row = models.Tenancy.objects.create(**_fields_of(tenancy))
    return _to_domain(row)


def save(tenancy: Tenancy) -> None:
    models.Tenancy.objects.filter(pk=tenancy.tenancy_id).update(**_fields_of(tenancy))


def get(tenancy_id: int) -> Tenancy | None:
    row = models.Tenancy.objects.filter(pk=tenancy_id).first()
    return None if row is None else _to_domain(row)


def active_for_account(account_id: int, day: date) -> Tenancy | None:
    """Действующий в этот день договор записи. При нескольких (наследие
    миграции до D3) — самый ранний, как и в истории объекта."""
    rows = (models.Tenancy.objects.filter(account_id=account_id, started_on__lte=day)
            .order_by("started_on", "id"))
    return next((_to_domain(r) for r in rows if _to_domain(r).covers(day)), None)


def list_for_account(account_id: int) -> list[Tenancy]:
    rows = (models.Tenancy.objects.filter(account_id=account_id)
            .order_by("started_on", "id"))
    return [_to_domain(r) for r in rows]


def mark_out_of_service(property_id: int, out: bool) -> None:
    if out:
        models.OutOfService.objects.get_or_create(property_id=property_id)
    else:
        models.OutOfService.objects.filter(property_id=property_id).delete()
