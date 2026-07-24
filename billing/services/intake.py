from django.db import transaction
from ..models import MonthlyStatement, Payment

class NoUnpaidStatementError(Exception):
    """No statement with status 'unpaid' to attach a receipt to."""

def earliest_unpaid_statement(apartment):
    return (MonthlyStatement.objects
            .filter(apartment=apartment, status=MonthlyStatement.UNPAID)
            .order_by("period").first())

@transaction.atomic
def attach_receipt(tenant, file, source, filename=None):
    stmt = earliest_unpaid_statement(tenant.apartment)
    if stmt is None:
        raise NoUnpaidStatementError("Нет неоплаченных начислений.")
    payment = Payment(statement=stmt, source=source)
    payment.file.save(filename or getattr(file, "name", "receipt"), file, save=False)
    payment.save()
    stmt.status = MonthlyStatement.PENDING
    stmt.save(update_fields=["status"])
    return payment

@transaction.atomic
def confirm_payment(payment):
    payment.status = Payment.CONFIRMED
    payment.save(update_fields=["status"])
    stmt = payment.statement
    stmt.status = MonthlyStatement.PAID
    stmt.save(update_fields=["status"])

@transaction.atomic
def reject_payment(payment, note=""):
    payment.status = Payment.REJECTED
    fields = ["status"]
    if note:
        payment.note = note
        fields.append("note")
    payment.save(update_fields=fields)
    stmt = payment.statement
    if not stmt.payments.filter(status=Payment.PENDING).exists():
        stmt.status = MonthlyStatement.UNPAID
        stmt.save(update_fields=["status"])
