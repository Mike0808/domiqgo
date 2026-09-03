"""Шаблоны: как из повода получить текст. Принадлежат Notifications.

Имя жильца и наименование объекта читаются запросами Tenancy и Properties в
момент составления текста (ADR-0019): событие несёт идентификаторы, а не
наименования — иначе каждый издатель подстраивал бы нагрузку под подписчика.
"""

from modules.properties import api as properties
from modules.tenancy import api as tenancy

MONTHS_RU = ["", "январь", "февраль", "март", "апрель", "май", "июнь",
             "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


def month(period) -> str:
    return f"{MONTHS_RU[period.month]} {period.year}"


def _label(property_id) -> str:
    obj = properties.get_property(property_id)
    return obj.label if obj is not None else f"объект #{property_id}"


def invoice_issued(event) -> str:
    return (f"Выставлен счёт за {month(event.period)} — {_label(event.property_id)}: "
            f"{event.total} ₽. Оплатите до {event.due_date:%d.%m.%Y}.")


def invoice_settled(event) -> str:
    return (f"Счёт за {month(event.period)} — {_label(event.property_id)} "
            f"погашен. Спасибо!")


def payment_submitted(event) -> str:
    where = ""
    if event.tenancy_id is not None:
        contract = tenancy.get_tenancy(event.tenancy_id)
        if contract is not None:
            where = f" — {_label(contract.property_id)}, {contract.full_name}"
    return f"Пришёл чек ({event.source}){where}. Проверьте и подтвердите."


def payment_confirmed(event) -> str:
    return f"Платёж на {event.amount} ₽ принят. Спасибо!"


def payment_rejected(event) -> str:
    reason = f": {event.reason}" if event.reason else ""
    return f"Чек не принят{reason}. Свяжитесь с арендодателем."


def payment_voided(event) -> str:
    return (f"Подтверждённый платёж на {event.amount} ₽ отменён "
            f"({event.reason}). Счёт снова ждёт оплаты.")


def tenancy_ended(event) -> str:
    return (f"Договор по объекту «{_label(event.property_id)}» завершён "
            f"{event.ended_on:%d.%m.%Y}.")
