"""Перевод между выгрузками домена и строками журнала."""

from ..domain.export_run import ExportRun as DomainRun
from . import models


def _to_domain(row: models.ExportRun) -> DomainRun:
    return DomainRun(run_id=row.pk, report_code=row.report_code,
                     initiated_by=row.initiated_by, scope=row.scope,
                     state=row.state, error=row.error)


def open(run: DomainRun) -> DomainRun:
    row = models.ExportRun.objects.create(
        report_code=run.report_code, initiated_by=run.initiated_by,
        scope=run.scope, state=run.state)
    return _to_domain(row)


def close(run: DomainRun) -> None:
    models.ExportRun.objects.filter(pk=run.run_id).update(
        state=run.state, error=run.error)


def list_runs() -> list[DomainRun]:
    return [_to_domain(r) for r in models.ExportRun.objects.all()]
