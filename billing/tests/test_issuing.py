"""Выставление счёта: срок, замок периода, событие, отказ черновикам (E4)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from billing.models import Apartment, BillingPolicy, MonthlyStatement
from billing.services.intake import InvoiceNotIssued, record_payment
from billing.services.issuing import (
    DraftWithoutTenancy, InvoiceAlreadyIssued, issue_invoice,
)
from billing.tests.tenancies import let_in
from modules.metering import api as metering

pytestmark = pytest.mark.django_db(transaction=True)


def _draft(tenancy_id=1, total="968.50"):
    a = Apartment.objects.create(label="кв")
    return MonthlyStatement.objects.create(
        apartment=a, period=date(2026, 7, 1), total=Decimal(total),
        tenancy_id=tenancy_id)


def test_issuing_fixes_the_due_date_and_locks_the_period():
    draft = _draft()

    issue_invoice(draft)

    draft.refresh_from_db()
    assert draft.is_issued
    assert draft.due_date == timezone.localdate() + timedelta(
        days=BillingPolicy.get().due_days)
    # Замок периода — в Metering (ADR-0012): показания месяца закрыты.
    assert not metering.is_period_open(draft.apartment_id, draft.period)


def test_issuing_tells_the_world():
    from bus.models import PublishedEvent

    draft = _draft()
    issue_invoice(draft)

    row = PublishedEvent.objects.get(
        event_type="modules.billing.events.InvoiceIssued")
    assert row.payload["invoice_id"] == draft.pk
    assert row.payload["total"] == "968.50"


def test_an_issued_invoice_is_not_issued_twice():
    draft = _draft()
    issue_invoice(draft)

    with pytest.raises(InvoiceAlreadyIssued):
        issue_invoice(draft)


def test_a_draft_without_a_tenancy_is_not_issued():
    """Инвариант 5 Billing: счёт без договора не предъявляется."""
    with pytest.raises(DraftWithoutTenancy):
        issue_invoice(_draft(tenancy_id=None))


def test_a_manual_payment_needs_an_issued_invoice():
    """Черновик — ещё не документ: по нему не платят (E4)."""
    draft = _draft()

    with pytest.raises(InvoiceNotIssued):
        record_payment(draft, Decimal("968.50"))


def test_the_changed_due_policy_does_not_touch_old_invoices():
    """ADR-0013: срок фиксируется в счёте значением в момент выставления."""
    first = _draft()
    issue_invoice(first)
    policy = BillingPolicy.get()
    policy.due_days = 3
    policy.save()

    first.refresh_from_db()
    assert first.due_date == timezone.localdate() + timedelta(days=10)
