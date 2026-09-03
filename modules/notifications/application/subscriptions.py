"""Подписка модуля на события — семь поводов из десяти (шаг F3).

Правило 4.4 держит `bus` в `application/`. Резолвер владельцев внедряется
вызывающим (интерфейсным слоем): Notifications не вызывает Identity —
матрица §2 разрешает ему только Tenancy и Properties.
"""

from bus import subscribe
from modules.billing.events import InvoiceIssued, InvoiceSettled
from modules.payments.events import (
    PaymentConfirmed, PaymentRejected, PaymentSubmitted, PaymentVoided,
)
from modules.tenancy.events import TenancyEnded

from . import commands, handlers

_owner_accounts = None


def _enqueue(account_id: int, text: str) -> None:
    from ..infrastructure import repository

    commands.enqueue_message(repository, repository, account_id, text)


def wire(owner_accounts) -> None:
    """Повторный вызов безвреден: шина игнорирует повторную подписку."""
    global _owner_accounts
    _owner_accounts = owner_accounts
    subscribe(InvoiceIssued, _on_invoice_issued)
    subscribe(InvoiceSettled, _on_invoice_settled)
    subscribe(PaymentSubmitted, _on_payment_submitted)
    subscribe(PaymentConfirmed, _on_payment_confirmed)
    subscribe(PaymentRejected, _on_payment_rejected)
    subscribe(PaymentVoided, _on_payment_voided)
    subscribe(TenancyEnded, _on_tenancy_ended)


def _on_invoice_issued(event):
    handlers.invoice_issued(_enqueue, event)


def _on_invoice_settled(event):
    handlers.invoice_settled(_enqueue, event)


def _on_payment_submitted(event):
    handlers.payment_submitted(_enqueue, _owner_accounts, event)


def _on_payment_confirmed(event):
    handlers.payment_confirmed(_enqueue, event)


def _on_payment_rejected(event):
    handlers.payment_rejected(_enqueue, event)


def _on_payment_voided(event):
    handlers.payment_voided(_enqueue, event)


def _on_tenancy_ended(event):
    handlers.tenancy_ended(_enqueue, event)
