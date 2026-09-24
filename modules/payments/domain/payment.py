"""Правила платежа — чистые, без Django и без хранения (шаг H2).

Инварианты спецификации Payments, переехавшие сюда из легаси-`intake.py`:

- **инв. 2** — сумма есть только у подтверждённого платежа и строго
  положительна: у заявленного чека суммы ещё нет;
- **инв. 4** — отменяется только подтверждённый платёж и только с причиной:
  у заявленного и отклонённого нет суммы в сверке — изымать нечего, их
  отклоняют; отмена без причины — удаление под другим именем;
- **инв. 5** — платёж не удаляется (правило живёт в интерфейсе запретом
  удаления и здесь отсутствием такой операции);
- **правило выбора счёта (ADR-0014)** — самый ранний непогашенный счёт без
  заявленного платежа: чек уже ждёт решения владельца, второй туда не кладут.
  Перечень непогашенных даёт Billing (`ListOutstandingInvoices`), правило —
  Payments.
"""

PENDING = "pending"
CONFIRMED = "confirmed"
REJECTED = "rejected"
VOIDED = "voided"
#: «Отменён» — не то же, что «отклонён»: отклоняют незнакомца, чья сумма
#: в сверке не участвовала; отменяют признанный платёж, и его сумма
#: изымается из сверки (шаг E5, дефект №16).
STATUS_CHOICES = [
    (PENDING, "На проверке"), (CONFIRMED, "Подтверждён"),
    (REJECTED, "Отклонён"), (VOIDED, "Отменён"),
]
STATUS_LABELS = dict(STATUS_CHOICES)

TELEGRAM = "telegram"
MAX = "max"
WEB = "web"
MANUAL = "manual"
SOURCE_CHOICES = [(TELEGRAM, "Telegram"), (MAX, "MAX"), (WEB, "Веб"),
                  (MANUAL, "Вручную")]


class NoUnpaidStatementError(Exception):
    """Нет непогашенного счёта, к которому можно отнести платёж."""


class InvoiceNotIssued(Exception):
    """Платёж относится к выставленному счёту: черновик — ещё не документ,
    по нему не платят (шаг E4)."""


class OnlyConfirmedIsVoided(Exception):
    """Отменить можно только подтверждённый платёж (инв. 4): у заявленного
    и отклонённого нет суммы в сверке — изымать нечего, их отклоняют."""


class VoidReasonRequired(Exception):
    """Отмена признанного платежа без причины — это удаление под другим
    именем: причина обязательна (спецификация Payments)."""


class PositiveAmountRequired(Exception):
    """Подтверждение требует суммы, и она строго положительна (инв. 2
    спецификации Payments)."""


def checked_amount(amount):
    if amount is None or amount <= 0:
        raise PositiveAmountRequired(
            f"Сумма платежа обязана быть больше нуля, получено: {amount}.")
    return amount


def choose_invoice(outstanding, claimed_invoice_ids):
    """Правило выбора счёта (ADR-0014): первый из непогашенных — они уже
    упорядочены по периоду, — по которому нет заявленного платежа."""
    for invoice in outstanding:
        if invoice["invoice_id"] not in claimed_invoice_ids:
            return invoice
    return None


def voided(status, note, reason):
    """Переход «отменён»: новая пара (статус, примечание) или отказ.

    Запись и чек остаются, причина фиксируется в примечании — жилец,
    заплативший наличными без чека, не останется без следа платежа при
    споре «а я платил» (шаг E5, дефект №16).
    """
    if status != CONFIRMED:
        raise OnlyConfirmedIsVoided(
            f"Платёж в состоянии «{STATUS_LABELS[status]}» не "
            "отменяется — отклоните его.")
    if not (reason or "").strip():
        raise VoidReasonRequired("Укажите причину отмены.")
    note = f"{note}; отменён: {reason}" if note else f"отменён: {reason}"
    return VOIDED, note
