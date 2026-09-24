"""Публичный API Billing — пока только read-контракт для Reporting (шаг G1).

Команды счёта живут в легаси-`billing/` до расформирования; здесь модуль
впервые обязан объявить, что́ о его данных можно читать снаружи — Reporting
на P1 проходит ту же проверку, которую роадмап требует от Analytics в P2.
"""


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


__all__ = ["list_invoice_rows", "get_invoice", "list_outstanding_invoices"]
