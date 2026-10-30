"""Публичный API Billing: команды счётного контура и read-контракт.

Команды переехали из легаси-`billing/services/` шагом H3; события публикуются
из `application/` (правило 4.4). Интерфейсный слой передаёт идентификаторы —
объекта, договора, счёта: моделей модуля снаружи не видно.
"""

from ..domain.invoice import (
    DraftWithoutTenancy, InvoiceAlreadyIssued, MissingTenancyError,
)


def _repository():
    from ..infrastructure import repository

    return repository


def list_invoice_rows(period_from=None, period_to=None) -> list[dict]:
    """Начисления построчно: объект, договор, период, строки, итог, момент
    предъявления. Строки несут применённые ставки значениями (инв. 6).
    Границы — первые числа месяцев, включительно; пустые — за всё время."""
    return _repository().list_invoice_rows(period_from, period_to)


def get_invoice(invoice_id) -> dict | None:
    """Один счёт: объект, договор, период, итог, момент предъявления и срок
    оплаты — или None. Появился для команд Payments (шаг H2)."""
    return _repository().get_invoice(invoice_id)


def list_outstanding_invoices(tenancy_id=None, property_id=None) -> list[dict]:
    """`ListOutstandingInvoices` (ADR-0014): выставленные и непогашенные по
    сверке счета договора, по периоду. Счета без договора — по объекту
    (наследие миграции E2). Без адресата перечень пуст."""
    return _repository().list_outstanding_invoices(tenancy_id, property_id)


def generate_statement(property_id, period) -> int:
    """Пересчитать черновик начисления за период; счёт ключуется договором
    периода (ADR-0024). Возвращает идентификатор счёта."""
    from ..application import generation

    return generation.generate_statement(property_id, period)


def issue_invoice(invoice_id, at=None) -> None:
    """Предъявить счёт: зафиксировать, назначить срок оплаты (ADR-0013),
    закрыть период показаний (ADR-0012)."""
    from ..application import issuing

    issuing.issue_invoice(invoice_id, at)


def rebuild_settlement(invoice_id):
    """`RebuildSettlement`: пересобрать проекцию из журнала событий
    (ADR-0015). Возвращает признанную сумму."""
    from ..application import settlement

    return settlement.rebuild_settlement(invoice_id)


def settlement_matches_journal(invoice_id) -> bool:
    """Сходится ли проекция сверки с журналом шины."""
    from ..application import settlement

    return settlement.settlement_matches_journal(invoice_id)


def missing_meters(property_id) -> list[str]:
    """Чего не хватает в реестре приборов для полного счёта — названиями."""
    from ..application import generation

    return generation.missing_meters(property_id)


def metered_resources(property_id) -> list[str]:
    """Что начисляется по приборам — из реестра Metering."""
    from ..application import generation

    return generation.metered_resources(property_id)


def subscribe_to_payment_events() -> None:
    """Подписать сверку на события Payments (ADR-0015). Зовётся при старте
    и тестовыми обвязками после очистки шины; подписка дедуплицируется."""
    from ..application import subscriptions

    subscriptions.wire()


def wire(has_pending_claim) -> None:
    """Внедрить провайдер «есть ли заявленный платёж по счёту» (шаг H3).

    «На проверке» — знание Payments, а стрелка payments → billing не
    разворачивается: провайдер даёт интерфейсный слой — как резолвер
    владельцев в F3 и метаданные документов в G2.
    """
    from ..infrastructure import claims

    claims.wire(has_pending_claim)


__all__ = [
    "list_invoice_rows", "get_invoice", "list_outstanding_invoices",
    "generate_statement", "issue_invoice", "rebuild_settlement",
    "settlement_matches_journal", "missing_meters", "metered_resources",
    "subscribe_to_payment_events", "wire",
    "InvoiceAlreadyIssued", "DraftWithoutTenancy", "MissingTenancyError",
]
