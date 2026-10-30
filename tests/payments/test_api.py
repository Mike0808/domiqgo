"""API модуля Payments: команды платёжного потока в модуле (шаг H2).

Интерфейсный путь (бот, админка, оболочка `intake.py`) проверяют тесты
легаси; здесь — граница модуля: идентификаторы вместо моделей, правило
выбора счёта (ADR-0014) и отказы домена.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.files.base import ContentFile

from billing.models import Apartment, MonthlyStatement
from billing.tests.settle import issue, pend, settle
from billing.tests.tenancies import let_in
from modules.billing import api as billing
from modules.payments import api
from modules.payments.infrastructure.models import Payment

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def media_isolation(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def _contract():
    flat = Apartment.objects.create(label="кв")
    user = User.objects.create_user("t", password="x")
    contract_id = let_in(flat, account_id=user.pk)
    return flat, contract_id


def _issued(flat, contract_id, month, total="100"):
    return issue(MonthlyStatement.objects.create(
        apartment_id=flat.pk, period=date(2026, month, 1), total=Decimal(total),
        tenancy_id=contract_id))


def _receipt():
    return ContentFile(b"img", name="r.jpg")


def test_submit_targets_the_earliest_outstanding_invoice(media_isolation):
    flat, contract_id = _contract()
    june = _issued(flat, contract_id, 6)
    _issued(flat, contract_id, 7)

    submitted = api.submit_receipt(tenancy_id=contract_id,
                                   property_id=flat.pk,
                                   file=_receipt(), source="telegram")

    assert submitted["invoice_id"] == june.pk
    payment = Payment.objects.get(pk=submitted["payment_id"])
    assert payment.status == Payment.PENDING
    assert payment.statement_id == june.pk


def test_submit_skips_settled_and_claimed_invoices(media_isolation):
    flat, contract_id = _contract()
    settle(_issued(flat, contract_id, 5))
    pend(_issued(flat, contract_id, 6))
    free = _issued(flat, contract_id, 7)

    submitted = api.submit_receipt(tenancy_id=contract_id,
                                   property_id=flat.pk,
                                   file=_receipt(), source="web")

    assert submitted["invoice_id"] == free.pk


def test_submit_without_an_addressee_is_refused(media_isolation):
    """Без договора и объекта перечня непогашенных нет — иначе это был бы
    список чужих долгов."""
    flat, contract_id = _contract()
    _issued(flat, contract_id, 7)

    with pytest.raises(api.NoUnpaidStatementError):
        api.submit_receipt(tenancy_id=None, property_id=None,
                           file=_receipt(), source="web")


def test_record_payment_refuses_a_draft_and_a_stranger():
    """По черновику не платят (E4), по несуществующему счёту — тем более."""
    flat, contract_id = _contract()
    draft = MonthlyStatement.objects.create(
        apartment_id=flat.pk, period=date(2026, 7, 1), total=Decimal("100"),
        tenancy_id=contract_id)

    with pytest.raises(api.InvoiceNotIssued):
        api.record_payment(draft.pk, Decimal("100"))
    with pytest.raises(api.InvoiceNotIssued):
        api.record_payment(10 ** 6, Decimal("100"))
    assert not Payment.objects.exists()


def test_void_demands_a_confirmed_payment_and_a_reason(media_isolation):
    flat, contract_id = _contract()
    stmt = _issued(flat, contract_id, 7)
    payment_id = api.record_payment(stmt.pk, Decimal("100"))

    with pytest.raises(api.VoidReasonRequired):
        api.void_payment(payment_id, "  ")

    pending = pend(stmt)
    with pytest.raises(api.OnlyConfirmedIsVoided):
        api.void_payment(pending.pk, "ошибка")

    api.void_payment(payment_id, "перевод вернулся")
    voided = Payment.objects.get(pk=payment_id)
    assert voided.status == Payment.VOIDED
    assert "отменён: перевод вернулся" in voided.note


def test_outstanding_invoices_come_from_the_billing_read_contract(media_isolation):
    """`ListOutstandingInvoices` (ADR-0014): выставленные и непогашенные,
    по периоду; без адресата — пусто."""
    flat, contract_id = _contract()
    july = _issued(flat, contract_id, 7)
    _issued(flat, contract_id, 6)
    settle(_issued(flat, contract_id, 5))
    MonthlyStatement.objects.create(   # черновик не предъявлен — не в счёт
        apartment_id=flat.pk, period=date(2026, 8, 1), total=Decimal("1"),
        tenancy_id=contract_id)

    rows = billing.list_outstanding_invoices(tenancy_id=contract_id,
                                             property_id=flat.pk)

    # SQLite отдаёт дату сырого запроса строкой — сравниваем текстом.
    assert [str(row["period"])[:7] for row in rows] == ["2026-06", "2026-07"]
    assert rows[1]["invoice_id"] == july.pk
    assert billing.list_outstanding_invoices() == []
