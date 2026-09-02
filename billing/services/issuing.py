"""Выставление счёта — отдельное действие владельца (шаг E4, дефект №35).

Разделены не расчёт и показ, а расчёт и предъявление: черновик считается и
пересчитывается как раньше (сценарий «ввёл показания — увидел сумму» цел),
а выставление фиксирует счёт, назначает срок оплаты (ADR-0013) и закрывает
период показаний (ADR-0012). Событие публикуется отсюда — из легаси-слоя,
контракт лежит в `modules/billing/events`.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from bus import publish
from modules.billing.events import InvoiceIssued
from modules.metering import api as metering

from ..models import BillingPolicy


class InvoiceAlreadyIssued(Exception):
    """Выставленный счёт неизменяем (инв. 2 Billing): ни пересчитать, ни
    выставить второй раз."""


class DraftWithoutTenancy(Exception):
    """Счёт без договора не предъявляется (инв. 5): сначала назначьте
    договор в форме начисления."""


@transaction.atomic
def issue_invoice(statement, at=None):
    """Предъявить счёт: зафиксировать, назначить срок, закрыть период."""
    if statement.is_issued:
        raise InvoiceAlreadyIssued(
            f"Счёт {statement} уже выставлен {statement.issued_at:%d.%m.%Y}.")
    if statement.tenancy_id is None:
        raise DraftWithoutTenancy(
            f"У счёта {statement} не определён договор — выставлять некому.")
    moment = at or timezone.now()
    statement.issued_at = moment
    statement.due_date = moment.date() + timedelta(days=BillingPolicy.get().due_days)
    statement.save(update_fields=["issued_at", "due_date"])
    metering.close_period(statement.apartment_id, statement.period)
    publish(InvoiceIssued(
        invoice_id=statement.pk, tenancy_id=statement.tenancy_id,
        property_id=statement.apartment_id, period=statement.period,
        total=statement.total, due_date=statement.due_date, at=moment))
    return statement
