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
            "SELECT id, apartment_id, tenancy_id, period, lines, total, issued_at,"
            " due_date FROM billing_monthlystatement" + clause +
            " ORDER BY period, id", args)
        return [{
            "invoice_id": row[0],
            "property_id": row[1], "tenancy_id": row[2], "period": row[3],
            "lines": json.loads(row[4]) if isinstance(row[4], str) else row[4],
            "total": row[5], "issued_at": row[6], "due_date": row[7],
        } for row in cursor.fetchall()]


def get_invoice(invoice_id) -> dict | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, apartment_id, tenancy_id, period, total, issued_at,"
            " due_date FROM billing_monthlystatement WHERE id = %s",
            [invoice_id])
        row = cursor.fetchone()
    if row is None:
        return None
    return {"invoice_id": row[0], "property_id": row[1], "tenancy_id": row[2],
            "period": row[3], "total": row[4], "issued_at": row[5],
            "due_date": row[6]}


def list_outstanding_invoices(tenancy_id=None, property_id=None) -> list[dict]:
    """Выставленные и непогашенные по сверке счета — кандидаты для платежа.

    «Погашен» — как в статусе счёта: признано больше нуля и не меньше итога
    (ADR-0015); всё остальное — непогашенное. Счета без договора учитываются
    по объекту: наследие миграции E2. Без адресата перечня нет — иначе это
    был бы список чужих долгов.
    """
    if tenancy_id is None and property_id is None:
        return []
    matches, args = [], []
    if tenancy_id is not None:
        matches.append("s.tenancy_id = %s"); args.append(tenancy_id)
    if property_id is not None:
        matches.append("(s.apartment_id = %s AND s.tenancy_id IS NULL)")
        args.append(property_id)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT s.id, s.tenancy_id, s.period, s.total"
            " FROM billing_monthlystatement s"
            " LEFT JOIN billing_settlement st ON st.statement_id = s.id"
            " WHERE s.issued_at IS NOT NULL"
            f" AND ({' OR '.join(matches)})"
            " AND NOT (COALESCE(st.confirmed_total, 0) > 0"
            "          AND COALESCE(st.confirmed_total, 0) >= s.total)"
            " ORDER BY s.period, s.id", args)
        return [{"invoice_id": row[0], "tenancy_id": row[1],
                 "period": row[2], "total": row[3]}
                for row in cursor.fetchall()]
