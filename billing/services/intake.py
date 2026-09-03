"""Платёжный поток: чек, подтверждение, отклонение, ручная отметка.

С шага E3 поток не пишет в счёт ни строчки (дефект №15): статус счёта —
результат сверки в Billing, а сюда входит только платёж. Каждый переход
публикует событие; события — контракты `modules/payments/events`, и публикация
переедет в модуль при расформировании `billing/`.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from bus import publish
from modules.payments.events import (
    PaymentConfirmed, PaymentRejected, PaymentSubmitted, PaymentVoided,
)

from ..models import MonthlyStatement, Payment, Settlement


class NoUnpaidStatementError(Exception):
    """Нет непогашенного счёта, к которому можно отнести платёж."""


class InvoiceNotIssued(Exception):
    """Платёж относится к выставленному счёту: черновик — ещё не документ,
    по нему не платят (шаг E4)."""


class OnlyConfirmedIsVoided(Exception):
    """Отменить можно только подтверждённый платёж (инв. 4): у заявленного
    и отклонённого нет суммы в сверке — изымать нечего, их отклоняют."""


class VoidReasonRequired(Exception):
    """Отмена признанного платежа без причины — это удаление под другим
    именем: причина обязательна (спецификация Payments)."""


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

    Непогашенный — по сверке, а не по полю; счёт с заявленным платежом
    пропускается: чек уже ждёт решения владельца, второй туда не кладут.
    Счета без договора (наследие миграции E2) учитываются по квартире
    договора и уйдут вместе с legacy-`billing/`.
    """
    candidates = (MonthlyStatement.objects
                  .filter(Q(tenancy_id=contract.tenancy_id)
                          | Q(apartment_id=contract.property_id, tenancy_id=None))
                  .exclude(issued_at=None)   # платят по выставленным (E4)
                  .order_by("period"))
    return next((s for s in candidates if s.status == MonthlyStatement.UNPAID),
                None)


@transaction.atomic
def attach_receipt(tenant, file, source, filename=None):
    from modules.tenancy import api as tenancy

    contract = tenancy.active_tenancy_for_account(tenant.user_id,
                                                  timezone.localdate())
    stmt = earliest_unpaid_statement(contract) if contract else None
    if stmt is None:
        raise NoUnpaidStatementError("Нет неоплаченных начислений.")
    payment = Payment(statement=stmt, source=source)
    payment.file.save(filename or getattr(file, "name", "receipt"), file, save=False)
    payment.save()
    publish(PaymentSubmitted(payment_id=payment.pk, statement_id=stmt.pk,
                             source=source, at=timezone.now()))
    return payment


@transaction.atomic
def confirm_payment(payment, amount):
    """Признать заявленный платёж и указать сумму (шаг E1).

    Счёт не трогается: погашение выведет сверка, услышав событие (E3).
    """
    payment.amount = _checked(amount)
    payment.status = Payment.CONFIRMED
    payment.save(update_fields=["status", "amount"])
    publish(PaymentConfirmed(payment_id=payment.pk,
                             statement_id=payment.statement_id,
                             amount=payment.amount, at=timezone.now()))


@transaction.atomic
def record_payment(statement, amount, note=""):
    """Отметить полученный платёж вручную, без чека (шаг E1).

    Платёж рождается сразу подтверждённым — владелец и есть подтверждающий.
    """
    if not statement.is_issued:
        raise InvoiceNotIssued(
            f"Счёт {statement} не выставлен — сначала предъявите его.")
    payment = Payment.objects.create(
        statement=statement, source=Payment.MANUAL, status=Payment.CONFIRMED,
        amount=_checked(amount), note=note)
    publish(PaymentConfirmed(payment_id=payment.pk, statement_id=statement.pk,
                             amount=payment.amount, at=timezone.now()))
    return payment


@transaction.atomic
def reject_payment(payment, note=""):
    """Отклонить заявленный платёж.

    Сумма отклонённого в сверке никогда не участвовала — Billing событие не
    слушает, счёт возвращается к «не оплачено» сам, силой вычисления.
    Прежняя защита `_revert_if_no_pending` исчезла вместе с полем, которое
    она стерегла.
    """
    payment.status = Payment.REJECTED
    fields = ["status"]
    if note:
        payment.note = note
        fields.append("note")
    payment.save(update_fields=fields)
    publish(PaymentRejected(payment_id=payment.pk,
                            statement_id=payment.statement_id,
                            reason=note, at=timezone.now()))


@transaction.atomic
def void_payment(payment, reason):
    """Отменить ранее подтверждённый платёж (шаг E5, дефект №16).

    Платёж — свершившийся факт: его не удаляют. Запись и чек остаются,
    причина фиксируется в примечании, сумма изымается из сверки событием —
    жилец, заплативший наличными без чека, не останется без следа платежа
    при споре «а я платил».
    """
    if payment.status != Payment.CONFIRMED:
        raise OnlyConfirmedIsVoided(
            f"Платёж в состоянии «{payment.get_status_display()}» не "
            "отменяется — отклоните его.")
    if not (reason or "").strip():
        raise VoidReasonRequired("Укажите причину отмены.")
    payment.status = Payment.VOIDED
    payment.note = (f"{payment.note}; отменён: {reason}" if payment.note
                    else f"отменён: {reason}")
    payment.save(update_fields=["status", "note"])
    publish(PaymentVoided(
        payment_id=payment.pk, statement_id=payment.statement_id,
        amount=payment.amount if payment.amount is not None else Decimal("0"),
        reason=reason, at=timezone.now()))
