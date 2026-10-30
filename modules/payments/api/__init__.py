"""Публичный API Payments: команды платёжного потока и read-контракт.

Команды переехали из легаси-`billing/services/intake.py` шагом H2; события
публикуются из `application/` (правило 4.4). Интерфейсный слой передаёт
идентификаторы — договора, счёта, платежа: моделей модуля снаружи не видно.
"""

from ..domain.payment import (
    InvoiceNotIssued, NoUnpaidStatementError, OnlyConfirmedIsVoided,
    PositiveAmountRequired, VoidReasonRequired,
)


def _commands():
    from ..application import commands

    return commands


def _repository():
    from ..infrastructure import repository

    return repository


def submit_receipt(tenancy_id, property_id, file, source, filename=None) -> dict:
    """Принять чек: счёт выбирает правило ADR-0014 — самый ранний
    непогашенный без заявленного платежа. Возвращает
    `{"payment_id", "invoice_id", "period"}`."""
    return _commands().submit_receipt(tenancy_id, property_id, file, source,
                                      filename)


def earliest_unpaid_invoice(tenancy_id, property_id=None) -> dict | None:
    """Счёт, к которому ляжет следующий платёж, — или None."""
    return _commands().earliest_unpaid_invoice(tenancy_id, property_id)


def confirm_payment(payment_id, amount) -> None:
    """Признать заявленный платёж и указать сумму (инв. 2)."""
    _commands().confirm_payment(payment_id, amount)


def record_payment(invoice_id, amount, note="") -> int:
    """Отметить полученный платёж вручную, без чека; платёж рождается
    подтверждённым. Возвращает идентификатор платежа."""
    return _commands().record_payment(invoice_id, amount, note)


def reject_payment(payment_id, note="") -> None:
    """Отклонить заявленный платёж — его сумма в сверке не участвовала."""
    _commands().reject_payment(payment_id, note)


def void_payment(payment_id, reason) -> None:
    """Отменить подтверждённый платёж: запись и чек остаются, сумма
    изымается из сверки событием (инв. 4, 5)."""
    _commands().void_payment(payment_id, reason)


def has_pending_claim(invoice_id) -> bool:
    """Есть ли по счёту заявленный платёж, ждущий решения владельца.

    Появился на H3 — для статуса счёта «на проверке»: Billing спрашивать
    Payments не вправе, провайдер этого ответа внедряет интерфейсный слой.
    """
    return _repository().has_pending_claim(invoice_id)


def list_confirmed_payments(period_from=None, period_to=None) -> list[dict]:
    """Подтверждённые платежи с суммами: объект, период счёта, источник,
    сумма, момент получения. Границы — по периоду счёта."""
    return _repository().list_confirmed_payments(period_from, period_to)


def list_payments(statement_ids=None) -> list[dict]:
    """Вся история платежей — включая заявленные, отклонённые и отменённые:
    полная выгрузка неполна без них (шаг G2)."""
    return _repository().list_payments(statement_ids)


__all__ = [
    "submit_receipt", "earliest_unpaid_invoice", "confirm_payment",
    "record_payment", "reject_payment", "void_payment",
    "has_pending_claim", "list_confirmed_payments", "list_payments",
    "NoUnpaidStatementError", "InvoiceNotIssued", "OnlyConfirmedIsVoided",
    "VoidReasonRequired", "PositiveAmountRequired",
]
