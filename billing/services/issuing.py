"""Интерфейсная оболочка выставления счёта (шаг H3).

Команда переехала в `modules/billing/application`; событие публикуется
оттуда. Здесь — переводчик с языка моделей на язык идентификаторов модуля
и реэкспорт исключений для старых импортов.
"""

from modules.billing import api as billing
from modules.billing.api import (  # noqa: F401 — реэкспорт для старых импортов
    DraftWithoutTenancy, InvoiceAlreadyIssued,
)


def issue_invoice(statement, at=None):
    billing.issue_invoice(statement.pk, at)
    statement.refresh_from_db()
    return statement
