from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
import pytest
from billing.models import Apartment, Tenant, MonthlyStatement, Payment
from billing.services.intake import (
    attach_receipt, confirm_payment, reject_payment,
    earliest_unpaid_statement, NoUnpaidStatementError,
)

pytestmark = pytest.mark.django_db

@pytest.fixture
def media_isolation(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path

def _tenant():
    from billing.tests.tenancies import let_in

    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user("t", password="x")
    let_in(a, account_id=u.pk)   # платёж ищет счёт договора (шаг E2)
    return Tenant.objects.create(user=u, apartment=a), a

def _receipt():
    return ContentFile(b"img", name="r.jpg")

def test_attach_targets_earliest_unpaid_and_sets_pending(media_isolation):
    tenant, a = _tenant()
    june = MonthlyStatement.objects.create(apartment=a, period=date(2026, 6, 1), status="unpaid")
    july = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="unpaid")
    payment = attach_receipt(tenant, _receipt(), source=Payment.TELEGRAM)
    assert payment.statement == june                 # earliest
    june.refresh_from_db(); july.refresh_from_db()
    assert june.status == MonthlyStatement.PENDING
    assert july.status == MonthlyStatement.UNPAID
    assert payment.status == Payment.PENDING
    assert payment.file.read() == b"img"

def test_attach_skips_pending_and_paid(media_isolation):
    tenant, a = _tenant()
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 5, 1), status="paid")
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 6, 1), status="pending")
    unpaid = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="unpaid")
    payment = attach_receipt(tenant, _receipt(), source=Payment.WEB)
    assert payment.statement == unpaid

def test_attach_raises_when_nothing_unpaid(media_isolation):
    tenant, a = _tenant()
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="paid")
    with pytest.raises(NoUnpaidStatementError):
        attach_receipt(tenant, _receipt(), source=Payment.TELEGRAM)

def test_confirm_sets_paid_and_records_the_amount(media_isolation):
    tenant, a = _tenant()
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="unpaid")
    payment = attach_receipt(tenant, _receipt(), source=Payment.TELEGRAM)
    confirm_payment(payment, Decimal("21500"))
    payment.refresh_from_db(); payment.statement.refresh_from_db()
    assert payment.status == Payment.CONFIRMED
    assert payment.amount == Decimal("21500")        # сумма есть только теперь
    assert payment.statement.status == MonthlyStatement.PAID


def test_confirming_without_a_positive_amount_is_refused(media_isolation):
    from billing.services.intake import PositiveAmountRequired
    tenant, a = _tenant()
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="unpaid")
    payment = attach_receipt(tenant, _receipt(), source=Payment.TELEGRAM)
    for bad in (None, Decimal("0"), Decimal("-1")):
        with pytest.raises(PositiveAmountRequired):
            confirm_payment(payment, bad)
    payment.refresh_from_db()
    assert payment.status == Payment.PENDING


def test_record_payment_marks_paid_without_a_receipt(media_isolation):
    """Шаг E1: владелец, получивший наличные, не просит чек ради
    формальности."""
    from billing.services.intake import record_payment
    tenant, a = _tenant()
    stmt = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1),
                                           status="unpaid")
    payment = record_payment(stmt, Decimal("21500"), note="наличными")
    stmt.refresh_from_db()
    assert payment.status == Payment.CONFIRMED and not payment.file
    assert payment.source == Payment.MANUAL
    assert payment.amount == Decimal("21500")
    assert stmt.status == MonthlyStatement.PAID

def test_reject_reverts_to_unpaid_when_no_other_pending(media_isolation):
    tenant, a = _tenant()
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="unpaid")
    payment = attach_receipt(tenant, _receipt(), source=Payment.TELEGRAM)
    reject_payment(payment, note="нечитаемый чек")
    payment.refresh_from_db(); payment.statement.refresh_from_db()
    assert payment.status == Payment.REJECTED
    assert payment.note == "нечитаемый чек"
    assert payment.statement.status == MonthlyStatement.UNPAID

def test_reject_keeps_pending_when_another_pending_exists(media_isolation):
    tenant, a = _tenant()
    stmt = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="unpaid")
    p1 = attach_receipt(tenant, _receipt(), source=Payment.TELEGRAM)
    # a second pending payment on the same statement
    p2 = Payment.objects.create(statement=stmt, source=Payment.WEB, status=Payment.PENDING)
    reject_payment(p1)
    stmt.refresh_from_db()
    assert stmt.status == MonthlyStatement.PENDING

def test_reject_stray_pending_on_paid_statement_keeps_it_paid(media_isolation):
    tenant, a = _tenant()
    stmt = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1), status="paid")
    # a stray pending payment attached after the statement was already confirmed paid
    stray = Payment.objects.create(statement=stmt, source=Payment.WEB, status=Payment.PENDING)
    reject_payment(stray)
    stray.refresh_from_db(); stmt.refresh_from_db()
    assert stray.status == Payment.REJECTED
    assert stmt.status == MonthlyStatement.PAID
