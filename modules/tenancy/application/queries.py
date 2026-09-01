"""Чтение: договор периода, договор учётной записи, история объекта."""

from datetime import date

from ..domain.tenancy import Tenancy
from .ports import TenancyRepository


def tenancy_for(repository: TenancyRepository, property_id: int,
                period_start: date) -> Tenancy | None:
    """Договор периода — действовавший на дату начала периода (ADR-0024).
    Пустой ответ означает, что объект пустовал; что с этим делать, решает
    Billing."""
    return repository.load_history(property_id).of_record_for(period_start)


def get_tenancy(repository: TenancyRepository, tenancy_id: int) -> Tenancy | None:
    return repository.get(tenancy_id)


def active_tenancy_for_account(repository: TenancyRepository, account_id: int,
                               today: date) -> Tenancy | None:
    """Какой объект показывать вошедшему жильцу."""
    return repository.active_for_account(account_id, today)


def list_tenancies_for(repository: TenancyRepository, property_id: int) -> list[Tenancy]:
    return repository.load_history(property_id).tenancies
