"""Состояние сверки для тестов (шаг E3).

`settle`/`pend` фабрикуют состояние напрямую — для тестов о блокировках и
отображении, которым не важен путь событий. Путь событий проверяет
`test_settlement.py`.

`wire` возвращает подписку сверки: чужие тесты чистят реестр шины целиком
(`clear_subscribers`), и подписка, сделанная приложением при старте, до
платёжного теста может не дожить.
"""

from decimal import Decimal

from billing.models import Payment, Settlement


def settle(statement, amount=None):
    """Счёт погашен: признанная сумма не меньше итога (и больше нуля)."""
    value = amount if amount is not None else (statement.total or Decimal("1"))
    Settlement.objects.update_or_create(
        statement_id=statement.pk, defaults={"confirmed_total": value})


def issue(statement):
    """Счёт предъявлен — фабрикой, без команды: для тестов о платежах и
    замках, которым не важен путь выставления. Путь проверяет
    `test_issuing.py`."""
    from django.utils import timezone

    statement.issued_at = timezone.now()
    statement.save(update_fields=["issued_at"])
    return statement


def pend(statement):
    """По счёту есть заявленный платёж — «на проверке»."""
    return Payment.objects.create(statement=statement, source=Payment.WEB,
                                  status=Payment.PENDING)


def wire():
    from bus import subscribe
    from modules.payments.events import PaymentConfirmed, PaymentVoided

    from billing.services import settlement

    subscribe(PaymentConfirmed, settlement.apply_confirmed)
    subscribe(PaymentVoided, settlement.apply_voided)
