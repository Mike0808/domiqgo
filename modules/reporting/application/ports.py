"""Порт журнала выгрузок."""

from typing import Protocol

from ..domain.export_run import ExportRun


class RunJournal(Protocol):
    def open(self, run: ExportRun) -> ExportRun:
        """Записать попытку — до начала сбора данных (инвариант 1)."""

    def close(self, run: ExportRun) -> None:
        """Дописать исход. Ничего больше запись не меняет (инвариант 2)."""

    def list_runs(self) -> list[ExportRun]: ...
