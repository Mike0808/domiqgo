"""Хранение счётного контура: с шага H3 — ORM собственных моделей.

До H3 чтение шло сырым SQL по имени таблицы: таблицами владел легаси, которого
модулям импортировать нельзя. Таблицы переехали — SQL сменился на ORM, и
контракт `api/` не шелохнулся (как и обещал комментарий на G1).
"""

from decimal import Decimal

from django.db.models import F, Q

from .models import BillingPolicy, MonthlyStatement, Settlement


def _row(stmt) -> dict:
    return {"invoice_id": stmt.pk, "property_id": stmt.apartment_id,
            "tenancy_id": stmt.tenancy_id, "period": stmt.period,
            "total": stmt.total, "issued_at": stmt.issued_at,
            "due_date": stmt.due_date}


# -- read-контракт (G1/G2) ------------------------------------------------

def list_invoice_rows(period_from=None, period_to=None) -> list[dict]:
    rows = MonthlyStatement.objects.all()
    if period_from is not None:
        rows = rows.filter(period__gte=period_from)
    if period_to is not None:
        rows = rows.filter(period__lte=period_to)
    return [dict(_row(stmt), lines=stmt.lines)
            for stmt in rows.order_by("period", "id")]


def get_invoice(invoice_id) -> dict | None:
    stmt = MonthlyStatement.objects.filter(pk=invoice_id).first()
    return _row(stmt) if stmt is not None else None


def list_outstanding_invoices(tenancy_id=None, property_id=None) -> list[dict]:
    """Выставленные и непогашенные по сверке счета — кандидаты для платежа.

    «Погашен» — как в статусе счёта: признано больше нуля и не меньше итога
    (ADR-0015); всё остальное — непогашенное. Счета без договора учитываются
    по объекту: наследие миграции E2. Без адресата перечня нет — иначе это
    был бы список чужих долгов.
    """
    if tenancy_id is None and property_id is None:
        return []
    matches = Q(pk=None)
    if tenancy_id is not None:
        matches |= Q(tenancy_id=tenancy_id)
    if property_id is not None:
        matches |= Q(apartment_id=property_id, tenancy_id=None)
    candidates = list(MonthlyStatement.objects
                      .filter(matches, issued_at__isnull=False)
                      .order_by("period", "id"))
    settled = dict(Settlement.objects
                   .filter(statement_id__in=[s.pk for s in candidates])
                   .values_list("statement_id", "confirmed_total"))
    return [{"invoice_id": s.pk, "tenancy_id": s.tenancy_id,
             "period": s.period, "total": s.total}
            for s in candidates
            if not (settled.get(s.pk, Decimal("0")) > 0
                    and settled.get(s.pk, Decimal("0")) >= s.total)]


# -- команды --------------------------------------------------------------

def due_days() -> int:
    return BillingPolicy.get().due_days


def set_issued(invoice_id, issued_at, due_date) -> None:
    MonthlyStatement.objects.filter(pk=invoice_id).update(
        issued_at=issued_at, due_date=due_date)


def draft_state(tenancy_id, property_id, period) -> dict | None:
    """Строка, в которую ляжет пересчёт: счёт договора за период — или
    оставшийся без договора счёт тех же объекта и месяца (усыновление E2)."""
    stmt = (MonthlyStatement.objects
            .filter(tenancy_id=tenancy_id, period=period).first()
            or MonthlyStatement.objects
            .filter(apartment_id=property_id, period=period,
                    tenancy_id=None).first())
    return _row(stmt) if stmt is not None else None


def write_draft(invoice_id, tenancy_id, property_id, period, lines,
                total) -> int:
    stmt = (MonthlyStatement.objects.get(pk=invoice_id)
            if invoice_id is not None
            else MonthlyStatement(period=period))
    stmt.tenancy_id = tenancy_id
    stmt.apartment_id = property_id
    stmt.lines = lines
    stmt.total = total
    stmt.save()
    return stmt.pk


# -- сверка (ADR-0015) ----------------------------------------------------

def settlement_total(statement_id) -> Decimal:
    row = Settlement.objects.filter(statement_id=statement_id).first()
    return row.confirmed_total if row is not None else Decimal("0")


def add_to_settlement(statement_id, delta) -> None:
    Settlement.objects.get_or_create(statement_id=statement_id)
    Settlement.objects.filter(statement_id=statement_id).update(
        confirmed_total=F("confirmed_total") + delta)


def set_settlement(statement_id, total) -> None:
    Settlement.objects.update_or_create(
        statement_id=statement_id, defaults={"confirmed_total": total})
