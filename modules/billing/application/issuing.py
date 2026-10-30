"""Выставление счёта — команда модуля (шаг E4, в модуле с H3).

Разделены не расчёт и показ, а расчёт и предъявление: черновик считается и
пересчитывается как раньше, а выставление фиксирует счёт, назначает срок
оплаты (ADR-0013) и закрывает период показаний (ADR-0012). Событие
публикуется отсюда — из `application/`, где правило 4.4 всегда его ждало.
"""

from django.utils import timezone

from bus import publish
from modules.metering import api as metering

from ..domain import invoice as rules
from ..events import InvoiceIssued
from ..infrastructure import repository


def issue_invoice(invoice_id, at=None) -> None:
    """Предъявить счёт: зафиксировать, назначить срок, закрыть период."""
    invoice = repository.get_invoice(invoice_id)
    if invoice is None:
        raise rules.InvoiceAlreadyIssued(f"Счёт #{invoice_id} не найден.")
    if invoice["issued_at"] is not None:
        raise rules.InvoiceAlreadyIssued(
            f"Счёт #{invoice_id} уже выставлен "
            f"{invoice['issued_at']:%d.%m.%Y}.")
    if invoice["tenancy_id"] is None:
        raise rules.DraftWithoutTenancy(
            f"У счёта #{invoice_id} не определён договор — выставлять "
            "некому.")
    moment = at or timezone.now()
    due = rules.due_date_for(moment, repository.due_days())
    repository.set_issued(invoice_id, moment, due)
    metering.close_period(invoice["property_id"], invoice["period"])
    publish(InvoiceIssued(
        invoice_id=invoice_id, tenancy_id=invoice["tenancy_id"],
        property_id=invoice["property_id"], period=invoice["period"],
        total=invoice["total"], due_date=due, at=moment))
