from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import Client
import pytest
from billing.models import Apartment, Tenant, MonthlyStatement, Payment
from billing.services.intake import attach_receipt

pytestmark = pytest.mark.django_db

@pytest.fixture
def admin_client():
    User.objects.create_superuser("boss", "b@e.com", "pass12345")
    c = Client(); c.login(username="boss", password="pass12345")
    return c

@pytest.fixture
def media_isolation(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path

def _pending_payment():
    from billing.tests.tenancies import let_in

    a = Apartment.objects.create(label="кв")
    u = User.objects.create_user("t", password="x")
    let_in(a, account_id=u.pk)   # платёж ищет счёт договора (шаг E2)
    t = Tenant.objects.create(user=u, apartment=a)
    MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1),
                                    status="unpaid", total=Decimal("21500"))
    return attach_receipt(t, ContentFile(b"img", name="r.jpg"), source=Payment.TELEGRAM)

def test_payment_changelist_loads(admin_client, media_isolation):
    _pending_payment()
    assert admin_client.get("/admin/billing/payment/").status_code == 200

def test_confirm_action_marks_paid_with_the_invoice_total(admin_client, media_isolation):
    """Обычный случай «пришло ровно столько, сколько выставлено»: сумма
    преднастроена итогом счёта — один клик (шаг E1)."""
    p = _pending_payment()
    admin_client.post("/admin/billing/payment/", {
        "action": "confirm_payments", "_selected_action": [str(p.pk)]})
    p.refresh_from_db(); p.statement.refresh_from_db()
    assert p.status == Payment.CONFIRMED
    assert p.amount == Decimal("21500")
    assert p.statement.status == MonthlyStatement.PAID


def test_recording_a_manual_payment_from_the_admin(admin_client, media_isolation):
    """Ручная отметка (шаг E1): счёт, сумма, примечание — без чека."""
    a = Apartment.objects.create(label="кв")
    stmt = MonthlyStatement.objects.create(apartment=a, period=date(2026, 7, 1),
                                           status="unpaid", total=Decimal("21500"))
    resp = admin_client.post("/admin/billing/payment/add/", {
        "statement": str(stmt.pk), "amount": "21500", "note": "наличными"})
    assert resp.status_code == 302
    stmt.refresh_from_db()
    payment = Payment.objects.get()
    assert payment.status == Payment.CONFIRMED and payment.source == Payment.MANUAL
    assert stmt.status == MonthlyStatement.PAID

def test_reject_action_reverts_to_unpaid(admin_client, media_isolation):
    p = _pending_payment()
    admin_client.post("/admin/billing/payment/", {
        "action": "reject_payments", "_selected_action": [str(p.pk)]})
    p.refresh_from_db(); p.statement.refresh_from_db()
    assert p.status == Payment.REJECTED
    assert p.statement.status == MonthlyStatement.UNPAID

def test_delete_payment_removes_file_and_reverts_status(admin_client, media_isolation):
    import os
    p = _pending_payment()
    path = p.file.path
    assert os.path.exists(path)
    p.statement.refresh_from_db()
    assert p.statement.status == MonthlyStatement.PENDING
    # Django admin's single-object delete confirmation calls delete_model().
    admin_client.post(f"/admin/billing/payment/{p.pk}/delete/", {"post": "yes"})
    assert not Payment.objects.filter(pk=p.pk).exists()
    assert not os.path.exists(path)
    assert MonthlyStatement.objects.get().status == MonthlyStatement.UNPAID

def test_delete_stray_pending_on_paid_statement_keeps_it_paid(admin_client, media_isolation):
    p = _pending_payment()
    stmt = p.statement
    stmt.status = MonthlyStatement.PAID
    stmt.save(update_fields=["status"])
    admin_client.post(f"/admin/billing/payment/{p.pk}/delete/", {"post": "yes"})
    assert not Payment.objects.filter(pk=p.pk).exists()
    stmt.refresh_from_db()
    assert stmt.status == MonthlyStatement.PAID
