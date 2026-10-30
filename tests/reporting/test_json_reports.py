"""JSON-пара: «Полная выгрузка» и «Мои данные» (шаг G2)."""

import json
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import Client

from billing.models import Apartment, Document, MonthlyStatement, Tenant
from billing.services.intake import record_payment
from billing.tests.settle import issue
from billing.tests.tenancies import let_in
from modules.identity import api as identity
from modules.notifications import api as notifications
from modules.properties import api as properties
from modules.reporting import api
from modules.reporting.infrastructure.models import ExportRun

pytestmark = pytest.mark.django_db(transaction=True)

BOSS = 1


def _home(username="ivanov", label="кв. на Ленина"):
    flat_id = properties.register_property(label, has_hot_water=False)
    flat = Apartment.objects.get(pk=flat_id)
    user = User.objects.create_user(username, password="pass12345")
    contract_id = let_in(flat, account_id=user.pk, full_name="Иванов",
                         rent="30000")
    tenant = Tenant.objects.create(user=user, apartment_id=flat.pk)
    return flat, user, contract_id, tenant


def _payload(raw) -> dict:
    return json.loads(raw.decode("utf-8"))


def test_the_full_dump_carries_every_section():
    flat, user, contract_id, tenant = _home()
    stmt = issue(MonthlyStatement.objects.create(
        apartment_id=flat.pk, period=date(2026, 7, 1), total=Decimal("100"),
        tenancy_id=contract_id, lines=[]))
    record_payment(stmt, Decimal("100"))
    Document.objects.create(tenant=tenant,
                            file=ContentFile(b"x", name="dogovor.pdf"),
                            title="Договор аренды")

    filename, raw = api.run_export("full", initiated_by=BOSS)

    data = _payload(raw)
    assert filename.endswith(".json")
    assert data["properties"][0]["label"] == "кв. на Ленина"
    assert data["tenancies"][0]["full_name"] == "Иванов"
    assert float(data["invoices"][0]["total"]) == 100
    assert data["payments"][0]["status"] == "confirmed"
    assert data["documents"][0]["title"] == "Договор аренды"   # только метаданные
    assert "file" not in data["documents"][0]                  # ADR-0022


def test_my_data_holds_only_the_asked_account():
    flat, user, contract_id, _ = _home()
    other_flat, other_user, other_contract, _ = _home("petrov", "чужая кв")
    issue(MonthlyStatement.objects.create(
        apartment_id=flat.pk, period=date(2026, 7, 1), total=Decimal("1"),
        tenancy_id=contract_id, lines=[]))
    issue(MonthlyStatement.objects.create(
        apartment_id=other_flat.pk, period=date(2026, 7, 1), total=Decimal("2"),
        tenancy_id=other_contract, lines=[]))
    identity.grant_privacy_consent(user.pk, "2026-07-27",
                                   __import__("django.utils.timezone",
                                              fromlist=["now"]).now())
    notifications.bind_channel(user.pk, "telegram", "555")

    _, raw = api.run_export("my_data", initiated_by=user.pk,
                            scope=f"учётная запись #{user.pk}",
                            params={"account_id": user.pk})

    data = _payload(raw)
    assert data["account_id"] == user.pk
    assert [t["full_name"] for t in data["tenancies"]] == ["Иванов"]
    assert [float(i["total"]) for i in data["invoices"]] == [1]   # чужого нет
    assert data["consents"][0]["policy_version"] == "2026-07-27"
    assert data["channels"] == [{"platform": "telegram", "address": "555"}]


def test_my_data_without_an_account_violates_the_scope_before_the_journal():
    with pytest.raises(api.ScopeViolation):
        api.run_export("my_data", initiated_by=BOSS)
    assert not ExportRun.objects.exists()   # инв. 3 — до записи в журнал


def test_the_tenant_downloads_their_data_from_the_cabinet():
    flat, user, contract_id, _ = _home()
    client = Client()
    assert client.login(username="ivanov", password="pass12345")

    response = client.get("/my-data.json")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    data = _payload(response.content)
    assert data["account_id"] == user.pk
    (run,) = ExportRun.objects.all()
    assert run.initiated_by == user.pk       # инициатор — из сессии (ADR-0023)
    assert run.report_code == "my_data"


def test_the_owner_downloads_the_full_dump_from_the_admin():
    _home()
    User.objects.create_superuser("boss2", "b@e.com", "pass12345")
    client = Client()
    client.login(username="boss2", password="pass12345")

    response = client.get("/admin/reporting/exportrun/?run=full")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    assert _payload(response.content)["properties"]
