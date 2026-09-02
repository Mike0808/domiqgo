"""Жизненный цикл счёта: пункты №6, 21 и 35 гап-анализа.

| Пункт | Что зафиксировано                                  | Кто перепишет |
|-------|----------------------------------------------------|---------------|
| №6    | счёт привязан к квартире, ключ `(квартира, период)` | E2            |
| №21   | блокировка ввода показаний следует за оплатой       | E4            |
| №35   | счёт возникает сам, из трёх мест, и переписывается  | E4            |
"""

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import Client
from django.utils import timezone

from modules.metering.infrastructure.models import Meter, MeterReading
from billing.tests.tenancies import draft, let_in
from billing.models import Apartment, MonthlyStatement, Tenant
from billing.services.statements import generate_statement
from modules.tariffs.api import publish_tariff_version

pytestmark = [pytest.mark.django_db, pytest.mark.characterization]

REPO_ROOT = Path(__file__).resolve().parents[2]


def _tariffs():
    for code, rate in (("cold_water", "48.15"), ("electricity_single", "4.87")):
        publish_tariff_version(utility=code, rate=Decimal(rate),
                              effective_from=date(2020, 1, 1))


def _apartment(label="кв"):
    """Квартира с ХВС и электричеством; базы отсчёта — из акта."""
    a = Apartment.objects.create(label=label, has_hot_water=False, has_sewage=False)
    Meter.objects.create(apartment_id=a.pk, resource="cold_water", initial_value=Decimal("100"))
    Meter.objects.create(apartment_id=a.pk, resource="electricity_single", initial_value=Decimal("1400"))
    let_in(a)   # счёт выставляется договору периода (D1b)
    return a


def _tenant(apartment, username):
    user = User.objects.create_user(username, password="pass12345")
    draft(apartment, user.pk)   # кабинет открывается по договору (D1d)
    return Tenant.objects.create(user=user, apartment=apartment), user


def _login(user):
    client = Client()
    assert client.login(username=user.username, password="pass12345")
    return client


def _current_period():
    return timezone.localdate().replace(day=1)


# --------------------------------------------------------------------------
# №6 — счёт принадлежит договору. Исправлен шагом E2 (ADR-0024).
# --------------------------------------------------------------------------

def test_a_new_tenant_does_not_see_invoices_of_the_previous_one():
    """Счёт принадлежит договору: жилец видит только свой период
    проживания, счета прежнего не переезжают вместе со стенами."""
    from modules.tenancy import api as tenancy_api

    apartment = _apartment()
    previous, prev_user = _tenant(apartment, "old")
    prev_contract = tenancy_api.active_tenancy_for_account(
        prev_user.pk, date(2026, 5, 1))
    MonthlyStatement.objects.create(
        apartment=apartment, period=date(2026, 5, 1), total=Decimal("1234.00"),
        tenancy_id=prev_contract.tenancy_id)
    previous.delete()  # прежний жилец съехал; его счета — история его договора

    _, user = _tenant(apartment, "new")
    response = _login(user).get("/history/")

    assert list(response.context["statements"]) == []


def test_two_tenancies_in_one_month_may_both_be_invoiced():
    """Ключ счёта — (договор, период): смена жильца в середине месяца
    выразима, оба счёта живут рядом (ADR-0024). За один договор и период
    счёт по-прежнему один."""
    apartment = _apartment()
    first = MonthlyStatement.objects.create(
        apartment=apartment, period=date(2026, 5, 1), tenancy_id=101)
    MonthlyStatement.objects.create(
        apartment=apartment, period=date(2026, 5, 1), tenancy_id=102)

    assert MonthlyStatement.objects.filter(period=date(2026, 5, 1)).count() == 2
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            MonthlyStatement.objects.create(
                apartment=apartment, period=first.period, tenancy_id=101)


# --------------------------------------------------------------------------
# №21 — блокировку ввода держит выставление счёта. Исправлен шагом E4.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "issued, locked",
    [
        (False, False),   # черновик: показания правятся, даже оплаченный
        (True, True),     # выставлен — форма закрыта (дефект №21 исправлен)
    ],
)
def test_reading_lock_follows_issuing(issued, locked):
    """№21 исправлен (E4): форму закрывает выставление счёта, а не платёж.

    Предъявленный счёт неизменяем — и показания под ним тоже; оплата сама по
    себе форму больше не трогает.
    """
    apartment = _apartment()
    _tariffs()
    _, user = _tenant(apartment, "ivanov")
    period = _current_period()
    from billing.tests.settle import issue, settle
    from modules.tenancy import api as tenancy_api
    stmt = MonthlyStatement.objects.create(
        apartment=apartment, period=period, total=Decimal("500.00"),
        tenancy_id=tenancy_api.tenancy_for(apartment.pk, period).tenancy_id)
    settle(stmt)                     # оплачен в обоих случаях
    if issued:
        issue(stmt)
    client = _login(user)

    assert client.get("/").context["locked"] is locked

    client.post("/", {"cold_water": "110", "electricity_single": "1500"})
    applied = MeterReading.objects.filter(apartment_id=apartment.pk, period=period).exists()
    assert applied is not locked


# --------------------------------------------------------------------------
# №35 — расчёт даёт черновик, предъявляет владелец. Исправлен шагом E4.
# --------------------------------------------------------------------------

def test_readings_make_a_draft_and_only_the_owner_issues_it():
    """№35 исправлен (E4): жилец вводит показания и видит сумму — это
    черновик; счётом он становится действием владельца, с моментом
    предъявления и сроком оплаты."""
    apartment = _apartment()
    _tariffs()
    _, user = _tenant(apartment, "ivanov")
    period = _current_period()

    _login(user).post("/", {"cold_water": "110", "electricity_single": "1500"})

    draft = MonthlyStatement.objects.get(apartment=apartment, period=period)
    assert draft.total == Decimal("968.50")   # сумма видна сразу — сценарий цел
    assert not draft.is_issued                # но никто ничего не предъявлял

    from billing.services.issuing import issue_invoice
    issue_invoice(draft)
    draft.refresh_from_db()
    assert draft.is_issued and draft.due_date is not None


def test_invoice_has_a_moment_of_issuance_and_a_due_date():
    """№35 исправлен (E4): у счёта есть момент предъявления и срок оплаты.

    Отсюда всё остальное: есть что уведомлять, от чего отсчитывать просрочку
    и что делать неизменяемым (ADR-0013).
    """
    fields = {f.name for f in MonthlyStatement._meta.get_fields()}
    assert "issued_at" in fields
    assert "due_date" in fields


def test_a_draft_is_rewritten_but_an_issued_invoice_is_not():
    """Черновик пересчитывается на месте — это и есть сценарий «увидел
    сумму»; выставленный счёт неизменяем (E4): пересчёт отказывает, ревизии
    придут со своим шагом."""
    apartment = _apartment()
    _tariffs()
    period = date(2026, 7, 1)
    MeterReading.objects.create(apartment_id=apartment.pk, period=period,
                                resource="cold_water", value=Decimal("110"))
    MeterReading.objects.create(apartment_id=apartment.pk, period=period,
                                resource="electricity_single", value=Decimal("1500"))

    first = generate_statement(apartment, period)
    assert first.total == Decimal("968.50")

    MeterReading.objects.filter(apartment_id=apartment.pk, resource="cold_water").update(
        value=Decimal("120"))
    second = generate_statement(apartment, period)

    assert second.pk == first.pk                 # черновик — тот же счёт
    assert second.total == Decimal("1450.00")    # (120-100)*48.15 + 487.00

    from billing.services.issuing import InvoiceAlreadyIssued, issue_invoice
    issue_invoice(second)
    with pytest.raises(InvoiceAlreadyIssued):
        generate_statement(apartment, period)


def test_statement_generation_is_triggered_from_three_places():
    """Расчёт вызывается из трёх мест: портала и двух точек админки.

    Проверка структурная, потому что фиксируется именно рассеянность вызова:
    после E4 остаётся одна команда выставления, и здесь останется один вызов.
    """
    sites = []
    for path in (REPO_ROOT / "billing").rglob("*.py"):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "generate_statement":
                sites.append(f"{path.name}:{node.lineno}")

    assert len(sites) == 3, f"вызовы generate_statement: {sorted(sites)}"
    assert sorted(s.split(":")[0] for s in sites) == ["admin.py", "admin.py", "views.py"]
