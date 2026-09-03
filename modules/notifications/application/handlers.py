"""Реакция на события: составить текст и поставить в очередь.

Приём события не отправляет сообщение — отправкой занимается прогон (F2).
Получатель-жилец берётся из договора (Tenancy); получатели-владельцы приходят
резолвером, внедрённым интерфейсным слоем при подписке: Identity модуль не
вызывает (матрица §2).

`InvoiceRevised`, `InvoiceCancelled` и `PaymentOverdue` из спецификации ждут
своих издателей — команд ревизии и проверки просрочки ещё нет.
"""

from modules.tenancy import api as tenancy

from . import templates


def _tenant_account(tenancy_id):
    if tenancy_id is None:
        return None
    contract = tenancy.get_tenancy(tenancy_id)
    return contract.account_id if contract is not None else None


def to_tenant(enqueue, tenancy_id, text) -> None:
    account_id = _tenant_account(tenancy_id)
    if account_id is not None:
        enqueue(account_id, text)


def invoice_issued(enqueue, event) -> None:
    to_tenant(enqueue, event.tenancy_id, templates.invoice_issued(event))


def invoice_settled(enqueue, event) -> None:
    to_tenant(enqueue, event.tenancy_id, templates.invoice_settled(event))


def payment_submitted(enqueue, owner_accounts, event) -> None:
    text = templates.payment_submitted(event)
    for account_id in owner_accounts():
        enqueue(account_id, text)


def payment_confirmed(enqueue, event) -> None:
    to_tenant(enqueue, event.tenancy_id, templates.payment_confirmed(event))


def payment_rejected(enqueue, event) -> None:
    to_tenant(enqueue, event.tenancy_id, templates.payment_rejected(event))


def payment_voided(enqueue, event) -> None:
    to_tenant(enqueue, event.tenancy_id, templates.payment_voided(event))


def tenancy_ended(enqueue, event) -> None:
    contract = tenancy.get_tenancy(event.tenancy_id)
    if contract is not None:
        enqueue(contract.account_id, templates.tenancy_ended(event))
