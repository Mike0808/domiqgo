"""Чтение счетов для read-контракта.

Таблицы пока принадлежат легаси-`billing/`; импортировать его модулям
запрещено, поэтому чтение идёт по имени таблицы. При расформировании таблица
переедет сюда вместе с моделью, и SQL сменится на ORM — контракт `api/` не
шелохнётся.
"""

import json

from django.db import connection


def list_invoice_rows(period_from=None, period_to=None) -> list[dict]:
    with connection.cursor() as cursor:
        where, args = [], []
        if period_from is not None:
            where.append("period >= %s"); args.append(period_from)
        if period_to is not None:
            where.append("period <= %s"); args.append(period_to)
        clause = f" WHERE {' AND '.join(where)}" if where else ""
        cursor.execute(
            "SELECT apartment_id, tenancy_id, period, lines, total, issued_at,"
            " due_date FROM billing_monthlystatement" + clause +
            " ORDER BY period, id", args)
        return [{
            "property_id": row[0], "tenancy_id": row[1], "period": row[2],
            "lines": json.loads(row[3]) if isinstance(row[3], str) else row[3],
            "total": row[4], "issued_at": row[5], "due_date": row[6],
        } for row in cursor.fetchall()]
