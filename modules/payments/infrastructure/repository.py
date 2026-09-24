"""Хранение платежей: ORM своей таблицы, read-контракт — с сырым соединением.

Команды работают со своей моделью через ORM (шаг H2). Read-контракт для
Reporting дополняет платёж полями счёта — а счётом до шага H3 владеет
легаси-`billing/`, которого модулям импортировать нельзя, поэтому соединение
идёт по имени таблицы `billing_monthlystatement`. На H3 счёт переедет в
`modules/billing`, и соединение сменится на запрос к его API.
"""

from django.db import connection

from .models import Payment


# -- команды --------------------------------------------------------------

def captured(payment_id) -> dict:
    """Снимок платежа для решения в domain: статус, сумма, примечание."""
    row = Payment.objects.get(pk=payment_id)
    return {"payment_id": row.pk, "statement_id": row.statement_id,
            "status": row.status, "amount": row.amount, "note": row.note,
            "source": row.source}


def claimed_invoice_ids(invoice_ids) -> set:
    """Счета из перечня, по которым уже есть заявленный платёж."""
    return set(Payment.objects
               .filter(statement_id__in=invoice_ids, status=Payment.PENDING)
               .values_list("statement_id", flat=True))


def add_submitted(statement_id, source, file, filename=None) -> int:
    payment = Payment(statement_id=statement_id, source=source)
    payment.file.save(filename or getattr(file, "name", "receipt"), file,
                      save=False)
    payment.save()
    return payment.pk


def add_confirmed(statement_id, amount, note="") -> int:
    payment = Payment.objects.create(
        statement_id=statement_id, source=Payment.MANUAL,
        status=Payment.CONFIRMED, amount=amount, note=note)
    return payment.pk


def set_state(payment_id, status, amount=..., note=...) -> None:
    """Записать исход перехода; сумму и примечание — только если решены."""
    fields = {"status": status}
    if amount is not ...:
        fields["amount"] = amount
    if note is not ...:
        fields["note"] = note
    Payment.objects.filter(pk=payment_id).update(**fields)


# -- read-контракт (G1/G2) ------------------------------------------------

def list_confirmed_payments(period_from=None, period_to=None) -> list[dict]:
    with connection.cursor() as cursor:
        where, args = ["p.status = 'confirmed'"], []
        if period_from is not None:
            where.append("s.period >= %s"); args.append(period_from)
        if period_to is not None:
            where.append("s.period <= %s"); args.append(period_to)
        cursor.execute(
            "SELECT s.apartment_id, s.period, p.source, p.amount,"
            " p.submitted_at FROM payments_payment p"
            " JOIN billing_monthlystatement s ON s.id = p.statement_id"
            " WHERE " + " AND ".join(where) +
            " ORDER BY p.submitted_at, p.id", args)
        return [{
            "property_id": row[0], "period": row[1], "source": row[2],
            "amount": row[3], "submitted_at": row[4],
        } for row in cursor.fetchall()]


def list_payments(statement_ids=None) -> list[dict]:
    with connection.cursor() as cursor:
        clause, args = "", []
        if statement_ids is not None:
            marks = ",".join(["%s"] * len(statement_ids)) or "NULL"
            clause = f" WHERE p.statement_id IN ({marks})"
            args = list(statement_ids)
        cursor.execute(
            "SELECT p.statement_id, s.apartment_id, s.period, p.source,"
            " p.status, p.amount, p.note, p.submitted_at"
            " FROM payments_payment p"
            " JOIN billing_monthlystatement s ON s.id = p.statement_id"
            + clause + " ORDER BY p.submitted_at, p.id", args)
        return [{
            "statement_id": row[0], "property_id": row[1], "period": row[2],
            "source": row[3], "status": row[4], "amount": row[5],
            "note": row[6], "submitted_at": row[7],
        } for row in cursor.fetchall()]
