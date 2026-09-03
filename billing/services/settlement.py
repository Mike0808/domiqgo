"""Проекция признанных оплат и её пересборка (шаг E3, ADR-0015).

Проекция строится исключительно из событий `PaymentConfirmed` и
`PaymentVoided`. На P1 доставка синхронна и идёт после коммита — между
коммитом платежа и обновлением проекции есть окно, в котором событие может
пропасть при сбое. Признать это и дать команду пересборки честнее, чем делать
вид, что расхождение невозможно; потому `rebuild_settlement` доступна
владельцу из списка начислений, а не только из консоли.
"""

from decimal import Decimal

from django.db.models import F
from django.utils import timezone

from bus import publish
from modules.billing.events import InvoiceSettled

from ..models import MonthlyStatement, Settlement

CONFIRMED = "modules.payments.events.PaymentConfirmed"
VOIDED = "modules.payments.events.PaymentVoided"


def apply_confirmed(event) -> None:
    _add(event.statement_id, event.amount)
    _announce_if_settled(event.statement_id)


def _announce_if_settled(statement_id: int) -> None:
    """`InvoiceSettled` — когда признанное впервые покрыло итог.

    Сверка — единственная, кто знает момент погашения; событие ведёт к
    сообщению жильцу (F3) и однажды к Analytics.
    """
    statement = MonthlyStatement.objects.filter(pk=statement_id).first()
    if statement is None or statement.status != MonthlyStatement.PAID:
        return
    publish(InvoiceSettled(
        invoice_id=statement.pk, tenancy_id=statement.tenancy_id,
        property_id=statement.apartment_id, period=statement.period,
        total=statement.total, at=timezone.now()))


def apply_voided(event) -> None:
    _add(event.statement_id, -event.amount)


def _add(statement_id: int, delta) -> None:
    Settlement.objects.get_or_create(statement_id=statement_id)
    Settlement.objects.filter(statement_id=statement_id).update(
        confirmed_total=F("confirmed_total") + delta)


def settled_by_journal(statement_id: int) -> Decimal:
    """Признанная сумма по журналу шины — источнику пересборки.

    Журнал хранит платежи с шага E3; подтверждения прежних лет переведены в
    него миграцией `billing/0022` со своими датами — как согласия на C4a.
    """
    from bus.models import PublishedEvent

    total = Decimal("0")
    for row in PublishedEvent.objects.filter(event_type__in=(CONFIRMED, VOIDED)):
        if int(row.payload.get("statement_id", -1)) != statement_id:
            continue
        amount = Decimal(str(row.payload["amount"]))
        total += amount if row.event_type == CONFIRMED else -amount
    return total


def rebuild_settlement(statement_id: int) -> Decimal:
    """`RebuildSettlement`: пересобрать проекцию из журнала событий."""
    total = settled_by_journal(statement_id)
    Settlement.objects.update_or_create(
        statement_id=statement_id, defaults={"confirmed_total": total})
    return total


def settlement_matches_journal(statement_id: int) -> bool:
    """Сходится ли проекция с журналом — проверка из плана шага E3."""
    row = Settlement.objects.filter(statement_id=statement_id).first()
    current = row.confirmed_total if row is not None else Decimal("0")
    return current == settled_by_journal(statement_id)
