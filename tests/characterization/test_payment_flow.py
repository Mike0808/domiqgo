"""Платёжный поток: пункты №15 и №16 гап-анализа.

| Пункт | Что зафиксировано                                    | Кто перепишет |
|-------|------------------------------------------------------|---------------|
| №15   | платёж пишет статус в счёт; статус — хранимое поле    | E3            |
| №16   | удаление платежа стирает и запись, и файл             | E5            |

Пересечение с `billing/tests/test_intake.py` и `test_payment_admin.py`
намеренное: там это проверка правильности сегодняшнего поведения, здесь —
пометка «поведение изменится, и вот как именно».
"""

import os
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import Client

from billing.models import Apartment, MonthlyStatement, Payment, Tenant
from billing.services.intake import attach_receipt, confirm_payment, reject_payment

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.characterization]


def _tenant_with_unpaid_invoice():
    from billing.tests.tenancies import let_in

    apartment = Apartment.objects.create(label="кв")
    user = User.objects.create_user("ivanov", password="pass12345")
    let_in(apartment, account_id=user.pk)   # платёж ищет счёт договора (E2)
    tenant = Tenant.objects.create(user=user, apartment=apartment)
    from billing.tests.settle import issue
    invoice = issue(MonthlyStatement.objects.create(
        apartment=apartment, period=date(2026, 7, 1), total=Decimal("1000.00")))
    return tenant, invoice


def _landlord_client():
    User.objects.create_superuser("boss", "boss@example.com", "pass12345")
    client = Client()
    assert client.login(username="boss", password="pass12345")
    return client


# --------------------------------------------------------------------------
# №15 — платёжный поток правит чужой агрегат. Переписывает шаг E3.
# --------------------------------------------------------------------------

def test_every_payment_step_writes_the_invoice_status(media_isolation):
    """№15 исправлен (E3): платёжный поток не пишет в счёт ни строчки.

    Статус вычисляется Billing'ом из проекции признанных оплат (ADR-0015);
    те же переходы видны снаружи, но за ними — сверка, а не запись поля.
    `_revert_if_no_pending` исчезла вместе с колонкой, которую стерегла.
    """
    tenant, invoice = _tenant_with_unpaid_invoice()

    payment = attach_receipt(tenant, ContentFile(b"img", name="r.jpg"),
                             source=Payment.TELEGRAM)
    invoice.refresh_from_db()
    assert invoice.status == MonthlyStatement.PENDING   # чек приложен

    confirm_payment(payment, invoice.total or Decimal("100"))
    invoice.refresh_from_db()
    assert invoice.status == MonthlyStatement.PAID      # оплата подтверждена

    stray = Payment.objects.create(statement=invoice, source=Payment.WEB,
                                   status=Payment.PENDING)
    reject_payment(stray)
    invoice.refresh_from_db()
    assert invoice.status == MonthlyStatement.PAID      # откат не трогает подтверждённое


def test_invoice_status_is_a_stored_field_answerable_to_nothing():
    """№15 исправлен (E3): объявить счёт оплаченным без платежа больше нельзя.

    Колонки нет — статус вычисляется, и записать в него нечего; проекция
    сходится с журналом событий, `RebuildSettlement` её пересобирает.
    """
    _, invoice = _tenant_with_unpaid_invoice()

    with pytest.raises(AttributeError):
        invoice.status = MonthlyStatement.PAID

    assert invoice.status == MonthlyStatement.UNPAID
    assert invoice.payments.count() == 0


# --------------------------------------------------------------------------
# №16 — удаление платежа. Переписывает шаг E5.
# --------------------------------------------------------------------------

def test_deleting_a_payment_erases_the_record_and_the_file(media_isolation):
    """Удаление в админке не оставляет следа ни в базе, ни на диске.

    После E5 вместо удаления — отмена: запись и файл остаются, причина
    фиксируется, история сверки не рвётся.
    """
    tenant, invoice = _tenant_with_unpaid_invoice()
    payment = attach_receipt(tenant, ContentFile(b"img", name="r.jpg"),
                             source=Payment.TELEGRAM)
    path = payment.file.path
    assert os.path.exists(path)

    _landlord_client().post(f"/admin/billing/payment/{payment.pk}/delete/", {"post": "yes"})

    assert not Payment.objects.exists()
    assert not os.path.exists(path)
    invoice.refresh_from_db()
    assert invoice.status == MonthlyStatement.UNPAID   # и статус счёта отыгран назад
