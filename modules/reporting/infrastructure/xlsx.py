"""Крошечный писатель XLSX — stdlib, без зависимостей.

XLSX — это zip с XML (SpreadsheetML). Владелец с тремя квартирами не должен
тянуть библиотеку ради трёх листов со строками и формулой «Итого»; на сервере
с гигабайтом памяти зависимость дороже сотни строк. Строки — inline,
формулы — настоящие: складывает Excel, а не Reporting (спецификация).
"""

import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape


@dataclass(frozen=True)
class Formula:
    """Итоговая строка — формула, не вычисленное значение: результат
    остаётся проверяемым, видно, из чего он получился."""

    text: str


def _column(index: int) -> str:
    name = ""
    while index >= 0:
        name = chr(ord("A") + index % 26) + name
        index = index // 26 - 1
    return name


def _cell(ref, value):
    if isinstance(value, Formula):
        return f'<c r="{ref}"><f>{escape(value.text)}</f></c>'
    if isinstance(value, bool):
        value = "да" if value else "нет"
    if isinstance(value, (int, Decimal, float)):
        return f'<c r="{ref}"><v>{value}</v></c>'
    if isinstance(value, (date, datetime)):
        value = value.strftime("%d.%m.%Y")
    text = escape(str(value))
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _sheet_xml(rows) -> str:
    body = []
    for r, row in enumerate(rows, start=1):
        cells = "".join(_cell(f"{_column(c)}{r}", value)
                        for c, value in enumerate(row))
        body.append(f'<row r="{r}">{cells}</row>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main"><sheetData>'
            + "".join(body) + "</sheetData></worksheet>")


def workbook(stamp, sheets) -> bytes:
    """`sheets` — пары (имя листа, строки); ячейка — str/число/дата/Formula.

    Отметка времени попадает отдельным листом: снимок не мгновенный, и файл
    обязан говорить, на какой момент он честен (спецификация).
    """
    sheets = list(sheets) + [
        ("Снимок", [["Сформировано (UTC)", stamp.strftime("%d.%m.%Y %H:%M")]])]
    n = len(sheets)
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.spreadsheetml.'
            'worksheet+xml"/>' for i in range(1, n + 1))
        + "</Types>")
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>")
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        + "".join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
                  for i, (name, _) in enumerate(sheets, start=1))
        + "</sheets></workbook>")
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.'
            f'org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, n + 1))
        + "</Relationships>")

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        for i, (_, rows) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(rows))
    return buffer.getvalue()
