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
    return a


def _tenant(apartment, username):
    user = User.objects.create_user(username, password="pass12345")
    return Tenant.objects.create(user=user, apartment=apartment, full_name=username), user


def _login(user):
    client = Client()
    assert client.login(username=user.username, password="pass12345")
    return client


def _current_period():
    return timezone.localdate().replace(day=1)


# --------------------------------------------------------------------------
# №6 — счёт принадлежит квартире, а не договору. Переписывает шаг E2.
# --------------------------------------------------------------------------

def test_new_tenant_sees_invoices_of_the_previous_one():
    """Счёт привязан к квартире, поэтому переезжает вместе с ней.

    После E2 счёт принадлежит договору, и жилец видит только свой период
    проживания.
    """
    apartment = _apartment()
    previous, _ = _tenant(apartment, "old")
    old_invoice = MonthlyStatement.objects.create(
        apartment=apartment, period=date(2026, 5, 1), total=Decimal("1234.00"))
    previous.delete()  # прежний жилец съехал

    _, user = _tenant(apartment, "new")
    response = _login(user).get("/history/")

    assert list(response.context["statements"]) == [old_invoice]


def test_two_tenancies_in_one_month_cannot_both_be_invoiced():
    """Ключ `(квартира, период)` допускает ровно один счёт за месяц.

    Смена жильца в середине месяца сегодня невыразима: второй счёт за тот же
    период не создать. После E2 ключом становится договор, и оба счёта живут
    рядом (ADR-0024).
    """
    apartment = _apartment()
    MonthlyStatement.objects.create(apartment=apartment, period=date(2026, 5, 1))

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            MonthlyStatement.objects.create(apartment=apartment, period=date(2026, 5, 1))


# --------------------------------------------------------------------------
# №21 — блокировка ввода следует за оплатой. Переписывает шаг E4.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "status, locked",
    [
        (MonthlyStatement.UNPAID, False),   # счёт есть, но показания ещё правятся
        (MonthlyStatement.PENDING, True),   # появился чек — форма закрылась
        (MonthlyStatement.PAID, True),
    ],
)
def test_reading_lock_follows_payment_status(status, locked):
    """Форму закрывает не выставление счёта, а платёж по нему.

    Это и есть замыкание Metering ↔ Billing: сценарий ввода показаний читает
    статус оплаты. После E4 форму закрывает выставление счёта, а замок живёт
    в Metering (ADR-0012) — таблица ожиданий здесь меняется целиком.
    """
    apartment = _apartment()
    _tariffs()
    _, user = _tenant(apartment, "ivanov")
    period = _current_period()
    MonthlyStatement.objects.create(apartment=apartment, period=period,
                                    total=Decimal("500.00"), status=status)
    client = _login(user)

    assert client.get("/").context["locked"] is locked

    client.post("/", {"cold_water": "110", "electricity_single": "1500"})
    applied = MeterReading.objects.filter(apartment_id=apartment.pk, period=period).exists()
    assert applied is not locked


# --------------------------------------------------------------------------
# №35 — счёт возникает как побочный эффект. Переписывает шаг E4.
# --------------------------------------------------------------------------

def test_invoice_appears_without_anyone_issuing_it():
    """Жилец вводит показания — счёт возникает сам, действий владельца нет.

    После E4 расчёт даёт черновик, а предъявление становится отдельным
    действием владельца.
    """
    apartment = _apartment()
    _tariffs()
    _, user = _tenant(apartment, "ivanov")
    period = _current_period()
    assert not MonthlyStatement.objects.exists()

    _login(user).post("/", {"cold_water": "110", "electricity_single": "1500"})

    invoice = MonthlyStatement.objects.get(apartment=apartment, period=period)
    # (110-100)*48.15 + (1500-1400)*4.87 = 968.50 — ниже 10 000, без округления
    assert invoice.total == Decimal("968.50")


def test_invoice_has_no_moment_of_issuance():
    """Ни даты предъявления, ни срока оплаты у счёта нет.

    Отсюда следствия: нечего уведомлять, не от чего отсчитывать просрочку и
    нечего делать неизменяемым. Поля появляются на шаге E4 (ADR-0013).
    """
    fields = {f.name for f in MonthlyStatement._meta.get_fields()}
    assert "issued_at" not in fields
    assert "due_date" not in fields


def test_invoice_is_silently_rewritten_by_a_later_reading():
    """Правка показания переписывает уже существующий счёт на месте.

    После E4 предъявленный счёт неизменяем, а пересчёт даёт корректировку.
    """
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

    assert second.pk == first.pk                 # тот же счёт, не корректировка
    assert second.total == Decimal("1450.00")    # (120-100)*48.15 + 487.00


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
