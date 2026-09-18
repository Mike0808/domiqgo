"""Публичный API Payments — пока только read-контракт для Reporting (G1).

Команды платежа живут в легаси-`billing/` до расформирования; события модуля
уже публикуются с целевыми именами (E3).
"""


def _repository():
    from ..infrastructure import repository

    return repository


def list_confirmed_payments(period_from=None, period_to=None) -> list[dict]:
    """Подтверждённые платежи с суммами: объект, период счёта, источник,
    сумма, момент получения. Границы — по периоду счёта."""
    return _repository().list_confirmed_payments(period_from, period_to)


__all__ = ["list_confirmed_payments"]
