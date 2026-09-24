"""Интерфейсная оболочка платёжного потока (шаг H2).

Команды переехали в `modules/payments/application`; события публикуются
оттуда — из application/, где правило 4.4 всегда их ждало. Здесь остались:

- привязка чека к жильцу: договор находит интерфейс — ADR-0014 отдаёт
  Payments лишь правило выбора счёта, а «кто платит» знает Tenancy;
- переводчики с языка моделей на язык идентификаторов модуля — админка и
  бот пока держат в руках объекты, а не id;
- реэкспорт исключений для старых импортов.
"""

from django.utils import timezone

from modules.payments import api as payments
from modules.payments.api import (  # noqa: F401 — реэкспорт для старых импортов
    InvoiceNotIssued, NoUnpaidStatementError, OnlyConfirmedIsVoided,
    PositiveAmountRequired, VoidReasonRequired,
)

from ..models import MonthlyStatement, Payment


def attach_receipt(tenant, file, source, filename=None):
    from modules.tenancy import api as tenancy

    contract = tenancy.active_tenancy_for_account(tenant.user_id,
                                                  timezone.localdate())
    if contract is None:
        raise NoUnpaidStatementError("Нет неоплаченных начислений.")
    submitted = payments.submit_receipt(
        tenancy_id=contract.tenancy_id, property_id=contract.property_id,
        file=file, source=source, filename=filename)
    return Payment.objects.get(pk=submitted["payment_id"])


def earliest_unpaid_statement(contract):
    row = payments.earliest_unpaid_invoice(contract.tenancy_id,
                                           contract.property_id)
    if row is None:
        return None
    return MonthlyStatement.objects.get(pk=row["invoice_id"])


def confirm_payment(payment, amount):
    payments.confirm_payment(payment.pk, amount)


def record_payment(statement, amount, note=""):
    payment_id = payments.record_payment(statement.pk, amount, note=note)
    return Payment.objects.get(pk=payment_id)


def reject_payment(payment, note=""):
    payments.reject_payment(payment.pk, note)


def void_payment(payment, reason):
    payments.void_payment(payment.pk, reason)
