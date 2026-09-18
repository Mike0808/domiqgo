"""Крошечный писатель XLSX: настоящий zip, настоящие формулы."""

import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO

from modules.reporting.infrastructure.xlsx import Formula, workbook

STAMP = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def test_the_file_is_a_valid_zip_with_declared_sheets():
    payload = workbook(STAMP, [("Лист", [["Заголовок"], ["значение", 5]])])

    archive = zipfile.ZipFile(BytesIO(payload))
    assert archive.testzip() is None
    names = set(archive.namelist())
    assert {"[Content_Types].xml", "xl/workbook.xml",
            "xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml"} <= names
    book = archive.read("xl/workbook.xml").decode()
    assert "Лист" in book and "Снимок" in book       # отметка времени — листом


def test_totals_are_formulas_not_precomputed_values():
    """Складывает Excel, а не Reporting: результат остаётся проверяемым."""
    payload = workbook(STAMP, [
        ("Т", [["Сумма"], [Decimal("2")], [Formula("SUM(A2:A2)")]])])

    sheet = zipfile.ZipFile(BytesIO(payload)).read(
        "xl/worksheets/sheet1.xml").decode()
    assert "<f>SUM(A2:A2)</f>" in sheet
    assert "&" not in sheet.replace("&amp;", "").replace("&lt;", "")


def test_text_dates_and_numbers_survive_escaping():
    from datetime import date

    payload = workbook(STAMP, [
        ("Т", [["<жилец> & Ко", date(2026, 7, 1), Decimal("21500.00")]])])

    sheet = zipfile.ZipFile(BytesIO(payload)).read(
        "xl/worksheets/sheet1.xml").decode()
    assert "&lt;жилец&gt; &amp; Ко" in sheet
    assert "01.07.2026" in sheet and "21500.00" in sheet
