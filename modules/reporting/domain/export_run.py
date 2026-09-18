"""Выгрузка — единственный корень агрегата Reporting.

Модуль не владеет ни одной предметной сущностью: всё содержимое отчётов
принадлежит другим и существует в файле только на момент отдачи (инвариант
4). Владеет он журналом выгрузок — ответом на вопрос «кто и когда выгружал
персональные данные». Здесь только stdlib.
"""

from dataclasses import dataclass, replace

STARTED = "started"
SUCCEEDED = "succeeded"
FAILED = "failed"


@dataclass(frozen=True)
class Report:
    """Именованный вид выгрузки: состав и формат заданы заранее —
    пользователь выбирает отчёт, а не поля."""

    code: str
    title: str
    format: str          # "xlsx" | "json"
    audience: str        # "owner" | "tenant"


#: Четыре отчёта P1. JSON-пара приходит шагом G2 — до тех пор их нет и в
#: перечне доступного: отчёт, который нельзя выполнить, не предлагается.
CATALOGUE = (
    Report("financial", "Финансовый за период", "xlsx", "owner"),
    Report("registry", "Реестр", "xlsx", "owner"),
)


def report(code: str) -> Report:
    for entry in CATALOGUE:
        if entry.code == code:
            return entry
    raise UnknownReport(f"Нет отчёта с кодом «{code}».")


def available_for(audience: str):
    return [entry for entry in CATALOGUE if entry.audience == audience]


class UnknownReport(LookupError):
    pass


@dataclass(frozen=True)
class ExportRun:
    """Единичное исполнение отчёта.

    Запись заводится **до** начала сбора данных (инвариант 1): аудит по
    152-ФЗ отвечает «кто пытался получить персональные данные», а не «кто
    успешно получил». Запись не изменяется и не удаляется (инвариант 2) —
    исход дописывается, прошлое не переписывается.
    """

    run_id: int | None
    report_code: str
    initiated_by: int
    scope: str
    state: str = STARTED
    error: str = ""

    def succeeded(self) -> "ExportRun":
        return replace(self, state=SUCCEEDED)

    def failed(self, error: str) -> "ExportRun":
        return replace(self, state=FAILED, error=error[:300])
