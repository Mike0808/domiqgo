"""Команды платёжного контура — в модуле (шаг H2).

С этого шага события Payments публикуются отсюда — из `application/`, где
правило 4.4 всегда их ждало; легаси-`intake.py` остался интерфейсной
оболочкой. Перечень непогашенных счетов даёт Billing запросом
`ListOutstandingInvoices`, правило выбора — домен Payments (ADR-0014).
Счёт команды не трогают ни строчкой (дефект №15): погашение выводит сверка
Billing, услышав событие.
"""

from decimal import Decimal

from django.utils import timezone

from bus import publish
from modules.billing import api as billing

from ..domain import payment as rules
from ..events import (
    PaymentConfirmed, PaymentRejected, PaymentSubmitted, PaymentVoided,
)
from ..infrastructure import repository


def earliest_unpaid_invoice(tenancy_id, property_id=None):
    """Счёт, к которому ляжет следующий платёж (правило — ADR-0014).

    Счета без договора (наследие миграции E2) учитываются по объекту
    договора и уйдут вместе с legacy-`billing/`.
    """
    outstanding = billing.list_outstanding_invoices(tenancy_id, property_id)
    claimed = repository.claimed_invoice_ids(
        [invoice["invoice_id"] for invoice in outstanding])
    return rules.choose_invoice(outstanding, claimed)


def submit_receipt(tenancy_id, property_id, file, source, filename=None):
    invoice = earliest_unpaid_invoice(tenancy_id, property_id)
    if invoice is None:
        raise rules.NoUnpaidStatementError("Нет неоплаченных начислений.")
    payment_id = repository.add_submitted(invoice["invoice_id"], source,
                                          file, filename)
    publish(PaymentSubmitted(payment_id=payment_id,
                             statement_id=invoice["invoice_id"],
                             tenancy_id=invoice["tenancy_id"], source=source,
                             at=timezone.now()))
    return {"payment_id": payment_id, "invoice_id": invoice["invoice_id"],
            "period": invoice["period"]}


def confirm_payment(payment_id, amount):
    """Признать заявленный платёж и указать сумму (шаг E1)."""
    amount = rules.checked_amount(amount)
    payment = repository.captured(payment_id)
    repository.set_state(payment_id, rules.CONFIRMED, amount=amount)
    publish(PaymentConfirmed(payment_id=payment_id,
                             statement_id=payment["statement_id"],
                             tenancy_id=_tenancy_of(payment["statement_id"]),
                             amount=amount, at=timezone.now()))


def record_payment(invoice_id, amount, note="") -> int:
    """Отметить полученный платёж вручную, без чека (шаг E1).

    Платёж рождается сразу подтверждённым — владелец и есть подтверждающий.
    """
    invoice = billing.get_invoice(invoice_id)
    if invoice is None or invoice["issued_at"] is None:
        raise rules.InvoiceNotIssued(
            f"Счёт #{invoice_id} не выставлен — сначала предъявите его.")
    amount = rules.checked_amount(amount)
    payment_id = repository.add_confirmed(invoice_id, amount, note)
    publish(PaymentConfirmed(payment_id=payment_id, statement_id=invoice_id,
                             tenancy_id=invoice["tenancy_id"], amount=amount,
                             at=timezone.now()))
    return payment_id


def reject_payment(payment_id, note=""):
    """Отклонить заявленный платёж.

    Сумма отклонённого в сверке никогда не участвовала — Billing событие не
    слушает, счёт возвращается к «не оплачено» сам, силой вычисления.
    """
    payment = repository.captured(payment_id)
    if note:
        repository.set_state(payment_id, rules.REJECTED, note=note)
    else:
        repository.set_state(payment_id, rules.REJECTED)
    publish(PaymentRejected(payment_id=payment_id,
                            statement_id=payment["statement_id"],
                            tenancy_id=_tenancy_of(payment["statement_id"]),
                            reason=note, at=timezone.now()))


def void_payment(payment_id, reason):
    """Отменить ранее подтверждённый платёж (шаг E5, дефект №16).

    Платёж — свершившийся факт: его не удаляют. Правило перехода — в домене,
    сумма изымается из сверки событием.
    """
    payment = repository.captured(payment_id)
    status, note = rules.voided(payment["status"], payment["note"], reason)
    repository.set_state(payment_id, status, note=note)
    publish(PaymentVoided(
        payment_id=payment_id, statement_id=payment["statement_id"],
        tenancy_id=_tenancy_of(payment["statement_id"]),
        amount=(payment["amount"] if payment["amount"] is not None
                else Decimal("0")),
        reason=reason, at=timezone.now()))


def _tenancy_of(invoice_id):
    """Договор счёта — в событие (F3): получателя ищут по договору."""
    invoice = billing.get_invoice(invoice_id)
    return invoice["tenancy_id"] if invoice is not None else None
