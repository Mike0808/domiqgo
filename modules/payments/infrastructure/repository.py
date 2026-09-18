"""Чтение платежей для read-контракта — по имени таблицы, как у Billing:
легаси импортировать нельзя, а таблица переедет сюда при расформировании."""

from django.db import connection


def list_confirmed_payments(period_from=None, period_to=None) -> list[dict]:
    with connection.cursor() as cursor:
        where, args = ["p.status = 'confirmed'"], []
        if period_from is not None:
            where.append("s.period >= %s"); args.append(period_from)
        if period_to is not None:
            where.append("s.period <= %s"); args.append(period_to)
        cursor.execute(
            "SELECT s.apartment_id, s.period, p.source, p.amount,"
            " p.submitted_at FROM billing_payment p"
            " JOIN billing_monthlystatement s ON s.id = p.statement_id"
            " WHERE " + " AND ".join(where) +
            " ORDER BY p.submitted_at, p.id", args)
        return [{
            "property_id": row[0], "period": row[1], "source": row[2],
            "amount": row[3], "submitted_at": row[4],
        } for row in cursor.fetchall()]
