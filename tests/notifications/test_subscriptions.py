"""Подписки и шаблоны: система впервые говорит первой (шаг F3)."""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.files.base import ContentFile

from billing.models import MonthlyStatement, Tenant
from billing.services.intake import (
    attach_receipt, confirm_payment, record_payment, reject_payment,
    void_payment,
)
from billing.services.issuing import issue_invoice
from billing.tests.settle import wire
from billing.tests.tenancies import let_in
from modules.notifications import api as notifications
from modules.properties import api as properties
from modules.tenancy import api as tenancy

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _wired():
    wire()


@pytest.fixture
def home(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    flat = properties.register_property("кв. на Ленина", has_hot_water=False)
    user = User.objects.create_user("ivanov", password="x")
    contract_id = let_in(flat_obj(flat), account_id=user.pk, full_name="Иванов",
                         rent="30000")
    notifications.bind_channel(user.pk, "telegram", "555")
    tenant = Tenant.objects.create(user=user, apartment=flat_obj(flat))
    return flat, user, contract_id, tenant


def flat_obj(flat_id):
    from billing.models import Apartment

    return Apartment.objects.get(pk=flat_id)


def _texts(account_id):
    return [m.text for m in notifications.list_messages(account_id)]


def _draft(flat, contract_id, total="21500"):
    return MonthlyStatement.objects.create(
        apartment=flat_obj(flat), period=date(2026, 7, 1),
        total=Decimal(total), tenancy_id=contract_id)


def test_issuing_an_invoice_tells_the_tenant(home):
    flat, user, contract_id, _ = home

    issue_invoice(_draft(flat, contract_id))

    (text,) = _texts(user.pk)
    assert "июль 2026" in text and "кв. на Ленина" in text
    assert "21500" in text and "Оплатите до" in text


def test_a_recorded_payment_thanks_and_announces_settlement(home):
    flat, user, contract_id, _ = home
    stmt = _draft(flat, contract_id)
    issue_invoice(stmt)

    record_payment(stmt, Decimal("21500"))

    texts = _texts(user.pk)
    assert any("принят" in t for t in texts)          # платёж принят
    assert any("погашен" in t for t in texts)         # счёт погашен


def test_a_partial_payment_thanks_but_does_not_announce_settlement(home):
    flat, user, contract_id, _ = home
    stmt = _draft(flat, contract_id)
    issue_invoice(stmt)

    record_payment(stmt, Decimal("100"))

    texts = _texts(user.pk)
    assert any("принят" in t for t in texts)
    assert not any("погашен" in t for t in texts)


def test_a_submitted_receipt_notifies_the_owner(home):
    flat, user, contract_id, tenant = home
    User.objects.create_superuser("boss", "b@e.com", "x")
    from modules.identity import api as identity

    (owner_id,) = identity.list_owner_accounts()
    notifications.bind_channel(owner_id, "telegram", "boss-chat")
    issue_invoice(_draft(flat, contract_id))

    attach_receipt(tenant, ContentFile(b"img", name="r.jpg"), source="telegram")

    (text,) = _texts(owner_id)
    assert "Пришёл чек" in text and "кв. на Ленина" in text and "Иванов" in text


def test_rejected_and_voided_payments_talk_to_the_tenant(home):
    flat, user, contract_id, tenant = home
    stmt = _draft(flat, contract_id)
    issue_invoice(stmt)
    payment = attach_receipt(tenant, ContentFile(b"img", name="r.jpg"),
                             source="telegram")

    reject_payment(payment, note="нечитаемый чек")
    confirmed = attach_receipt(tenant, ContentFile(b"img", name="r2.jpg"),
                               source="telegram")
    confirm_payment(confirmed, Decimal("21500"))
    void_payment(confirmed, "не тот счёт")

    texts = _texts(user.pk)
    assert any("не принят" in t and "нечитаемый чек" in t for t in texts)
    assert any("отменён" in t and "не тот счёт" in t for t in texts)


def test_an_ended_tenancy_says_goodbye(home):
    flat, user, contract_id, _ = home

    tenancy.end_tenancy(contract_id, date(2026, 8, 31))

    assert any("завершён" in t and "кв. на Ленина" in t for t in _texts(user.pk))


def test_a_tenant_without_channels_breaks_nothing(home):
    flat, user, contract_id, _ = home
    notifications.unbind_channel(user.pk, "telegram")

    issue_invoice(_draft(flat, contract_id))   # не падает

    assert _texts(user.pk) == []
