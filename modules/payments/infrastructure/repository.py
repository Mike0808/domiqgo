"""Хранение платежей: ORM своей таблицы (шаг H2).

Read-контракт для Reporting дополняет платёж полями счёта; с шага H3 счётом
владеет модуль Billing, и вместо сырого соединения по имени таблицы платежи
дополняются его же read-контрактом — обещание комментария времён G1
исполнено. Соединения в SQL больше нет нигде: между модулями — только API.
"""

from .models import Payment


def _invoice_index(statement_ids=None, period_from=None, period_to=None):
    """Счета платежей — из read-контракта Billing, ключом по идентификатору."""
    from modules.billing import api as billing

    if statement_ids is None:
        rows = billing.list_invoice_rows(period_from, period_to)
        return {row["invoice_id"]: row for row in rows}
    index = {}
    for invoice_id in set(statement_ids):
        row = billing.get_invoice(invoice_id)
        if row is not None:
            index[invoice_id] = row
    return index


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

def has_pending_claim(invoice_id) -> bool:
    """Есть ли по счёту заявленный платёж — для статуса «на проверке»."""
    return (Payment.objects
            .filter(statement_id=invoice_id, status=Payment.PENDING)
            .exists())


def list_confirmed_payments(period_from=None, period_to=None) -> list[dict]:
    invoices = _invoice_index(period_from=period_from, period_to=period_to)
    rows = (Payment.objects
            .filter(status=Payment.CONFIRMED, statement_id__in=invoices)
            .order_by("submitted_at", "id"))
    return [{
        "property_id": invoices[p.statement_id]["property_id"],
        "period": invoices[p.statement_id]["period"], "source": p.source,
        "amount": p.amount, "submitted_at": p.submitted_at,
    } for p in rows]


def list_payments(statement_ids=None) -> list[dict]:
    invoices = _invoice_index(statement_ids)
    rows = Payment.objects.order_by("submitted_at", "id")
    if statement_ids is not None:
        rows = rows.filter(statement_id__in=list(statement_ids))
    return [{
        "statement_id": p.statement_id,
        "property_id": invoices[p.statement_id]["property_id"],
        "period": invoices[p.statement_id]["period"], "source": p.source,
        "status": p.status, "amount": p.amount, "note": p.note,
        "submitted_at": p.submitted_at,
    } for p in rows if p.statement_id in invoices]
