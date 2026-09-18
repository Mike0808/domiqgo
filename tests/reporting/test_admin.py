"""Журнал выгрузок в панели: запуск, файл, неизменяемость записей."""

import pytest
from django.contrib.auth.models import User
from django.test import Client

from modules.reporting.infrastructure.models import ExportRun

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client():
    User.objects.create_superuser("boss", "b@e.com", "pass12345")
    c = Client()
    c.login(username="boss", password="pass12345")
    return c


def test_the_journal_page_offers_the_reports(admin_client):
    page = admin_client.get("/admin/reporting/exportrun/").content.decode()
    assert "Реестр (XLSX)" in page and "Финансовый за период" in page


def test_running_a_report_returns_the_file_and_logs_the_initiator(admin_client):
    response = admin_client.get("/admin/reporting/exportrun/?run=registry")

    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment;")
    assert response.content[:2] == b"PK"           # zip: файл не сохраняется
    (run,) = ExportRun.objects.all()
    assert run.initiated_by == User.objects.get(username="boss").pk
    assert run.state == "succeeded"


def test_journal_rows_have_no_edit_or_delete(admin_client):
    """Инвариант 2: запись журнала не изменяется и не удаляется — в панели
    нет ни добавления, ни правки, ни удаления."""
    row = ExportRun.objects.create(report_code="registry", initiated_by=1,
                                   scope="все")
    base = "/admin/reporting/exportrun/"
    assert admin_client.get(f"{base}add/").status_code == 403
    assert admin_client.post(f"{base}{row.pk}/change/",
                             {"scope": "чужая"}).status_code == 403
    assert admin_client.post(f"{base}{row.pk}/delete/",
                             {"post": "yes"}).status_code == 403
