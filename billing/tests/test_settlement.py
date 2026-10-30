"""Проекция признанных оплат: путь событий, пересборка, сходимость (E3)."""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from billing.models import Apartment, MonthlyStatement, Settlement, Tenant
from billing.services.intake import record_payment
from billing.services.settlement import (
    rebuild_settlement, settlement_matches_journal,
)
from billing.tests.tenancies import let_in

pytestmark = pytest.mark.django_db(transaction=True)


def _statement(total="21500"):
    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user("t", password="x")
    let_in(a, account_id=u.pk)
    Tenant.objects.create(user=u, apartment_id=a.pk)
    from billing.tests.settle import issue
    return issue(MonthlyStatement.objects.create(
        apartment_id=a.pk, period=date(2026, 7, 1), total=Decimal(total)))


def test_a_confirmed_payment_reaches_the_projection_by_event():
    stmt = _statement()

    record_payment(stmt, Decimal("21500"))

    assert stmt.settled_total == Decimal("21500")
    assert stmt.status == MonthlyStatement.PAID
    assert settlement_matches_journal(stmt.pk)


def test_a_partial_payment_does_not_close_the_invoice():
    """Погашен — значит признано не меньше итога: частичная оплата видна,
    но счёт остаётся неоплаченным (Q3 карты: «хватило ли»)."""
    stmt = _statement()

    record_payment(stmt, Decimal("10000"))

    assert stmt.settled_total == Decimal("10000")
    assert stmt.status == MonthlyStatement.UNPAID

    record_payment(stmt, Decimal("11500"))
    assert stmt.status == MonthlyStatement.PAID


def test_rebuild_restores_a_tampered_projection_from_the_journal():
    """ADR-0015: проекция обязана быть перестраиваемой из журнала шины."""
    stmt = _statement()
    record_payment(stmt, Decimal("21500"))

    Settlement.objects.filter(statement_id=stmt.pk).update(
        confirmed_total=Decimal("1"))
    assert not settlement_matches_journal(stmt.pk)

    assert rebuild_settlement(stmt.pk) == Decimal("21500")
    assert settlement_matches_journal(stmt.pk)
    assert stmt.status == MonthlyStatement.PAID


def test_a_voided_payment_leaves_the_projection_and_the_journal_agrees():
    """PaymentVoided изымает сумму; журнал хранит обе записи (E5)."""
    from billing.models import Payment
    from billing.services.intake import void_payment

    stmt = _statement()
    record_payment(stmt, Decimal("21500"))
    assert stmt.status == MonthlyStatement.PAID

    void_payment(Payment.objects.get(), "ошибка")

    assert stmt.settled_total == Decimal("0")
    assert stmt.status == MonthlyStatement.UNPAID
    assert settlement_matches_journal(stmt.pk)
