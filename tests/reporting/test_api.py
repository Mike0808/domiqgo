"""Публичная поверхность Reporting: журнал, отчёты, отказы (шаг G1)."""

import zipfile
from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest

from billing.models import MonthlyStatement
from billing.services.intake import record_payment
from billing.tests.settle import issue
from billing.tests.tenancies import let_in
from modules.properties import api as properties
from modules.reporting import api
from modules.reporting.infrastructure.models import ExportRun

pytestmark = pytest.mark.django_db(transaction=True)

BOSS = 1


def _sheet(payload, index):
    return zipfile.ZipFile(BytesIO(payload)).read(
        f"xl/worksheets/sheet{index}.xml").decode()


def _home():
    from billing.models import Apartment

    flat_id = properties.register_property("кв. на Ленина", has_hot_water=False)
    let_in(Apartment.objects.get(pk=flat_id), account_id=11,
           full_name="Иванов", rent="30000")
    return Apartment.objects.get(pk=flat_id)


def test_the_registry_report_lists_properties_and_tenancies():
    _home()

    filename, payload = api.run_export("registry", initiated_by=BOSS)

    assert filename.startswith("registry_") and filename.endswith(".xlsx")
    assert "кв. на Ленина" in _sheet(payload, 1)
    contracts = _sheet(payload, 2)
    assert "Иванов" in contracts and "30000" in contracts

    (run,) = api.list_export_runs()
    assert run.report_code == "registry" and run.state == "succeeded"
    assert run.initiated_by == BOSS


def test_the_financial_report_carries_lines_payments_and_formulas():
    flat = _home()
    stmt = issue(MonthlyStatement.objects.create(
        apartment=flat, period=date(2026, 7, 1), total=Decimal("21500"),
        tenancy_id=1,
        lines=[{"code": "rent", "label": "Аренда", "quantity": None,
                "rate": "21500.00", "amount": "21500.00"}]))
    record_payment(stmt, Decimal("21500"), note="наличными")

    filename, payload = api.run_export(
        "financial", initiated_by=BOSS, scope="период 2026-07..2026-07",
        params={"from": date(2026, 7, 1), "to": date(2026, 7, 1)})

    invoices = _sheet(payload, 1)
    assert "Аренда" in invoices and "<f>SUM(" in invoices
    payments_sheet = _sheet(payload, 2)
    assert "21500" in payments_sheet and "manual" in payments_sheet

    (run,) = api.list_export_runs()
    assert run.scope == "период 2026-07..2026-07"


def test_the_period_bounds_are_honoured():
    flat = _home()
    issue(MonthlyStatement.objects.create(
        apartment=flat, period=date(2026, 6, 1), total=Decimal("1"),
        tenancy_id=1, lines=[{"code": "rent", "label": "Июньская строка",
                              "quantity": None, "rate": "1", "amount": "1"}]))

    _, payload = api.run_export(
        "financial", initiated_by=BOSS,
        params={"from": date(2026, 7, 1), "to": date(2026, 7, 1)})

    assert "Июньская строка" not in _sheet(payload, 1)


def test_a_failed_run_stays_in_the_journal():
    """Инвариант 1: запись заводится до сбора — аудит видит и попытки."""
    from modules.reporting.application import commands

    original = commands.build
    commands.build = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("сбой"))
    try:
        with pytest.raises(RuntimeError):
            api.run_export("registry", initiated_by=BOSS)
    finally:
        commands.build = original

    (run,) = api.list_export_runs()
    assert run.state == "failed" and "сбой" in run.error


def test_an_unknown_report_is_refused_before_the_journal():
    with pytest.raises(api.UnknownReport):
        api.run_export("mystery", initiated_by=BOSS)
    assert not ExportRun.objects.exists()


def test_the_available_reports_split_by_audience():
    codes = [r.code for r in api.list_available_reports("owner")]
    assert codes == ["financial", "registry", "full"]
    assert [r.code for r in api.list_available_reports("tenant")] == ["my_data"]
