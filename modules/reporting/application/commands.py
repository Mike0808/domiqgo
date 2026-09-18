"""`RunExport` — единственная команда модуля.

Не бедность, а следствие устройства: всё разнообразие лежит в составе
отчётов. Право запрашивающего проверяет прикладной слой (ADR-0023) — сюда
приходит уже проверенный `initiated_by`, и он пишется в журнал независимо от
того, кто проверял.
"""

from ..domain.export_run import ExportRun, report
from .ports import RunJournal
from .reports import build


def run_export(journal: RunJournal, report_code: str, initiated_by: int,
               scope: str = "все объекты", params: dict | None = None):
    """Выполнить отчёт и вернуть (имя файла, содержимое байтами).

    Файл не сохраняется (инвариант 4): он существует ровно столько, сколько
    идёт отдача. Неудача сбора остаётся в журнале — ради неё запись и
    заводится заранее.
    """
    entry = report(report_code)
    run = journal.open(ExportRun(run_id=None, report_code=report_code,
                                 initiated_by=initiated_by, scope=scope))
    try:
        filename, payload = build(entry, run, params or {})
    except Exception as exc:
        journal.close(run.failed(f"{type(exc).__name__}: {exc}"))
        raise
    journal.close(run.succeeded())
    return filename, payload
