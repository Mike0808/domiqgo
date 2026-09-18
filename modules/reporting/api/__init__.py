"""Публичный API Reporting — единственная дверь для остальных модулей.

| Спецификация | Здесь |
|---|---|
| `RunExport` | `run_export` |
| `ListAvailableReports` | `list_available_reports` |
| `ListExportRuns` | `list_export_runs` |

**Право запрашивающего проверяет прикладной слой** (ADR-0023): модуль следит
за согласованностью области выгрузки, а `initiated_by` обязан приходить
снаружи и пишется в журнал независимо от того, кто проверял право.

**Чего здесь пока нет.** JSON-отчёты «Полная выгрузка» и «Мои данные» —
шаг **G2**.
"""

from ..application import commands, queries
from ..domain.export_run import Report, ScopeViolation, UnknownReport, report


def _journal():
    """Импорт внутри функции: `api/__init__` попадает в граф импортов раньше,
    чем Django готов отдать модели."""
    from ..infrastructure import repository

    return repository


def wire(documents_meta) -> None:
    """Внедрить `ListDocumentsMeta(tenancy_id)` (ADR-0022): модуля Documents
    нет, его граница лишь зафиксирована — провайдера даёт интерфейсный слой,
    как резолвер владельцев в Notifications."""
    from ..application import reports

    reports.wire(documents_meta)


def content_type(report_code: str) -> str:
    """MIME по формату отчёта — формат следует из назначения, не выбирается."""
    return {
        "xlsx": ("application/vnd.openxmlformats-officedocument"
                 ".spreadsheetml.sheet"),
        "json": "application/json",
    }[report(report_code).format]


def run_export(report_code: str, initiated_by: int,
               scope: str = "все объекты", params: dict | None = None):
    """Выполнить отчёт и вернуть (имя файла, байты). Файл не сохраняется."""
    return commands.run_export(_journal(), report_code, initiated_by, scope,
                               params)


def list_available_reports(audience: str) -> list[Report]:
    """Какие отчёты доступны владельцу («owner») и какие жильцу («tenant»)."""
    return queries.list_available_reports(audience)


def list_export_runs():
    """Журнал: кто, что, когда выгружал и чем закончилось."""
    return queries.list_export_runs(_journal())


__all__ = ["Report", "ScopeViolation", "UnknownReport",
           "run_export", "list_available_reports", "list_export_runs",
           "wire", "content_type"]
