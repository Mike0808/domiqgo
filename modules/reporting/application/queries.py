"""Чтение: доступные отчёты и журнал выгрузок."""

from ..domain.export_run import available_for


def list_available_reports(audience: str):
    return available_for(audience)


def list_export_runs(journal):
    return journal.list_runs()
