"""Проекция признанных оплат и её пересборка (шаг E3, ADR-0015; в модуле
с H3).

Проекция строится исключительно из событий `PaymentConfirmed` и
`PaymentVoided`. На P1 доставка синхронна и идёт после коммита — между
коммитом платежа и обновлением проекции есть окно, в котором событие может
пропасть при сбое. Признать это и дать команду пересборки честнее, чем делать
вид, что расхождение невозможно; потому `rebuild_settlement` доступна
владельцу из списка начислений, а не только из консоли.
"""

from decimal import Decimal

from django.utils import timezone

from bus import publish

from ..domain import invoice as rules
from ..events import InvoiceSettled
from ..infrastructure import repository

CONFIRMED = "modules.payments.events.PaymentConfirmed"
VOIDED = "modules.payments.events.PaymentVoided"


def apply_confirmed(event) -> None:
    repository.add_to_settlement(event.statement_id, event.amount)
    _announce_if_settled(event.statement_id)


def _announce_if_settled(statement_id: int) -> None:
    """`InvoiceSettled` — когда признанное впервые покрыло итог.

    Сверка — единственная, кто знает момент погашения; событие ведёт к
    сообщению жильцу (F3) и однажды к Analytics.
    """
    invoice = repository.get_invoice(statement_id)
    if invoice is None:
        return
    settled = repository.settlement_total(statement_id)
    if rules.settled_status(settled, invoice["total"], False) != rules.PAID:
        return
    publish(InvoiceSettled(
        invoice_id=statement_id, tenancy_id=invoice["tenancy_id"],
        property_id=invoice["property_id"], period=invoice["period"],
        total=invoice["total"], at=timezone.now()))


def apply_voided(event) -> None:
    repository.add_to_settlement(event.statement_id, -event.amount)


def settled_by_journal(statement_id: int) -> Decimal:
    """Признанная сумма по журналу шины — источнику пересборки.

    Журнал хранит платежи с шага E3; подтверждения прежних лет переведены в
    него миграцией `billing/0022` со своими датами — как согласия на C4a.
    Журнал — забота шины, и читается он из `application/`: правило 4.4
    держит `bus` именно здесь.
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
    repository.set_settlement(statement_id, total)
    return total


def settlement_matches_journal(statement_id: int) -> bool:
    """Сходится ли проекция с журналом — проверка из плана шага E3."""
    return repository.settlement_total(statement_id) == settled_by_journal(
        statement_id)
