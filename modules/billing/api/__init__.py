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


__all__ = ["list_invoice_rows"]
