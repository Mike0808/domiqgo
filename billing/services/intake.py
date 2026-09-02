from django.db import transaction
from ..models import MonthlyStatement, Payment

class NoUnpaidStatementError(Exception):
    """No statement with status 'unpaid' to attach a receipt to."""

class PositiveAmountRequired(Exception):
    """Подтверждение требует суммы, и она строго положительна (инв. 2
    спецификации Payments)."""

def _checked(amount):
    if amount is None or amount <= 0:
        raise PositiveAmountRequired(
            f"Сумма платежа обязана быть больше нуля, получено: {amount}.")
    return amount

def earliest_unpaid_statement(contract):
    """Самый ранний непогашенный счёт договора (правило — ADR-0014).

    Счета без договора (наследие миграции E2) учитываются по квартире
    договора: они ничьи, пока владелец не разберёт их вручную, но платёж
    жильца этой квартиры чаще всего про них. Уйдёт вместе с legacy-`billing/`.
    """
    from django.db.models import Q

    return (MonthlyStatement.objects
            .filter(Q(tenancy_id=contract.tenancy_id)
                    | Q(apartment_id=contract.property_id, tenancy_id=None),
                    status=MonthlyStatement.UNPAID)
            .order_by("period").first())

@transaction.atomic
def attach_receipt(tenant, file, source, filename=None):
    from django.utils import timezone

    from modules.tenancy import api as tenancy

    contract = tenancy.active_tenancy_for_account(tenant.user_id,
                                                  timezone.localdate())
    stmt = earliest_unpaid_statement(contract) if contract else None
    if stmt is None:
        raise NoUnpaidStatementError("Нет неоплаченных начислений.")
    payment = Payment(statement=stmt, source=source)
    payment.file.save(filename or getattr(file, "name", "receipt"), file, save=False)
    payment.save()
    stmt.status = MonthlyStatement.PENDING
    stmt.save(update_fields=["status"])
    return payment

@transaction.atomic
def confirm_payment(payment, amount):
    """Признать заявленный платёж и указать сумму (шаг E1).

    Сумма появляется у платежа только здесь: заявленный чек — ещё не деньги.
    Статус счёта пока проставляется по-старому — его судьба решается на E3.
    """
    payment.amount = _checked(amount)
    payment.status = Payment.CONFIRMED
    payment.save(update_fields=["status", "amount"])
    stmt = payment.statement
    stmt.status = MonthlyStatement.PAID
    stmt.save(update_fields=["status"])


@transaction.atomic
def record_payment(statement, amount, note=""):
    """Отметить полученный платёж вручную, без чека (шаг E1).

    Роадмап относит ручную отметку к P1, но команды до сих пор не было:
    владелец, получивший наличные, был вынужден просить чек ради
    формальности. Платёж рождается сразу подтверждённым — владелец
    и есть подтверждающий.
    """
    payment = Payment.objects.create(
        statement=statement, source=Payment.MANUAL, status=Payment.CONFIRMED,
        amount=_checked(amount), note=note)
    statement.status = MonthlyStatement.PAID
    statement.save(update_fields=["status"])
    return payment

def _revert_if_no_pending(stmt):
    """Drop a statement back to UNPAID once no PENDING payment remains,
    unless it's already PAID — a landlord-confirmed payment must never be
    silently undone by rejecting/deleting an unrelated stray receipt."""
    if (stmt.status != MonthlyStatement.PAID
            and not stmt.payments.filter(status=Payment.PENDING).exists()):
        stmt.status = MonthlyStatement.UNPAID
        stmt.save(update_fields=["status"])

@transaction.atomic
def reject_payment(payment, note=""):
    payment.status = Payment.REJECTED
    fields = ["status"]
    if note:
        payment.note = note
        fields.append("note")
    payment.save(update_fields=fields)
    _revert_if_no_pending(payment.statement)
